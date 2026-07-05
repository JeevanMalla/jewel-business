"""
pages/orders.py
Order management - search, filter, status update, images, delete, export.
"""
import streamlit as st
import pandas as pd
from datetime import date

from config.settings import ORDER_STATUSES
from services.database import (
    get_all_orders, update_order, delete_order, get_order_vendor_summary,
    save_transaction, init_production_pipeline, mark_order_delivered,
    get_setting, get_order_stages,
)
from services.pdf_generator import generate_karigar_pdf
from components.image_uploader import render_image_gallery, render_image_uploader
from components.vendor_panel import render_vendor_panel


def _safe_df(all_orders):
    """Build a DataFrame from orders list with all columns guaranteed."""
    df = pd.DataFrame(all_orders)

    # String columns - add if missing, clean NaN/None
    for c in ["order_id", "customer", "phone", "item_type", "item_desc",
              "status", "gold_purity", "diamond_type", "cert_type",
              "hallmark_type", "notes", "order_date", "due_date", "vendor"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str)
        df[c] = df[c].replace("nan", "").replace("None", "")

    # Numeric columns - add if missing, coerce to float
    for c in ["gross", "net_amount", "gst", "gold_wt",
              "diamond_tcw", "diamond_pcs"]:
        if c not in df.columns:
            df[c] = 0.0
        else:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # Date columns
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["due_date"]   = pd.to_datetime(df["due_date"],   errors="coerce")

    return df


def render():
    st.markdown("# 📦 Order Management")
    st.markdown("---")

    all_orders = get_all_orders()

    if not all_orders:
        st.info("📭 No orders yet. Create an estimation first!")
        return

    df = _safe_df(all_orders)

    if df.empty:
        st.info("📭 No orders found.")
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        # key="order_search" lets other pages (e.g. Dashboard's Upcoming
        # Deadlines list) deep-link straight to an order by setting
        # st.session_state["order_search"] before switching tabs here.
        search = st.text_input("🔍 Search customer / order ID", key="order_search")
    with f2: status_filter = st.selectbox("Status", ["All", "Estimate", "── Orders ──",
                                                      "Pending", "In Progress", "Quality Check",
                                                      "Ready for Delivery", "Delivered"])
    with f3: date_from   = st.date_input("From", value=date(2024, 1, 1))
    with f4: date_to     = st.date_input("To",   value=date.today())

    fdf = df.copy()

    # Status filter — if All selected, show everything including estimates
    if status_filter not in ("All", "── Orders ──"):
        fdf = fdf[fdf["status"] == status_filter]

    if search:
        mask = (
            fdf["customer"].str.contains(search, case=False, na=False) |
            fdf["order_id"].str.contains(search, case=False, na=False)
        )
        fdf = fdf[mask]

    valid_dates = fdf["order_date"].notna()
    fdf = fdf[
        ~valid_dates |
        (
            valid_dates &
            (fdf["order_date"] >= pd.Timestamp(date_from)) &
            (fdf["order_date"] <= pd.Timestamp(date_to))
        )
    ]

    st.markdown(f"**{len(fdf)} order(s) found**")
    st.markdown("---")

    # ── Order cards ───────────────────────────────────────────────────────────
    for _, row in fdf.iterrows():
        oid = str(row["order_id"])

        is_estimate = str(row.get("status","")) == "Estimate"
        badge = "📋 ESTIMATE  " if is_estimate else "🔖 "
        # Auto-expand the card if we were deep-linked here for this exact order
        deep_linked = bool(search) and search.strip().lower() == oid.lower()
        with st.expander(
            f"{badge}{oid}  —  {row['customer']}  |  "
            f"{row['item_type']}  |  "
            f"₹{row['gross']:,.0f}  |  **{row['status']}**",
            expanded=deep_linked,
        ):
            detail_tab, vendor_tab, image_tab, action_tab = st.tabs(
                ["📋 Details", "🏭 Vendor & Costs", "🖼️ Images", "✏️ Actions"]
            )

            with detail_tab:
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    st.markdown(f"**Customer:** {row['customer']}")
                    st.markdown(f"**Phone:** {row['phone'] or '—'}")
                    st.markdown(f"**Item:** {row['item_desc'] or '—'}")
                    st.markdown(f"**Type:** {row['item_type'] or '—'}")
                with dc2:
                    od = row["order_date"]
                    dd = row["due_date"]
                    st.markdown(f"**Order Date:** {od.strftime('%d %b %Y') if pd.notna(od) else '—'}")
                    st.markdown(f"**Due Date:**   {dd.strftime('%d %b %Y') if pd.notna(dd) else '—'}")
                    st.markdown(f"**Gold:** {row['gold_purity']} · {row['gold_wt']}g")
                    st.markdown(f"**Diamond:** {row['diamond_pcs']} pcs · {row['diamond_tcw']} ct")
                with dc3:
                    st.markdown(f"**Net:** ₹{row['net_amount']:,.0f}")
                    st.markdown(f"**GST:** ₹{row['gst']:,.0f}")
                    st.markdown(f"**Gross:** ₹{row['gross']:,.0f}")
                    if row["notes"]:
                        st.markdown(f"**Notes:** {row['notes']}")

                # Vendor gold summary
                vs = get_order_vendor_summary(oid)
                if vs["gold_sent"] > 0 or vs["gold_received"] > 0 or vs["cash_paid"] > 0:
                    st.markdown("---")
                    st.markdown("**🏭 Vendor Activity**")
                    va1, va2, va3 = st.columns(3)
                    va1.metric("Gold Sent", f"{vs['gold_sent']:.3f}g")
                    va2.metric("Gold Back",  f"{vs['gold_received']:.3f}g")
                    va3.metric("Cash Paid",  f"₹{vs['cash_paid']:,.0f}")
                    if vs["net_gold"] > 0:
                        st.warning(f"⚠️ {vs['net_gold']:.3f}g gold still with vendor")
                    elif vs["goods_received"] > 0:
                        st.success("✅ Goods received from vendor")

            with vendor_tab:
                render_vendor_panel(
                    order_id   = oid,
                    vendor_name= str(row.get("vendor", "") or ""),
                    order_doc  = row.to_dict(),
                )

            with image_tab:
                st.markdown("#### Stored Images")
                render_image_gallery(row.to_dict())
                st.markdown("---")
                st.markdown("**Upload / Replace Images**")
                new_imgs = render_image_uploader(oid, key_prefix=f"ord_{oid}")
                if new_imgs:
                    if st.button("💾 Save Images", key=f"save_img_{oid}"):
                        update_order(oid, new_imgs)
                        st.success("✅ Images saved!")
                        st.rerun()

            with action_tab:
                # Convert to Order — only shown for Estimates
                if is_estimate:
                    st.markdown(
                        '<div class="estimate-badge">📋 This is an Estimate — not yet a confirmed order</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown("")
                    if st.button(
                        "✅ Convert to Order",
                        key=f"conv_{oid}",
                        use_container_width=True,
                    ):
                        update_order(oid, {"status": "Pending"})

                        # ── Start the production pipeline now that it's a real order ──
                        init_production_pipeline(oid)

                        # ── Post vendor ledger now that it's a confirmed order ──
                        vendor_name = str(row.get("vendor", "") or "")
                        if vendor_name:
                            from config.settings import GOLD_PURITY
                            from datetime import datetime as _dt

                            gold_wt     = float(row.get("gold_weight", row.get("gold_wt", 0)) or 0)
                            gold_purity = str(row.get("gold_purity", "24K (99.9%)"))
                            pf          = GOLD_PURITY.get(gold_purity, 1.0)
                            gold_base   = float(row.get("gold_price_gram", 0) or 0) / pf if pf > 0 else 0
                            gold_24k    = round(gold_wt * pf, 4)
                            today_str   = str(date.today())

                            # 1. Gold sent to vendor (24K equivalent)
                            if gold_wt > 0:
                                save_transaction(dict(
                                    party_name  = vendor_name,
                                    party_type  = "vendor",
                                    date        = today_str,
                                    mode        = "Gold (grams)",
                                    direction   = "out",
                                    cash_amount = -round(gold_24k * gold_base, 2),
                                    gold_grams  = -gold_24k,
                                    gold_rate   = gold_base,
                                    order_ref   = oid,
                                    notes       = (
                                        f"Gold sent for order {oid}: "
                                        f"{gold_wt}g {gold_purity} "
                                        f"= {gold_24k}g pure 24K"
                                    ),
                                    auto_posted = True,
                                ))

                            # 2. Cash payable to vendor
                            making   = float(row.get("making_value",        0) or 0)
                            diamonds = float(row.get("total_diamond_value", 0) or 0)
                            cert     = float(row.get("cert_cost",           0) or 0)
                            hallmark = float(row.get("hallmark_value",      0) or 0)
                            payable  = making + diamonds + cert + hallmark

                            if payable > 0:
                                save_transaction(dict(
                                    party_name  = vendor_name,
                                    party_type  = "vendor",
                                    date        = today_str,
                                    mode        = "Cash",
                                    direction   = "out",
                                    cash_amount = -round(payable, 2),
                                    gold_grams  = 0.0,
                                    gold_rate   = 0.0,
                                    order_ref   = oid,
                                    notes       = (
                                        f"Payable for order {oid}: "
                                        f"Making ₹{making:,.0f} + "
                                        f"Diamonds ₹{diamonds:,.0f} + "
                                        f"Cert/HM ₹{cert+hallmark:,.0f}"
                                    ),
                                    auto_posted = True,
                                ))

                            st.success(
                                f"✅ Estimate **{oid}** converted to Order! "
                                f"Vendor ledger updated for **{vendor_name}**."
                            )
                        else:
                            st.success(f"✅ Estimate **{oid}** converted to Order!")

                        st.rerun()
                    st.markdown("---")

                a1, a2, a3 = st.columns([2, 2, 1])
                with a1:
                    cur_idx = ORDER_STATUSES.index(row["status"]) if row["status"] in ORDER_STATUSES else 0
                    new_status = st.selectbox(
                        "Update Status", ORDER_STATUSES,
                        index=cur_idx, key=f"sel_{oid}",
                    )
                with a2:
                    if st.button("✅ Update Status", key=f"upd_{oid}", use_container_width=True):
                        update_order(oid, {"status": new_status})
                        if new_status == "Delivered":
                            mark_order_delivered(oid, "Admin")
                        st.success("Updated!")
                        st.rerun()
                with a3:
                    if st.button("🗑️ Delete", key=f"del_{oid}", use_container_width=True):
                        delete_order(oid)
                        st.warning("Deleted.")
                        st.rerun()

                # Jump straight to the Production board for this order —
                # only makes sense once it's a real order, not an Estimate.
                if not is_estimate:
                    st.markdown("---")
                    if st.button("🏭 Open Production", key=f"prod_{oid}", use_container_width=True):
                        st.session_state["production_open_order"] = oid
                        st.session_state["nav_request"] = "🏭 Production"
                        st.rerun()

                # Karigar work order — technical specs + images only, no pricing.
                st.markdown("---")
                st.markdown("**📄 Karigar Work Order**")
                st.caption("Gold/diamond specs + reference images only — no prices, no GST.")
                karigar_doc = row.to_dict()
                karigar_doc["due_date"]     = dd.strftime("%d %b %Y") if pd.notna(dd) else "—"
                karigar_doc["gold_weight"]  = row.get("gold_wt", 0)
                stage_imgs = []
                for s in get_order_stages(oid):
                    stage_imgs.extend(s.get("images", []))
                karigar_doc["stage_images"] = stage_imgs

                if st.button("📄 Generate Karigar PDF", key=f"kar_gen_{oid}", use_container_width=True):
                    business_name = get_setting("business_name", "Your Jewellery House")
                    logo_bytes    = st.session_state.get("logo_bytes")
                    pdf_bytes     = generate_karigar_pdf(karigar_doc, business_name, logo_bytes)
                    st.download_button(
                        "⬇️ Download Karigar PDF",
                        data=pdf_bytes,
                        file_name=f"karigar_{oid}.pdf",
                        mime="application/pdf",
                        key=f"kar_dl_{oid}",
                        use_container_width=True,
                    )

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown("---")
    export = fdf.drop(columns=["_id"], errors="ignore")
    st.download_button(
        "⬇️ Export CSV",
        data=export.to_csv(index=False).encode(),
        file_name="orders_export.csv",
        mime="text/csv",
    )
"""
pages/estimation.py

Full estimation builder with:
  - Multiple diamond groups (each with own shape / sieve / quality / price)
  - Vendor / supplier field
  - Google Sheet price auto-lookup per row
  - Gold, making, certificate, hallmark, GST totals
  - Save to MongoDB  |  Estimation PDF  |  Invoice PDF
"""
import streamlit as st
from datetime import datetime, date
import pandas as pd

from config.settings import (
    GOLD_PURITY, ITEM_TYPES, DIAMOND_QUALITIES,
    DIAMOND_SHAPES_DEFAULT, CERTIFICATE_TYPES, HALLMARK_TYPES, GST_RATE,
)
from services.database import (
    save_estimate, update_estimate, update_order,
    get_setting, get_all_vendors,
)
from services.diamond_sheet import get_price, get_sieve_sizes
from services.pdf_generator import generate_estimation_pdf, generate_invoice_pdf
from components.image_uploader import render_image_uploader, render_image_gallery


# ── Diamond row helpers ───────────────────────────────────────────────────────
def _default_diamond_row(label="Centre Stone"):
    return dict(
        label=label, diamond_type="Lab Diamond",
        shape="Round", quality="VVS EF",
        sieve="", wt_per_pc=0.0, pcs=1,
        price_per_ct=0.0, cost_per_ct=0.0, use_sheet=True,
    )


def _init_diamonds():
    if "diamond_rows" not in st.session_state:
        st.session_state.diamond_rows = [
            _default_diamond_row("Centre Stone"),
            _default_diamond_row("Side Diamonds"),
        ]


def _reset_to_blank():
    st.session_state.diamond_rows = [
        _default_diamond_row("Centre Stone"),
        _default_diamond_row("Side Diamonds"),
    ]
    for k in ("editing_order_id", "editing_order_data", "_loaded_edit_for", "current_order_id"):
        st.session_state.pop(k, None)


def _parse_date(value, fallback):
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return fallback


def _enter_edit_mode(order_id: str, data: dict):
    """
    Loads an existing order's data into the builder — including every
    diamond group — so it can all be edited in place. Guarded by
    _loaded_edit_for so this only runs once per order, not on every rerun
    (otherwise it would keep clobbering in-progress edits).
    """
    # Diamond row widgets (and the gold cost field) carry their own keys,
    # so leftover values from an earlier New Estimation session in this
    # same browser tab would silently override the loaded order's data.
    # Clear them first so the widgets re-initialize from `data` below.
    for k in list(st.session_state.keys()):
        if k.startswith("d_") or k == "gold_cost_gram":
            del st.session_state[k]

    st.session_state.diamond_rows = data.get("diamond_rows") or [
        _default_diamond_row("Centre Stone"),
        _default_diamond_row("Side Diamonds"),
    ]
    st.session_state.current_order_id  = order_id
    st.session_state["_loaded_edit_for"] = order_id


def _render_diamond_rows(shape_dfs, diamond_base):
    rows       = st.session_state.diamond_rows
    computed   = []
    shape_opts = list(shape_dfs.keys()) if shape_dfs else DIAMOND_SHAPES_DEFAULT

    for i, row in enumerate(rows):
        st.markdown(f"##### 💎 Diamond Group {i + 1}")
        r1, r2, r3, r4, r5 = st.columns([2, 2, 2, 2, 1])

        with r1:
            row["label"] = st.text_input("Label", value=row["label"], key=f"d_label_{i}")
        with r2:
            row["diamond_type"] = st.radio(
                "Type", ["Lab", "Natural"],
                index=0 if "Lab" in row["diamond_type"] else 1,
                key=f"d_type_{i}", horizontal=True,
            )
        with r3:
            idx = shape_opts.index(row["shape"]) if row["shape"] in shape_opts else 0
            row["shape"] = st.selectbox("Shape", shape_opts, index=idx, key=f"d_shape_{i}")
        with r4:
            idx = DIAMOND_QUALITIES.index(row["quality"]) if row["quality"] in DIAMOND_QUALITIES else 0
            row["quality"] = st.selectbox("Quality", DIAMOND_QUALITIES, index=idx, key=f"d_quality_{i}")
        with r5:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🗑️", key=f"d_del_{i}"):
                st.session_state.diamond_rows.pop(i)
                st.rerun()

        r6, r7, r8, r9, r10 = st.columns(5)
        sieve_opts = get_sieve_sizes(shape_dfs, row["shape"]) if shape_dfs else []
        with r6:
            if sieve_opts:
                idx = sieve_opts.index(row["sieve"]) if row["sieve"] in sieve_opts else 0
                row["sieve"] = st.selectbox("Sieve", sieve_opts, index=idx, key=f"d_sieve_{i}")
            else:
                row["sieve"] = st.text_input("Sieve", value=row["sieve"], key=f"d_sieve_{i}")
        with r7:
            row["wt_per_pc"] = st.number_input("Wt/pc (ct)", value=float(row["wt_per_pc"]),
                                                min_value=0.0, step=0.001, format="%.3f", key=f"d_wt_{i}")
        with r8:
            row["pcs"] = st.number_input("PCS", value=int(row["pcs"]), min_value=0, step=1, key=f"d_pcs_{i}")

        sheet_price = None
        if shape_dfs and row["sieve"] and row["quality"] != "Custom":
            sheet_price = get_price(shape_dfs, row["shape"], row["sieve"], row["quality"])

        with r9:
            st.metric("Sheet ₹/ct", f"₹{sheet_price:,.0f}" if sheet_price else "—")
            if sheet_price:
                row["use_sheet"] = st.checkbox("Use sheet", value=row.get("use_sheet", True), key=f"d_us_{i}")
            else:
                row["use_sheet"] = False

        with r10:
            if row["use_sheet"] and sheet_price:
                price_per_ct = sheet_price
                st.markdown('<span class="price-badge-sheet">📊 Sheet</span>', unsafe_allow_html=True)
                st.markdown(f"**₹{price_per_ct:,.0f}/ct**")
            else:
                price_per_ct = st.number_input(
                    "₹/ct manual",
                    value=float(sheet_price or row["price_per_ct"] or diamond_base),
                    step=100.0, key=f"d_price_{i}",
                )
                st.markdown('<span class="price-badge-manual">✏️ Manual</span>', unsafe_allow_html=True)
            row["price_per_ct"] = price_per_ct

        tcw   = round(row["wt_per_pc"] * row["pcs"], 4)
        value = round(tcw * price_per_ct, 0)

        cost_per_ct = st.number_input(
            "Cost ₹/ct (vendor)",
            value=float(row.get("cost_per_ct", 0.0)),
            step=100.0, key=f"d_cost_{i}",
        )
        row["cost_per_ct"] = cost_per_ct
        cost_value = round(tcw * cost_per_ct, 0)

        sv1, sv2, sv3, sv4 = st.columns(4)
        sv1.metric("TCW", f"{tcw:.4f} ct")
        sv2.metric("Sell Value", f"₹ {value:,.0f}")
        sv3.metric("Cost Value", f"₹ {cost_value:,.0f}")
        sv4.metric("Margin", f"₹ {value - cost_value:,.0f}")

        if shape_dfs and not sheet_price and row["sieve"] and row["quality"] != "Custom":
            st.warning(f"⚠️ No sheet price for {row['shape']} / {row['sieve']} / {row['quality']}.")

        computed.append({
            "label": row["label"], "diamond_type": row["diamond_type"],
            "shape": row["shape"], "quality": row["quality"],
            "sieve": row["sieve"], "wt_per_pc": row["wt_per_pc"],
            "pcs": int(row["pcs"]), "price_per_ct": price_per_ct,
            "cost_per_ct": cost_per_ct,
            "tcw": tcw, "value": value, "cost_value": cost_value,
        })
        st.markdown("---")

    return computed


# ── Main ──────────────────────────────────────────────────────────────────────
def render(gold_base, diamond_base, shape_dfs):
    editing_order_id = st.session_state.get("editing_order_id")
    ed = st.session_state.get("editing_order_data") or {} if editing_order_id else {}

    if editing_order_id and st.session_state.get("_loaded_edit_for") != editing_order_id:
        _enter_edit_mode(editing_order_id, ed)

    if editing_order_id:
        title_col, cancel_col = st.columns([4, 1])
        with title_col:
            st.markdown(f"# ✏️ Edit Order — {editing_order_id}")
        with cancel_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("❌ Cancel Edit", use_container_width=True):
                _reset_to_blank()
                st.rerun()
    else:
        st.markdown("# 📋 New Estimation")
    st.markdown("---")

    _init_diamonds()

    if "current_order_id" not in st.session_state:
        st.session_state.current_order_id = f"ORD-{datetime.now().strftime('%y%m%d%H%M%S')}"

    tab_est, tab_images = st.tabs(["📝 Estimation Details", "🖼️ Upload Images"])

    with tab_est:

        # ── Customer & Order ──────────────────────────────────────────────────
        st.markdown('<div class="gold-header">👤 Customer & Order Info</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        with c1: customer  = st.text_input("Customer Name *", value=ed.get("customer", ""))
        with c2: phone     = st.text_input("Phone", value=ed.get("phone", ""))
        with c3:
            order_id = st.text_input(
                "Order ID", value=st.session_state.current_order_id,
                disabled=bool(editing_order_id),
            )
        with c4:
            it_idx = ITEM_TYPES.index(ed["item_type"]) if ed.get("item_type") in ITEM_TYPES else 0
            item_type = st.selectbox("Item Type", ITEM_TYPES, index=it_idx)

        # A quote has a date, but not a delivery promise — the due date is set
        # when the estimate is converted into a real order. This builder is
        # also the editor for confirmed orders though, so keep the field there
        # or editing an order would wipe the date it was promised on.
        editing_confirmed_order = bool(editing_order_id) and str(ed.get("status", "")) != "Estimate"

        if editing_confirmed_order:
            d1, d2, d3 = st.columns(3)
            with d2:
                due_date = st.date_input("Due Date", value=_parse_date(ed.get("due_date"), date.today()))
        else:
            d1, d3 = st.columns(2)
            due_date = None

        with d1: order_date = st.date_input("Order Date", value=_parse_date(ed.get("order_date"), date.today()))
        with d3: item_desc  = st.text_input("Item Description", value=ed.get("item_desc", ""), placeholder="e.g. SOL-001 Solitaire Ring")

        if not editing_confirmed_order:
            st.caption("📅 The delivery due date is set when you convert this estimate into an order.")

        # Vendor row
        st.markdown('<div class="gold-header">🏭 Vendor / Supplier</div>', unsafe_allow_html=True)
        vendors      = get_all_vendors()
        vendor_names = ["— None —"] + [v["name"] for v in vendors]
        vn_idx = vendor_names.index(ed["vendor"]) if ed.get("vendor") in vendor_names else 0
        vn1, vn2 = st.columns(2)
        with vn1:
            vendor_name = st.selectbox("Assign Vendor / Supplier", vendor_names, index=vn_idx)
            vendor_name = "" if vendor_name == "— None —" else vendor_name
        with vn2:
            vendor_notes = st.text_input("Vendor Notes", value=ed.get("vendor_notes", ""), placeholder="e.g. sent for making on 10 Mar")

        st.markdown("---")

        # ── Gold ─────────────────────────────────────────────────────────────
        st.markdown('<div class="gold-header">🥇 Gold Details</div>', unsafe_allow_html=True)
        g1, g2, g3, g4, g5, g6, g7 = st.columns(7)
        with g1:
            purity_opts = list(GOLD_PURITY.keys())
            p_idx = purity_opts.index(ed["gold_purity"]) if ed.get("gold_purity") in purity_opts else 0
            gold_purity_label = st.selectbox("Purity", purity_opts, index=p_idx)
        with g2:
            color_opts = ["Yellow Gold", "White Gold", "Rose Gold"]
            c_idx = color_opts.index(ed["gold_color"]) if ed.get("gold_color") in color_opts else 0
            gold_color = st.selectbox("Colour", color_opts, index=c_idx)
        pf   = GOLD_PURITY[gold_purity_label]
        gppg = round(gold_base * pf, 2)
        with g3: st.metric("Sell Rate/gram", f"₹ {gppg:,.2f}")
        with g4:
            default_cost_gram = float(ed.get("gold_cost_per_gram", gppg))
            gold_cost_per_gram = st.number_input("Cost Rate/gram (vendor)", value=default_cost_gram, step=10.0, key="gold_cost_gram")
        with g5: gold_weight = st.number_input("Weight (grams)", min_value=0.0, value=float(ed.get("gold_weight", 5.500)), step=0.001, format="%.3f")
        gold_value      = round(gppg * gold_weight, 0)
        gold_cost_value = round(gold_cost_per_gram * gold_weight, 0)
        with g6: st.metric("Sell Value", f"₹ {gold_value:,.0f}")
        with g7: st.metric("Cost Value", f"₹ {gold_cost_value:,.0f}")
        st.markdown("---")

        # ── Diamonds ─────────────────────────────────────────────────────────
        st.markdown('<div class="gold-header">💎 Diamond Details</div>', unsafe_allow_html=True)
        diamond_rows = _render_diamond_rows(shape_dfs, diamond_base)

        col_add, col_summary = st.columns([1, 3])
        with col_add:
            if st.button("➕ Add Diamond Group", use_container_width=True):
                st.session_state.diamond_rows.append(
                    _default_diamond_row(f"Group {len(st.session_state.diamond_rows) + 1}")
                )
                st.rerun()

        total_diamond_value = sum(r["value"] for r in diamond_rows)
        total_tcw           = sum(r["tcw"]   for r in diamond_rows)
        total_pcs           = sum(r["pcs"]   for r in diamond_rows)

        with col_summary:
            if diamond_rows:
                st.dataframe(pd.DataFrame([{
                    "Group":   r["label"],  "Shape": r["shape"],
                    "Sieve":   r["sieve"],  "Quality": r["quality"],
                    "PCS":     r["pcs"],    "TCW": f"{r['tcw']:.4f}ct",
                    "₹/ct":   f"₹{r['price_per_ct']:,.0f}",
                    "Value":   f"₹{r['value']:,.0f}",
                } for r in diamond_rows]), use_container_width=True, hide_index=True)

        sv1, sv2, sv3 = st.columns(3)
        sv1.metric("Total Diamond Value", f"₹ {total_diamond_value:,.0f}")
        sv2.metric("Total Carat Weight",  f"{total_tcw:.4f} ct")
        sv3.metric("Total Stones",        f"{total_pcs} pcs")
        st.markdown("---")

        # ── Making ────────────────────────────────────────────────────────────
        st.markdown('<div class="gold-header">🔨 Making Charges</div>', unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1: making_per_gram = st.number_input("Sell Making ₹/gram", value=float(ed.get("making_per_gram", 1500.0)), step=10.0)
        with m2: making_cost_per_gram = st.number_input("Cost Making ₹/gram (karigar)", value=float(ed.get("making_cost_per_gram", 1000.0)), step=10.0)
        making_value      = round(making_per_gram      * gold_weight, 0)
        making_cost_value = round(making_cost_per_gram * gold_weight, 0)
        m3.metric("Gold Weight",   f"{gold_weight:.3f} g")
        m4.metric("Sell Making",   f"₹ {making_value:,.0f}")
        m5.metric("Cost Making",   f"₹ {making_cost_value:,.0f}")
        st.markdown("---")

        # ── Certificate & Hallmark ────────────────────────────────────────────
        st.markdown('<div class="gold-header">📜 Certificate & Hallmark</div>', unsafe_allow_html=True)
        h1, h2, h3, h4, h5, h6, h7, h8 = st.columns(8)
        with h1:
            ct_idx = CERTIFICATE_TYPES.index(ed["cert_type"]) if ed.get("cert_type") in CERTIFICATE_TYPES else 0
            cert_type          = st.selectbox("Certificate",       CERTIFICATE_TYPES, index=ct_idx)
        with h2: cert_cost          = st.number_input("Cert Sell ₹",    value=float(ed.get("cert_cost", 0.0)),  step=100.0)
        with h3: cert_actual_cost   = st.number_input("Cert Actual ₹",  value=float(ed.get("cert_actual_cost", 0.0)),  step=100.0)
        with h4:
            ht_idx = HALLMARK_TYPES.index(ed["hallmark_type"]) if ed.get("hallmark_type") in HALLMARK_TYPES else 0
            hallmark_type      = st.selectbox("Hallmark",          HALLMARK_TYPES, index=ht_idx)
        with h5: hallmark_per       = st.number_input("Sell ₹/article", value=55.0, step=5.0)
        with h6: hallmark_cost_per  = st.number_input("Cost ₹/article", value=float(ed.get("hallmark_cost_per", 45.0)), step=5.0)
        with h7: hallmark_arts      = st.number_input("Articles",        value=2,    step=1, min_value=0)
        hallmark_value      = round(hallmark_per      * hallmark_arts, 0)
        hallmark_cost_value = round(hallmark_cost_per * hallmark_arts, 0)
        with h8: st.metric("HM Sell / Cost", f"₹{hallmark_value:,.0f} / ₹{hallmark_cost_value:,.0f}")
        if editing_order_id:
            st.caption("ℹ️ Hallmark Sell ₹/article and Articles count aren't stored on the order, so they reset to defaults here — only the final Hallmark value/cost carried over. Re-enter them if they differ.")
        st.markdown("---")

        # ── Totals ────────────────────────────────────────────────────────────
        net_amount        = gold_value + total_diamond_value + making_value + cert_cost + hallmark_value
        gst_amount        = round(net_amount * GST_RATE, 0)
        gross_amount      = net_amount + gst_amount
        # Cost totals (what you pay vendors/karigars)
        total_diamond_cost = sum(r.get("cost_value", 0) for r in diamond_rows)
        total_cost        = gold_cost_value + total_diamond_cost + making_cost_value + cert_actual_cost + hallmark_cost_value
        total_profit      = net_amount - total_cost
        profit_pct        = round((total_profit / net_amount * 100), 1) if net_amount > 0 else 0

        st.markdown(f"""
        <div class="total-box">
            <p>Gold ₹{gold_value:,.0f} &nbsp;+&nbsp; Diamonds ₹{total_diamond_value:,.0f}
               &nbsp;+&nbsp; Making ₹{making_value:,.0f}
               &nbsp;+&nbsp; Others ₹{cert_cost + hallmark_value:,.0f}</p>
            <p>Net ₹{net_amount:,.0f} &nbsp;|&nbsp; GST {GST_RATE * 100:g}% ₹{gst_amount:,.0f}</p>
            <h1>₹ {gross_amount:,.0f}</h1>
            <p>Gross Amount (incl. GST) · <i>Estimated — may vary on final CAD</i></p>
        </div>
        """, unsafe_allow_html=True)

        # Profit summary
        profit_clr = "#27ae60" if total_profit >= 0 else "#c0392b"
        pc1, pc2, pc3, pc4 = st.columns(4)
        pc1.metric("Total Cost",   f"₹ {total_cost:,.0f}")
        pc2.metric("Net Revenue",  f"₹ {net_amount:,.0f}")
        pc3.metric("Gross Profit", f"₹ {total_profit:,.0f}")
        pc4.metric("Margin %",     f"{profit_pct}%")

        st.markdown("---")
        notes = st.text_area("Notes / Remarks", value=ed.get("notes", ""))

    with tab_images:
        st.markdown("### 🖼️ Upload Images")
        st.caption("Item photo · Customer reference · CAD design — stored on Cloudinary.")
        if editing_order_id and any(ed.get(k) for k in ("item_image", "customer_image", "cad_image")):
            st.markdown("**Currently Saved**")
            render_image_gallery(ed)
            st.markdown("---")
            st.markdown("**Upload to Replace**")
        st.markdown("---")
        new_imgs = render_image_uploader(order_id, key_prefix="new_est")
        if new_imgs:
            existing = st.session_state.get("pending_images", {})
            existing.update(new_imgs)
            st.session_state["pending_images"] = existing

    # ── Actions ───────────────────────────────────────────────────────────────
    st.markdown("---")

    estimation = dict(
        order_id=order_id, customer=customer, phone=phone,
        item_desc=item_desc, item_type=item_type,
        order_date=str(order_date),
        vendor=vendor_name, vendor_notes=vendor_notes,
        # Selling prices
        gold_purity=gold_purity_label, gold_color=gold_color, gold_weight=gold_weight,
        gold_price_gram=gppg, gold_value=gold_value,
        diamond_rows=diamond_rows,
        total_diamond_value=total_diamond_value,
        total_tcw=total_tcw, total_pcs=total_pcs,
        making_per_gram=making_per_gram, making_value=making_value,
        cert_type=cert_type, cert_cost=cert_cost,
        hallmark_type=hallmark_type, hallmark_value=hallmark_value,
        net_amount=net_amount, gst_amount=gst_amount, gross_amount=gross_amount,
        # Cost prices (what you actually pay)
        gold_cost_per_gram=gold_cost_per_gram, gold_cost_value=gold_cost_value,
        total_diamond_cost=total_diamond_cost,
        making_cost_per_gram=making_cost_per_gram, making_cost_value=making_cost_value,
        cert_actual_cost=cert_actual_cost,
        hallmark_cost_per=hallmark_cost_per, hallmark_cost_value=hallmark_cost_value,
        total_cost=total_cost, total_profit=total_profit, profit_pct=profit_pct,
        notes=notes,
    )

    # Only confirmed orders carry a due date; leaving the key out entirely
    # means saving an estimate can't write a placeholder, and updating an
    # order can't blank the real one.
    if due_date is not None:
        estimation["due_date"] = str(due_date)

    b1, b2, b3 = st.columns(3)

    with b1:
        if editing_order_id:
            if st.button("💾 Update Order", use_container_width=True):
                if not customer.strip():
                    st.error("Please enter customer name.")
                else:
                    img_data = st.session_state.pop("pending_images", {})
                    doc = {
                        **estimation,
                        "order_id":       editing_order_id,  # never changes on edit
                        "item_image":     img_data.get("item_image")     or ed.get("item_image", ""),
                        "customer_image": img_data.get("customer_image") or ed.get("customer_image", ""),
                        "cad_image":      img_data.get("cad_image")      or ed.get("cad_image", ""),
                    }
                    # Estimates and orders live in different collections, so
                    # the edit has to go back where it came from. Status is
                    # left untouched — editing details shouldn't silently
                    # revert a confirmed order back to "Estimate".
                    if str(ed.get("status", "")) == "Estimate":
                        update_estimate(editing_order_id, doc)
                    else:
                        update_order(editing_order_id, doc)

                    _reset_to_blank()
                    st.session_state["order_search"] = editing_order_id
                    st.session_state["nav_request"]  = "📦 Orders"
                    st.success(f"✅ Order **{editing_order_id}** updated!")
                    st.rerun()
        else:
            if st.button("💾 Save as Estimate", use_container_width=True):
                if not customer.strip():
                    st.error("Please enter customer name.")
                else:
                    img_data = st.session_state.pop("pending_images", {})
                    doc = {
                        **estimation, "status": "Estimate",
                        "item_image":     img_data.get("item_image", ""),
                        "customer_image": img_data.get("customer_image", ""),
                        "cad_image":      img_data.get("cad_image", ""),
                    }
                    # Goes to the `estimates` collection — an estimate is only
                    # a quote. It stays out of orders, revenue, production and
                    # the vendor ledger until it's converted to an Order.
                    save_estimate(doc)

                    del st.session_state["current_order_id"]
                    st.session_state.diamond_rows = [
                        _default_diamond_row("Centre Stone"),
                        _default_diamond_row("Side Diamonds"),
                    ]
                    st.success(
                        f"✅ Estimate **{order_id}** saved! "
                        f"Nothing is committed yet — production and the vendor "
                        f"ledger start when you convert it to an Order."
                    )

    with b2:
        if st.button("📄 Estimation PDF", use_container_width=True):
            bname      = get_setting("business_name", "Your Jewellery House")
            logo_bytes = st.session_state.get("logo_bytes")
            try:
                pdf = generate_estimation_pdf(estimation, bname, logo_bytes)
                st.download_button("⬇️ Download Estimation", data=pdf,
                                   file_name=f"Estimation_{order_id}.pdf",
                                   mime="application/pdf", use_container_width=True)
            except Exception as ex:
                st.error(f"PDF error: {ex}")

    with b3:
        if st.button("🧾 Invoice PDF", use_container_width=True):
            bname      = get_setting("business_name", "Your Jewellery House")
            logo_bytes = st.session_state.get("logo_bytes")
            try:
                pdf = generate_invoice_pdf(estimation, bname, logo_bytes)
                st.download_button("⬇️ Download Invoice", data=pdf,
                                   file_name=f"Invoice_{order_id}.pdf",
                                   mime="application/pdf", use_container_width=True)
            except Exception as ex:
                st.error(f"Invoice error: {ex}")
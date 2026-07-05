"""
pages/finance.py

Tabs:
  1. Add Transaction       - standalone customer/vendor ledger entry
  2. Order Vendor Tracker  - gold sent/received + cash paid per order
  3. Customer Ledger       - who owes me
  4. Supplier Ledger       - who I owe
  5. Cash Flow             - summary + charts
  6. P&L per Order         - billed vs received
  7. Manage Vendors        - vendor master
"""
import streamlit as st
import pandas as pd
from datetime import date

from services.database import (
    get_all_vendors, save_vendor, delete_vendor,
    get_transactions, save_transaction, delete_transaction,
    get_party_balance, get_all_orders,
    get_order_vendor_txns, save_order_vendor_txn,
    delete_order_vendor_txn, get_order_vendor_summary,
)

PAYMENT_MODES = ["Cash", "Gold (grams)", "Bank Transfer", "UPI"]

ORDER_VENDOR_TYPES = {
    "gold_sent":      "🥇 Gold Sent to Vendor for Making",
    "cash_paid":      "💵 Cash Paid to Vendor",
    "gold_received":  "🔄 Gold Received Back from Vendor",
    "goods_received": "📦 Finished Goods Received from Vendor",
}


def _safe_float(val, default=0.0):
    try:
        return float(val or default)
    except Exception:
        return default


def _txn_df(txns):
    if not txns:
        return pd.DataFrame()
    df = pd.DataFrame(txns)
    for c in ["party_name","party_type","mode","direction","notes","order_ref","date"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).replace("nan","").replace("None","")
    for c in ["cash_amount","gold_grams","gold_rate"]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def render(gold_base):
    st.markdown("# 💰 Finance & Ledger")
    st.markdown("---")

    (tab_txn, tab_order_vendor, tab_customer,
     tab_vendor, tab_cash, tab_pnl, tab_vendors) = st.tabs([
        "📝 Add Transaction",
        "🔗 Order Vendor Tracker",
        "👤 Customer Ledger",
        "🏭 Supplier Ledger",
        "💵 Cash Flow",
        "📊 P&L per Order",
        "🏭 Manage Vendors",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — Add Transaction (standalone ledger)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_txn:
        st.markdown('<div class="gold-header">📝 New Ledger Entry</div>',
                    unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            party_type = st.radio("Party Type", ["Customer","Vendor / Supplier"],
                                  horizontal=True, key="txn_pt")
            pt = "customer" if party_type == "Customer" else "vendor"

            vendors      = get_all_vendors()
            vendor_names = [v["name"] for v in vendors]
            if pt == "vendor" and vendor_names:
                party_name = st.selectbox("Select Vendor", vendor_names, key="txn_vsel")
            else:
                party_name = st.text_input(
                    "Customer Name" if pt == "customer" else "Vendor Name",
                    key="txn_pname")

            txn_date  = st.date_input("Date", value=date.today(), key="txn_date")
            order_ref = st.text_input("Order Ref (optional)", key="txn_oref")

        with col2:
            direction     = st.radio(
                "Direction",
                ["Received (IN ↓)","Paid / Given (OUT ↑)"],
                key="txn_dir")
            direction_key = "in" if "Received" in direction else "out"
            mode          = st.selectbox("Payment Mode", PAYMENT_MODES, key="txn_mode")

            cash_amount = gold_grams = gold_rate = gold_value = 0.0
            if mode == "Gold (grams)":
                gc1, gc2 = st.columns(2)
                with gc1:
                    gold_grams = st.number_input("Gold Grams", min_value=0.0,
                                                  step=0.001, format="%.3f", key="txn_gg")
                with gc2:
                    gold_rate = st.number_input("Rate ₹/g 24K",
                                                 value=gold_base, step=10.0, key="txn_gr")
                gold_value  = round(gold_grams * gold_rate, 0)
                cash_amount = gold_value
                st.metric("Cash Equivalent", f"₹ {gold_value:,.0f}")
            else:
                cash_amount = st.number_input("Amount ₹", min_value=0.0,
                                               step=100.0, key="txn_ca")

            notes = st.text_area("Notes", key="txn_notes")

        sign        = 1 if direction_key == "in" else -1
        signed_cash = round(sign * cash_amount, 2)
        signed_gold = round(sign * gold_grams, 4)

        st.markdown("---")
        lbl = "received from" if direction_key == "in" else "paid to"
        if mode == "Gold (grams)":
            st.info(f"Recording **{abs(gold_grams):.3f}g gold** {lbl} **{party_name or '…'}** "
                    f"@ ₹{gold_rate:,.0f}/g = **₹{gold_value:,.0f}**")
        else:
            st.info(f"Recording **₹{abs(cash_amount):,.0f}** {lbl} **{party_name or '…'}**")

        if st.button("💾 Save Transaction", use_container_width=True, key="save_txn"):
            if not party_name.strip():
                st.error("Enter party name.")
            else:
                save_transaction(dict(
                    party_name=party_name.strip(), party_type=pt,
                    date=str(txn_date), mode=mode, direction=direction_key,
                    cash_amount=signed_cash,
                    gold_grams=signed_gold if mode == "Gold (grams)" else 0.0,
                    gold_rate=gold_rate if mode == "Gold (grams)" else 0.0,
                    order_ref=order_ref.strip(), notes=notes.strip(),
                ))
                st.success(f"✅ Saved for **{party_name}**!")

        # Recent
        st.markdown("---")
        st.markdown("### 🕐 Recent Transactions")
        recent = get_transactions()
        if recent:
            rdf = _txn_df(recent).head(20)
            show = [c for c in ["date","party_name","party_type","mode",
                                  "cash_amount","gold_grams","order_ref","notes"]
                    if c in rdf.columns]
            rshow = rdf[show].copy()
            rshow["date"]        = rshow["date"].dt.strftime("%d %b %Y")
            rshow["cash_amount"] = rshow["cash_amount"].apply(lambda x: f"₹ {x:+,.0f}")
            rshow["gold_grams"]  = rshow["gold_grams"].apply(
                lambda x: f"{x:+.3f}g" if x != 0 else "—")
            st.dataframe(rshow, use_container_width=True, hide_index=True)

            with st.expander("🗑️ Delete a Transaction"):
                del_ids = {
                    f"{t.get('date','')} | {t.get('party_name','')} | "
                    f"₹{_safe_float(t.get('cash_amount',0)):+,.0f}": t["_id"]
                    for t in recent
                }
                sel = st.selectbox("Select", list(del_ids.keys()), key="del_txn_sel")
                if st.button("🗑️ Delete", key="del_txn_btn"):
                    delete_transaction(del_ids[sel])
                    st.warning("Deleted.")
                    st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — Order Vendor Tracker
    # ══════════════════════════════════════════════════════════════════════════
    with tab_order_vendor:
        st.markdown("### 🔗 Order Vendor Tracker")
        st.caption("Track gold sent/received and cash paid to vendor per order.")

        orders       = get_all_orders()
        vendors      = get_all_vendors()
        vendor_names = [v["name"] for v in vendors]

        if not orders:
            st.info("No orders yet.")
        else:
            # Pick order
            order_ids   = [o["order_id"] for o in orders]
            order_labels = [
                f"{o['order_id']} — {o.get('customer','')} | {o.get('item_type','')}"
                for o in orders
            ]
            sel_idx = st.selectbox("Select Order", range(len(order_labels)),
                                   format_func=lambda i: order_labels[i],
                                   key="ovt_order_sel")
            sel_order = orders[sel_idx]
            oid       = sel_order["order_id"]

            # Summary cards
            summary = get_order_vendor_summary(oid)
            st.markdown("---")
            st.markdown(f"#### Order: **{oid}** — {sel_order.get('customer','')} — {sel_order.get('item_type','')}")
            if sel_order.get("vendor"):
                st.caption(f"Assigned vendor: **{sel_order['vendor']}**")

            k1, k2, k3, k4 = st.columns(4)
            k1.markdown(
                f'<div class="metric-card" style="border-left-color:#c0392b">'
                f'<h3>Gold Sent Out</h3>'
                f'<h2 style="color:#c0392b">{summary["gold_sent"]:.3f}g</h2></div>',
                unsafe_allow_html=True)
            k2.markdown(
                f'<div class="metric-card" style="border-left-color:#27ae60">'
                f'<h3>Gold Received Back</h3>'
                f'<h2 style="color:#27ae60">{summary["gold_received"]:.3f}g</h2></div>',
                unsafe_allow_html=True)
            k3.markdown(
                f'<div class="metric-card" style="border-left-color:#d4a843">'
                f'<h3>Net Gold with Vendor</h3>'
                f'<h2 style="color:#d4a843">{summary["net_gold"]:.3f}g</h2></div>',
                unsafe_allow_html=True)
            k4.markdown(
                f'<div class="metric-card" style="border-left-color:#004085">'
                f'<h3>Cash Paid to Vendor</h3>'
                f'<h2 style="color:#004085">₹ {summary["cash_paid"]:,.0f}</h2></div>',
                unsafe_allow_html=True)

            st.markdown("---")

            # Add new vendor transaction for this order
            st.markdown("#### ➕ Add Vendor Transaction for this Order")
            fa, fb = st.columns(2)
            with fa:
                if vendor_names:
                    txn_vendor = st.selectbox("Vendor", vendor_names, key="ovt_vendor")
                else:
                    txn_vendor = st.text_input("Vendor Name", key="ovt_vendor_txt")

                txn_type = st.selectbox(
                    "Transaction Type",
                    list(ORDER_VENDOR_TYPES.keys()),
                    format_func=lambda k: ORDER_VENDOR_TYPES[k],
                    key="ovt_type"
                )
                txn_date = st.date_input("Date", value=date.today(), key="ovt_date")

            with fb:
                gold_grams = cash_amount = gold_rate = 0.0

                if txn_type in ("gold_sent", "gold_received"):
                    gold_grams = st.number_input(
                        "Gold Weight (grams)", min_value=0.0,
                        step=0.001, format="%.3f", key="ovt_gg")
                    gold_rate = st.number_input(
                        "Gold Rate ₹/g (24K)", value=gold_base,
                        step=10.0, key="ovt_gr")
                    gold_value = round(gold_grams * gold_rate, 0)
                    st.metric("Cash Equivalent", f"₹ {gold_value:,.0f}")

                elif txn_type == "cash_paid":
                    cash_amount = st.number_input(
                        "Amount ₹", min_value=0.0, step=100.0, key="ovt_ca")

                elif txn_type == "goods_received":
                    st.info("📦 This marks goods as received back from vendor.")

                ovt_notes = st.text_area("Notes", key="ovt_notes",
                                          placeholder="e.g. Sent for rhodium plating")

            if st.button("💾 Save Vendor Transaction", use_container_width=True, key="save_ovt"):
                if not txn_vendor:
                    st.error("Select a vendor.")
                else:
                    doc = dict(
                        order_id    = oid,
                        vendor_name = txn_vendor,
                        txn_type    = txn_type,
                        date        = str(txn_date),
                        gold_grams  = gold_grams  if txn_type in ("gold_sent","gold_received") else 0.0,
                        gold_rate   = gold_rate   if txn_type in ("gold_sent","gold_received") else 0.0,
                        cash_amount = cash_amount if txn_type == "cash_paid" else 0.0,
                        notes       = ovt_notes.strip(),
                    )
                    save_order_vendor_txn(doc)
                    st.success("✅ Vendor transaction saved!")
                    st.rerun()

            # Transaction history for this order
            st.markdown("---")
            st.markdown("#### 📋 Vendor Transaction History")
            ovt_list = get_order_vendor_txns(oid)
            if not ovt_list:
                st.caption("No vendor transactions recorded for this order yet.")
            else:
                rows = []
                for t in ovt_list:
                    rows.append({
                        "Date":        t.get("date",""),
                        "Vendor":      t.get("vendor_name",""),
                        "Type":        ORDER_VENDOR_TYPES.get(t.get("txn_type",""), t.get("txn_type","")),
                        "Gold (g)":    f"{_safe_float(t.get('gold_grams',0)):+.3f}g"
                                       if t.get("gold_grams",0) else "—",
                        "Rate ₹/g":   f"₹{_safe_float(t.get('gold_rate',0)):,.0f}"
                                       if t.get("gold_rate",0) else "—",
                        "Cash":        f"₹{_safe_float(t.get('cash_amount',0)):,.0f}"
                                       if t.get("cash_amount",0) else "—",
                        "Notes":       t.get("notes",""),
                    })
                hist_df = pd.DataFrame(rows)
                st.dataframe(hist_df, use_container_width=True, hide_index=True)

                with st.expander("🗑️ Delete a record"):
                    del_map = {
                        f"{t.get('date','')} | {ORDER_VENDOR_TYPES.get(t.get('txn_type',''),'')} | "
                        f"{t.get('vendor_name','')}": t["_id"]
                        for t in ovt_list
                    }
                    sel_del = st.selectbox("Select", list(del_map.keys()), key="ovt_del_sel")
                    if st.button("🗑️ Delete", key="ovt_del_btn"):
                        delete_order_vendor_txn(del_map[sel_del])
                        st.warning("Deleted.")
                        st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — Customer Ledger
    # ══════════════════════════════════════════════════════════════════════════
    with tab_customer:
        st.markdown("### 👤 Customer Ledger")
        st.caption("Positive balance = customer still owes you money.")

        txns = get_transactions({"party_type": "customer"})
        if not txns:
            st.info("No customer transactions yet.")
        else:
            df = _txn_df(txns)
            summary = (df.groupby("party_name")
                         .agg(total_cash=("cash_amount","sum"),
                              total_gold=("gold_grams","sum"),
                              txn_count=("cash_amount","count"))
                         .reset_index())

            orders = get_all_orders()
            order_totals = {}
            if orders:
                odf = pd.DataFrame(orders)
                if "customer" in odf.columns and "gross" in odf.columns:
                    odf["gross"] = pd.to_numeric(odf["gross"], errors="coerce").fillna(0)
                    order_totals = odf.groupby("customer")["gross"].sum().to_dict()

            for _, row in summary.iterrows():
                name      = row["party_name"]
                paid      = _safe_float(row["total_cash"])
                total_due = _safe_float(order_totals.get(name, 0))
                balance   = total_due - paid
                gold_bal  = _safe_float(row["total_gold"])
                clr = "#c0392b" if balance > 0 else "#27ae60"
                st.markdown(
                    f'<div class="metric-card" style="border-left-color:{clr}">'
                    f'<h3>{name}</h3>'
                    f'<h2 style="color:{clr}">₹ {balance:,.0f} due</h2>'
                    f'<p style="color:#888;font-size:12px">'
                    f'Billed: ₹{total_due:,.0f} &nbsp;|&nbsp; Received: ₹{paid:,.0f}'
                    f' &nbsp;|&nbsp; Gold: {gold_bal:.3f}g</p></div>',
                    unsafe_allow_html=True)

            st.markdown("---")
            cust_list = df["party_name"].unique().tolist()
            sel_c = st.selectbox("Filter", ["All"] + cust_list, key="cust_flt")
            cdf   = df if sel_c == "All" else df[df["party_name"] == sel_c]
            cs    = cdf[["date","party_name","mode","cash_amount","gold_grams",
                          "order_ref","notes"]].copy()
            cs["date"]        = cs["date"].dt.strftime("%d %b %Y")
            cs["cash_amount"] = cs["cash_amount"].apply(lambda x: f"₹ {x:+,.0f}")
            cs["gold_grams"]  = cs["gold_grams"].apply(lambda x: f"{x:+.3f}g" if x != 0 else "—")
            st.dataframe(cs, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Export", data=cs.to_csv(index=False).encode(),
                               file_name="customer_ledger.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — Supplier Ledger
    # ══════════════════════════════════════════════════════════════════════════
    with tab_vendor:
        st.markdown("### 🏭 Supplier Ledger")
        st.caption("Negative = you owe the vendor.")

        txns = get_transactions({"party_type": "vendor"})
        if not txns:
            st.info("No vendor transactions yet.")
        else:
            df = _txn_df(txns)
            summary = (df.groupby("party_name")
                         .agg(total_cash=("cash_amount","sum"),
                              total_gold=("gold_grams","sum"))
                         .reset_index())

            for _, row in summary.iterrows():
                name     = row["party_name"]
                net_cash = _safe_float(row["total_cash"])
                net_gold = _safe_float(row["total_gold"])
                balance  = -net_cash
                clr = "#c0392b" if balance > 0 else "#27ae60"
                lbl = "we owe" if balance > 0 else "settled"
                st.markdown(
                    f'<div class="metric-card" style="border-left-color:{clr}">'
                    f'<h3>{name}</h3>'
                    f'<h2 style="color:{clr}">₹ {balance:,.0f} {lbl}</h2>'
                    f'<p style="color:#888;font-size:12px">'
                    f'Net paid: ₹{net_cash:,.0f} &nbsp;|&nbsp; Gold: {net_gold:.3f}g'
                    f'</p></div>', unsafe_allow_html=True)

            st.markdown("---")
            vend_list = df["party_name"].unique().tolist()
            sel_v = st.selectbox("Filter", ["All"] + vend_list, key="vend_flt")
            vdf   = df if sel_v == "All" else df[df["party_name"] == sel_v]
            vs    = vdf[["date","party_name","mode","cash_amount","gold_grams",
                          "order_ref","notes"]].copy()
            vs["date"]        = vs["date"].dt.strftime("%d %b %Y")
            vs["cash_amount"] = vs["cash_amount"].apply(lambda x: f"₹ {x:+,.0f}")
            vs["gold_grams"]  = vs["gold_grams"].apply(lambda x: f"{x:+.3f}g" if x != 0 else "—")
            st.dataframe(vs, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Export", data=vs.to_csv(index=False).encode(),
                               file_name="supplier_ledger.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5 — Cash Flow
    # ══════════════════════════════════════════════════════════════════════════
    with tab_cash:
        st.markdown("### 💵 Cash Flow Summary")
        all_txns = get_transactions()
        if not all_txns:
            st.info("No transactions yet.")
        else:
            df = _txn_df(all_txns)
            cf1, cf2 = st.columns(2)
            with cf1: cf_from = st.date_input("From", value=date(date.today().year,1,1), key="cf_from")
            with cf2: cf_to   = st.date_input("To",   value=date.today(), key="cf_to")

            mask     = df["date"].notna()
            df_range = df[mask & (df["date"] >= pd.Timestamp(cf_from)) &
                                  (df["date"] <= pd.Timestamp(cf_to))]

            total_in  = df_range[df_range["cash_amount"] > 0]["cash_amount"].sum()
            total_out = df_range[df_range["cash_amount"] < 0]["cash_amount"].sum()
            net_flow  = total_in + total_out
            gold_in   = df_range[df_range["gold_grams"]  > 0]["gold_grams"].sum()
            gold_out  = df_range[df_range["gold_grams"]  < 0]["gold_grams"].sum()

            k1,k2,k3 = st.columns(3)
            k1.markdown(f'<div class="metric-card" style="border-left-color:#27ae60">'
                        f'<h3>Cash In</h3><h2 style="color:#27ae60">₹ {total_in:,.0f}</h2></div>',
                        unsafe_allow_html=True)
            k2.markdown(f'<div class="metric-card" style="border-left-color:#c0392b">'
                        f'<h3>Cash Out</h3><h2 style="color:#c0392b">₹ {abs(total_out):,.0f}</h2></div>',
                        unsafe_allow_html=True)
            clr = "#27ae60" if net_flow >= 0 else "#c0392b"
            k3.markdown(f'<div class="metric-card"><h3>Net Flow</h3>'
                        f'<h2 style="color:{clr}">₹ {net_flow:,.0f}</h2></div>',
                        unsafe_allow_html=True)

            g1,g2,g3 = st.columns(3)
            g1.markdown(f'<div class="metric-card" style="border-left-color:#d4a843">'
                        f'<h3>Gold In</h3><h2 style="color:#d4a843">{gold_in:.3f}g</h2></div>',
                        unsafe_allow_html=True)
            g2.markdown(f'<div class="metric-card" style="border-left-color:#d4a843">'
                        f'<h3>Gold Out</h3><h2 style="color:#d4a843">{abs(gold_out):.3f}g</h2></div>',
                        unsafe_allow_html=True)
            net_g = gold_in + gold_out
            g3.markdown(f'<div class="metric-card" style="border-left-color:#d4a843">'
                        f'<h3>Net Gold</h3><h2 style="color:#d4a843">{net_g:+.3f}g</h2></div>',
                        unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### 📈 Monthly Cash Flow")
            if df_range["date"].notna().any():
                df_range = df_range.copy()
                df_range["month"] = df_range["date"].dt.to_period("M").astype(str)
                monthly = df_range.groupby("month")["cash_amount"].sum().reset_index()
                monthly.columns = ["Month","Net Cash (₹)"]
                st.bar_chart(monthly.set_index("Month"))

            st.markdown("### 💳 By Payment Mode")
            mode_df = df_range.groupby("mode")["cash_amount"].sum().reset_index()
            mode_df.columns = ["Mode","Net (₹)"]
            mode_df["Net (₹)"] = mode_df["Net (₹)"].apply(lambda x: f"₹ {x:,.0f}")
            st.dataframe(mode_df, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 6 — P&L per Order
    # ══════════════════════════════════════════════════════════════════════════
    with tab_pnl:
        st.markdown("### 📊 P&L per Order")
        st.caption("Line-by-line cost vs selling price breakdown per order.")

        orders   = get_all_orders()
        all_txns = get_transactions()

        if not orders:
            st.info("No orders yet.")
        else:
            odf = pd.DataFrame(orders)
            for c in ["order_id","customer","item_type","status"]:
                if c not in odf.columns: odf[c] = ""
                odf[c] = odf[c].astype(str).replace("nan","")

            num_cols = ["gross","net_amount","gold_value","gold_cost_value",
                        "total_diamond_value","total_diamond_cost",
                        "making_value","making_cost_value",
                        "cert_cost","cert_actual_cost",
                        "hallmark_value","hallmark_cost_value",
                        "total_cost","total_profit","profit_pct"]
            for c in num_cols:
                if c not in odf.columns: odf[c] = 0.0
                odf[c] = pd.to_numeric(odf[c], errors="coerce").fillna(0.0)

            txn_map = {}
            if all_txns:
                tdf = _txn_df(all_txns)
                tdf = tdf[tdf["order_ref"].str.strip() != ""]
                if not tdf.empty:
                    txn_map = tdf.groupby("order_ref")["cash_amount"].sum().to_dict()

            # ── Overall summary table ─────────────────────────────────────────
            summary_rows = []
            for _, o in odf.iterrows():
                oid      = o["order_id"]
                billed   = _safe_float(o.get("gross", 0))
                received = _safe_float(txn_map.get(oid, 0))
                cost     = _safe_float(o.get("total_cost", 0))
                profit   = _safe_float(o.get("total_profit", 0))
                pct      = _safe_float(o.get("profit_pct", 0))
                balance  = billed - received
                summary_rows.append({
                    "Order ID":   oid,
                    "Customer":   o["customer"],
                    "Status":     o["status"],
                    "Sell (Net)": f"₹{_safe_float(o.get('net_amount',0)):,.0f}",
                    "Total Cost": f"₹{cost:,.0f}",
                    "Profit":     f"₹{profit:,.0f}",
                    "Margin %":   f"{pct:.1f}%",
                    "Billed":     f"₹{billed:,.0f}",
                    "Received":   f"₹{received:,.0f}",
                    "Balance":    f"₹{balance:,.0f}",
                    "💰":         "✅" if balance <= 0 else "⏳",
                })

            st.markdown("#### 📋 Order Summary")
            st.dataframe(pd.DataFrame(summary_rows),
                         use_container_width=True, hide_index=True)

            # ── Overall KPIs ──────────────────────────────────────────────────
            total_sell    = odf["net_amount"].sum()
            total_cost    = odf["total_cost"].sum()
            total_profit  = odf["total_profit"].sum()
            total_billed  = odf["gross"].sum()
            total_recv    = sum(txn_map.values()) if txn_map else 0
            avg_margin    = round((total_profit / total_sell * 100), 1) if total_sell > 0 else 0

            st.markdown("---")
            st.markdown("#### 📊 Overall KPIs")
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            k1.metric("Total Revenue",     f"₹{total_sell:,.0f}")
            k2.metric("Total Cost",        f"₹{total_cost:,.0f}")
            k3.metric("Total Profit",      f"₹{total_profit:,.0f}")
            k4.metric("Avg Margin",        f"{avg_margin}%")
            k5.metric("Total Billed",      f"₹{total_billed:,.0f}")
            k6.metric("Outstanding",       f"₹{total_billed - total_recv:,.0f}")

            # ── Per-order line-by-line drill down ─────────────────────────────
            st.markdown("---")
            st.markdown("#### 🔍 Order Detail Breakdown")
            order_ids = odf["order_id"].tolist()
            sel_order = st.selectbox("Select Order", ["— Select —"] + order_ids, key="pnl_sel_order")

            if sel_order and sel_order != "— Select —":
                o = odf[odf["order_id"] == sel_order].iloc[0]

                st.markdown(f"**{sel_order}** — {o['customer']} | {o['item_type']} | {o['status']}")
                st.markdown("")

                # Line-by-line table
                def _sf(val): return _safe_float(o.get(val, 0))

                diam_sell = _sf("total_diamond_value")
                diam_cost = _sf("total_diamond_cost")

                line_rows = [
                    {
                        "Component":   "🥇 Gold",
                        "Sell Price":  f"₹{_sf('gold_value'):,.0f}",
                        "Cost Price":  f"₹{_sf('gold_cost_value'):,.0f}",
                        "Profit":      f"₹{_sf('gold_value') - _sf('gold_cost_value'):,.0f}",
                        "Margin":      f"{round((_sf('gold_value') - _sf('gold_cost_value')) / _sf('gold_value') * 100, 1) if _sf('gold_value') > 0 else 0:.1f}%",
                    },
                    {
                        "Component":   "💎 Diamonds",
                        "Sell Price":  f"₹{diam_sell:,.0f}",
                        "Cost Price":  f"₹{diam_cost:,.0f}",
                        "Profit":      f"₹{diam_sell - diam_cost:,.0f}",
                        "Margin":      f"{round((diam_sell - diam_cost) / diam_sell * 100, 1) if diam_sell > 0 else 0:.1f}%",
                    },
                    {
                        "Component":   "🔨 Making",
                        "Sell Price":  f"₹{_sf('making_value'):,.0f}",
                        "Cost Price":  f"₹{_sf('making_cost_value'):,.0f}",
                        "Profit":      f"₹{_sf('making_value') - _sf('making_cost_value'):,.0f}",
                        "Margin":      f"{round((_sf('making_value') - _sf('making_cost_value')) / _sf('making_value') * 100, 1) if _sf('making_value') > 0 else 0:.1f}%",
                    },
                    {
                        "Component":   "📜 Certificate",
                        "Sell Price":  f"₹{_sf('cert_cost'):,.0f}",
                        "Cost Price":  f"₹{_sf('cert_actual_cost'):,.0f}",
                        "Profit":      f"₹{_sf('cert_cost') - _sf('cert_actual_cost'):,.0f}",
                        "Margin":      f"{round((_sf('cert_cost') - _sf('cert_actual_cost')) / _sf('cert_cost') * 100, 1) if _sf('cert_cost') > 0 else 0:.1f}%",
                    },
                    {
                        "Component":   "🏅 Hallmark",
                        "Sell Price":  f"₹{_sf('hallmark_value'):,.0f}",
                        "Cost Price":  f"₹{_sf('hallmark_cost_value'):,.0f}",
                        "Profit":      f"₹{_sf('hallmark_value') - _sf('hallmark_cost_value'):,.0f}",
                        "Margin":      f"{round((_sf('hallmark_value') - _sf('hallmark_cost_value')) / _sf('hallmark_value') * 100, 1) if _sf('hallmark_value') > 0 else 0:.1f}%",
                    },
                    {
                        "Component":   "📦 TOTAL",
                        "Sell Price":  f"₹{_sf('net_amount'):,.0f}",
                        "Cost Price":  f"₹{_sf('total_cost'):,.0f}",
                        "Profit":      f"₹{_sf('total_profit'):,.0f}",
                        "Margin":      f"{_sf('profit_pct'):.1f}%",
                    },
                ]
                st.dataframe(pd.DataFrame(line_rows),
                             use_container_width=True, hide_index=True)

                # Profit bar
                tp = _sf("total_profit")
                clr = "#27ae60" if tp >= 0 else "#c0392b"
                st.markdown(
                    f'<div class="metric-card" style="border-left-color:{clr}">'
                    f'<h3>Net Profit on this Order</h3>'
                    f'<h2 style="color:{clr}">₹ {tp:,.0f} ({_sf("profit_pct"):.1f}% margin)</h2>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("---")
            st.download_button("⬇️ Export P&L", data=pd.DataFrame(summary_rows).to_csv(index=False).encode(),
                               file_name="pnl_orders.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 7 — Manage Vendors
    # ══════════════════════════════════════════════════════════════════════════
    with tab_vendors:
        st.markdown("### 🏭 Vendor / Supplier Master")
        with st.form("add_vendor_form"):
            st.markdown("**Add New Vendor**")
            vc1,vc2,vc3 = st.columns(3)
            with vc1: v_name  = st.text_input("Vendor Name *")
            with vc2: v_phone = st.text_input("Phone")
            with vc3: v_type  = st.selectbox("Type", ["Diamond Supplier","Gold Supplier",
                                                        "Making/Labour","Other"])
            vc4,vc5 = st.columns(2)
            with vc4: v_gstin = st.text_input("GSTIN (optional)")
            with vc5: v_notes = st.text_input("Notes")
            if st.form_submit_button("➕ Add Vendor"):
                if not v_name.strip():
                    st.error("Name required.")
                else:
                    save_vendor(dict(name=v_name.strip(), phone=v_phone.strip(),
                                    vendor_type=v_type, gstin=v_gstin.strip(),
                                    notes=v_notes.strip()))
                    st.success(f"✅ **{v_name}** added!")
                    st.rerun()

        st.markdown("---")
        vendors = get_all_vendors()
        if not vendors:
            st.info("No vendors added yet.")
        else:
            for v in vendors:
                bal = get_party_balance(v["name"], "vendor")
                owe = -bal["cash_balance"]
                with st.expander(
                    f"🏭 {v['name']}  |  {v.get('vendor_type','')}  |  "
                    f"{'⚠️ Owe ₹' + f'{owe:,.0f}' if owe > 0 else '✅ Settled'}"
                ):
                    c1,c2,c3 = st.columns(3)
                    c1.markdown(f"**Phone:** {v.get('phone','—')}")
                    c2.markdown(f"**GSTIN:** {v.get('gstin','—')}")
                    c3.markdown(f"**Notes:** {v.get('notes','—')}")
                    st.markdown(f"**Balance:** ₹{owe:,.0f} &nbsp;|&nbsp; Gold: {bal['gold_balance']:.3f}g")
                    if st.button("🗑️ Delete", key=f"dv_{v['_id']}"):
                        delete_vendor(v["_id"])
                        st.warning("Deleted.")
                        st.rerun()
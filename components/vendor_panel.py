"""
components/vendor_panel.py

Reusable panel to:
  1. Show vendor cost breakdown for an order (diamond, making, cert, hallmark)
  2. Show all vendor transactions linked to that order
  3. Allow adding new vendor transactions (cash payments, gold sent/received, goods received)
"""
import streamlit as st
import pandas as pd
from datetime import date, datetime

from config.settings import GOLD_PURITY
from services.database import (
    get_order_vendor_txns,
    save_order_vendor_txn,
    delete_order_vendor_txn,
    get_order_vendor_summary,
)

PAYMENT_MODES = ["Cash", "Bank Transfer", "UPI", "Gold (grams)"]

TXN_TYPE_LABELS = {
    "gold_sent":      "🥇 Gold Sent to Vendor",
    "gold_received":  "🥇 Gold Received Back",
    "cash_paid":      "💵 Cash / Payment Made",
    "goods_received": "📦 Goods Received from Vendor",
}


def render_vendor_panel(order_id: str, vendor_name: str, order_doc: dict):
    """
    Full vendor panel for one order.
    Shows cost summary, transaction history, and add-transaction form.

    order_doc must contain:
      gold_weight, making_value, total_diamond_value,
      cert_cost, hallmark_value, gold_price_gram, vendor
    """
    if not vendor_name:
        st.caption("No vendor assigned to this order.")
        return

    st.markdown(f"**Vendor:** {vendor_name}")
    st.markdown("---")

    # ── Cost summary from estimation ──────────────────────────────────────────
    gold_wt        = float(order_doc.get("gold_weight",      order_doc.get("gold_wt", 0)) or 0)
    gold_rate      = float(order_doc.get("gold_price_gram",   0) or 0)
    gold_purity    = str(order_doc.get("gold_purity",         "24K (99.9%)"))
    # Purity factors come from GOLD_PURITY so the ledger can never disagree
    # with what the estimate was priced at.
    purity_factor  = GOLD_PURITY.get(gold_purity, 1.0)
    # Pure 24K equivalent of this order's gold
    gold_24k_wt    = round(gold_wt * purity_factor, 4)
    gold_24k_rate  = float(order_doc.get("gold_price_gram", 0) or 0) / purity_factor if purity_factor > 0 else gold_rate
    making       = float(order_doc.get("making_value",          0) or 0)
    diamonds     = float(order_doc.get("total_diamond_value",   0) or 0)
    cert         = float(order_doc.get("cert_cost",             0) or 0)
    hallmark     = float(order_doc.get("hallmark_value",        0) or 0)
    total_payable = making + diamonds + cert + hallmark

    st.markdown("#### 📋 Order Cost Breakdown")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(
        f"Gold to Send ({gold_purity})",
        f"{gold_wt:.3f} g",
        delta=f"= {gold_24k_wt:.4f}g pure 24K",
        delta_color="off",
    )
    col2.metric("Making Payable",  f"₹ {making:,.0f}")
    col3.metric("Diamond Payable", f"₹ {diamonds:,.0f}")
    col4.metric("Cert + Hallmark", f"₹ {cert + hallmark:,.0f}")
    col5.metric("Total Payable",   f"₹ {total_payable:,.0f}")

    # ── Transaction summary ───────────────────────────────────────────────────
    summary = get_order_vendor_summary(order_id)
    st.markdown("#### 📊 Transaction Summary")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Gold Sent",        f"{summary['gold_sent']:.3f} g")
    s2.metric("Gold Received Back",f"{summary['gold_received']:.3f} g")

    net_gold = summary["net_gold"]
    net_clr  = "normal" if net_gold == 0 else "inverse"
    s3.metric("Net Gold w/ Vendor", f"{net_gold:.3f} g",
              delta="settled" if net_gold == 0 else f"{net_gold:.3f}g pending",
              delta_color=net_clr)

    cash_paid = summary["cash_paid"]
    balance   = total_payable - cash_paid
    s4.metric("Cash Paid",        f"₹ {cash_paid:,.0f}")
    s5.metric("Balance Due",      f"₹ {balance:,.0f}",
              delta="settled" if balance <= 0 else f"₹{balance:,.0f} pending",
              delta_color="normal" if balance <= 0 else "inverse")

    # ── Transaction history ───────────────────────────────────────────────────
    txns = get_order_vendor_txns(order_id)
    if txns:
        st.markdown("#### 🕐 Transaction History")
        rows = []
        for t in txns:
            rows.append({
                "Date":     t.get("date", ""),
                "Type":     TXN_TYPE_LABELS.get(t.get("txn_type", ""), t.get("txn_type", "")),
                "Mode":     t.get("mode", ""),
                "Gold (g)": f"{float(t.get('gold_grams', 0) or 0):+.3f}"
                             if t.get("gold_grams") else "—",
                "Cash (₹)": f"₹ {float(t.get('cash_amount', 0) or 0):,.0f}"
                             if t.get("cash_amount") else "—",
                "Notes":    t.get("notes", ""),
                "_id":      t["_id"],
            })
        tdf = pd.DataFrame(rows)
        st.dataframe(
            tdf.drop(columns=["_id"]),
            use_container_width=True, hide_index=True,
        )

        with st.expander("🗑️ Delete a Transaction"):
            del_map = {
                f"{r['Date']} | {r['Type']} | {r['Cash (₹)']} | {r['Gold (g)']}": r["_id"]
                for r in rows
            }
            sel = st.selectbox("Select", list(del_map.keys()),
                               key=f"del_sel_{order_id}")
            if st.button("🗑️ Delete", key=f"del_btn_{order_id}"):
                delete_order_vendor_txn(del_map[sel])
                st.warning("Deleted.")
                st.rerun()
    else:
        st.caption("No vendor transactions recorded yet for this order.")

    # ── Add new transaction ───────────────────────────────────────────────────
    st.markdown("#### ➕ Add Transaction")
    with st.form(key=f"vendor_txn_form_{order_id}"):
        f1, f2, f3 = st.columns(3)
        with f1:
            txn_type = st.selectbox(
                "Transaction Type",
                list(TXN_TYPE_LABELS.keys()),
                format_func=lambda x: TXN_TYPE_LABELS[x],
            )
        with f2:
            txn_date = st.date_input("Date", value=date.today())
        with f3:
            mode = st.selectbox("Payment Mode", PAYMENT_MODES)

        f4, f5, f6 = st.columns(3)
        with f4:
            if txn_type in ("gold_sent", "gold_received"):
                st.caption(f"Item gold: {gold_wt}g {gold_purity} = {gold_24k_wt}g pure 24K")
                gold_grams_item = st.number_input(
                    f"Gold (grams, {gold_purity})", min_value=0.0,
                    value=gold_wt if txn_type == "gold_sent" else 0.0,
                    step=0.001, format="%.3f",
                )
                # Convert to 24K equivalent for ledger
                gold_grams_24k = round(gold_grams_item * purity_factor, 4)
                st.caption(f"= **{gold_grams_24k:.4f}g pure 24K** will be recorded in ledger")
                gold_grams  = gold_grams_item   # item grams (for order txn record)
                cash_amount = 0.0
            else:
                cash_amount = st.number_input(
                    "Amount (₹)", min_value=0.0,
                    value=float(total_payable) if txn_type == "cash_paid" else 0.0,
                    step=100.0,
                )
                gold_grams = 0.0
        with f5:
            notes = st.text_input("Notes", placeholder="e.g. Advance payment")
        with f6:
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💾 Save", use_container_width=True)

        if submitted:
            txn_doc = dict(
                order_id    = order_id,
                vendor_name = vendor_name,
                txn_type    = txn_type,
                date        = str(txn_date),
                mode        = mode,
                gold_grams  = round(gold_grams, 4),
                cash_amount = round(cash_amount, 2),
                notes       = notes.strip(),
            )
            save_order_vendor_txn(txn_doc)

            # Also post to main ledger so finance page reflects it
            from services.database import save_transaction
            if txn_type == "gold_sent":
                _24k = round(gold_grams * purity_factor, 4)
                save_transaction(dict(
                    party_name  = vendor_name,
                    party_type  = "vendor",
                    date        = str(txn_date),
                    mode        = "Gold (grams)",
                    direction   = "out",
                    cash_amount = -round(_24k * gold_24k_rate, 2),
                    gold_grams  = -_24k,           # 24K pure grams in ledger
                    gold_rate   = gold_24k_rate,
                    order_ref   = order_id,
                    notes       = (
                        f"Gold sent for order {order_id}: "
                        f"{gold_grams}g {gold_purity} = {_24k}g pure 24K"
                    ),
                ))
            elif txn_type == "gold_received":
                _24k = round(gold_grams * purity_factor, 4)
                save_transaction(dict(
                    party_name  = vendor_name,
                    party_type  = "vendor",
                    date        = str(txn_date),
                    mode        = "Gold (grams)",
                    direction   = "in",
                    cash_amount = round(_24k * gold_24k_rate, 2),
                    gold_grams  = _24k,            # 24K pure grams back in ledger
                    gold_rate   = gold_24k_rate,
                    order_ref   = order_id,
                    notes       = (
                        f"Gold received back for order {order_id}: "
                        f"{gold_grams}g {gold_purity} = {_24k}g pure 24K"
                    ),
                ))
            elif txn_type == "cash_paid":
                save_transaction(dict(
                    party_name  = vendor_name,
                    party_type  = "vendor",
                    date        = str(txn_date),
                    mode        = mode,
                    direction   = "out",
                    cash_amount = -round(cash_amount, 2),
                    gold_grams  = 0.0,
                    gold_rate   = 0.0,
                    order_ref   = order_id,
                    notes       = notes or f"Payment for order {order_id}",
                ))

            st.success("✅ Transaction saved!")
            st.rerun()
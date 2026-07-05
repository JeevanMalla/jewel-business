"""
pages/dashboard.py
Main dashboard - KPI cards, revenue trend, recent orders, overdue alerts.
"""
import streamlit as st
import pandas as pd
from datetime import date

from services.database import get_setting, get_all_orders


def render():
    bname = get_setting("business_name", "Your Jewellery House")
    st.markdown(f"# 🏠 {bname}")
    st.caption(pd.Timestamp.now().strftime("%A, %d %B %Y"))
    st.markdown("---")

    all_orders = get_all_orders()
    print(all_orders)

    if not all_orders or not isinstance(all_orders, list):
        st.info("📭 No orders yet. Head to **New Estimation** to create your first order!")
        return

    try:
        df = pd.DataFrame(all_orders)
    except Exception:
        st.error("Could not load orders. Check MongoDB connection.")
        return

    if df.empty:
        st.info("📭 No orders yet.")
        return

    # ── Safe column coercion ──────────────────────────────────────────────────
    str_cols = ["order_id", "customer", "item_type", "status",
                "due_date", "order_date", "gold_purity", "notes"]
    for c in str_cols:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).replace("nan", "").replace("None", "")

    num_cols = ["gross", "net_amount", "gst", "total_profit", "profit_pct"]
    for c in num_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["due_date"]   = pd.to_datetime(df["due_date"],   errors="coerce")

    today   = pd.Timestamp(date.today())
    this_mo = today.month

    # ── KPI cards ─────────────────────────────────────────────────────────────
    # Exclude estimates from order KPIs
    orders_only = df[df["status"] != "Estimate"]
    estimates   = df[df["status"] == "Estimate"]

    kpis = [
        ("Total Orders",   len(orders_only),                                        "#1a1a2e"),
        ("Estimates",      len(estimates),                                           "#856404"),
        ("In Progress",    (orders_only["status"] == "In Progress").sum(),           "#004085"),
        ("Quality Check",  (orders_only["status"] == "Quality Check").sum(),         "#155724"),
        ("Ready",          (orders_only["status"] == "Ready for Delivery").sum(),    "#0c5460"),
        ("Delivered",      (orders_only["status"] == "Delivered").sum(),             "#383d41"),
    ]

    cols = st.columns(6)
    for col, (label, val, clr) in zip(cols, kpis):
        col.markdown(
            f'<div class="metric-card">'
            f'<h3>{label}</h3>'
            f'<h2 style="color:{clr}">{val}</h2>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Revenue + profit this month
    valid_month = df["order_date"].notna() & (df["order_date"].dt.month == this_mo)
    rev_mo    = df.loc[valid_month, "gross"].sum()
    profit_mo = df.loc[valid_month, "total_profit"].sum()

    r1, r2 = st.columns(2)
    r1.markdown(
        f'<div class="metric-card" style="border-left-color:#d4a843">'
        f'<h3>This Month Revenue</h3>'
        f'<h2 style="color:#d4a843">₹ {rev_mo:,.0f}</h2>'
        f'</div>',
        unsafe_allow_html=True,
    )
    profit_clr = "#27ae60" if profit_mo >= 0 else "#c0392b"
    r2.markdown(
        f'<div class="metric-card" style="border-left-color:{profit_clr}">'
        f'<h3>This Month Profit</h3>'
        f'<h2 style="color:{profit_clr}">₹ {profit_mo:,.0f}</h2>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Overdue alert ──────────────────────────────────────────────────────────
    valid_due = df["due_date"].notna()
    overdue   = df[
        valid_due &
        (df["due_date"] < today) &
        (~df["status"].isin(["Delivered", "Estimate"]))
    ]
    if not overdue.empty:
        st.error(f"⚠️ **{len(overdue)} order(s) are overdue!** Check the Orders page.")

    st.markdown("---")

    # ── Recent orders + status chart ──────────────────────────────────────────
    left, right = st.columns([2, 1])

    with left:
        st.markdown("### 📋 Recent Orders")
        show = [c for c in ["order_id", "customer", "item_type", "status", "due_date", "gross"]
                if c in df.columns]
        recent = df[df["status"] != "Estimate"].head(10)[show].copy()
        if "due_date" in recent.columns:
            recent["due_date"] = recent["due_date"].dt.strftime("%d %b %Y").fillna("—")
        if "gross" in recent.columns:
            recent["gross"] = recent["gross"].apply(lambda x: f"₹{x:,.0f}")
        st.dataframe(recent, use_container_width=True, hide_index=True)

    with right:
        st.markdown("### 📊 Status")
        st.bar_chart(orders_only["status"].value_counts())

    # ── Monthly revenue + profit trend ────────────────────────────────────────
    st.markdown("### 📈 Monthly Revenue & Profit Trend")
    if df["order_date"].notna().any():
        df["month"] = df["order_date"].dt.to_period("M").astype(str)
        rev = df.groupby("month").agg(
            Revenue=("gross", "sum"),
            Profit=("total_profit", "sum"),
        ).reset_index().set_index("month")
        st.line_chart(rev)
    else:
        st.caption("No date data for trend chart yet.")
"""
app_pages/dashboard.py
Main dashboard - production alerts, KPI cards, upcoming deadlines, recent orders.
"""
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from services.database import (
    get_setting, get_all_orders, get_all_estimates,
    get_production_kpis, get_all_active_production,
)


def render():
    bname = get_setting("business_name", "Your Jewellery House")
    st.markdown(f"# 🏠 {bname}")
    st.caption(pd.Timestamp.now().strftime("%A, %d %B %Y"))
    st.markdown("---")

    # ── Production alerts (shown first, above everything else) ────────────────
    pkpis = get_production_kpis()
    if pkpis["delayed"] or pkpis["waiting_approval"] or pkpis["due_today"]:
        st.markdown("### 🏭 Production Alerts")
        a1, a2, a3 = st.columns(3)
        if pkpis["delayed"]:
            a1.error(f"⚠️ {pkpis['delayed']} stage(s) overdue")
        if pkpis["waiting_approval"]:
            a2.warning(f"⏳ {pkpis['waiting_approval']} awaiting CAD approval")
        if pkpis["due_today"]:
            a3.info(f"📅 {pkpis['due_today']} due today")

        qc_waiting = [s for s in get_all_active_production() if s["stage_name"] == "Quality Check"]
        if qc_waiting:
            st.warning(f"🔍 {len(qc_waiting)} order(s) waiting on Quality Check")

        st.markdown("---")

    all_orders = get_all_orders()

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

    num_cols = ["gross_amount", "net_amount", "gst_amount", "total_profit", "profit_pct"]
    for c in num_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["due_date"]   = pd.to_datetime(df["due_date"],   errors="coerce")

    today   = pd.Timestamp(date.today())
    this_mo = today.month

    # ── KPI cards ─────────────────────────────────────────────────────────────
    # `df` is the orders collection, which no longer contains estimates at all;
    # estimates are counted separately and contribute nothing to revenue.
    orders_only    = df
    estimate_count = len(get_all_estimates())

    kpis = [
        ("Total Orders",   len(orders_only),                                        "#1a1a2e"),
        ("Estimates",      estimate_count,                                          "#856404"),
        ("In Progress",    (orders_only["status"] == "In Progress").sum(),           "#004085"),
        ("Quality Check",  (orders_only["status"] == "Quality Check").sum(),         "#155724"),
        ("Ready",          (orders_only["status"] == "Ready for Delivery").sum(),    "#0c5460"),
    ]

    cols = st.columns(len(kpis))
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
    rev_mo    = df.loc[valid_month, "gross_amount"].sum()
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

    # ── Recent orders + upcoming deadlines ──────────────────────────────────────
    left, right = st.columns([2, 1])

    with left:
        st.markdown("### 📋 Recent Orders")
        show = [c for c in ["order_id", "customer", "item_type", "status", "due_date", "gross_amount"]
                if c in df.columns]
        recent = df.head(10)[show].copy()
        if "due_date" in recent.columns:
            recent["due_date"] = recent["due_date"].dt.strftime("%d %b %Y").fillna("—")
        if "gross_amount" in recent.columns:
            recent["gross_amount"] = recent["gross_amount"].apply(lambda x: f"₹{x:,.0f}")
        recent = recent.rename(columns={"gross_amount": "gross"})
        st.dataframe(recent, use_container_width=True, hide_index=True)

    with right:
        st.markdown("### 📅 Deadlines This Week")
        week_out = today + timedelta(days=7)
        upcoming = df[
            valid_due &
            (df["due_date"] >= today) &
            (df["due_date"] <= week_out) &
            (~df["status"].isin(["Delivered", "Estimate"]))
        ].sort_values("due_date")

        if upcoming.empty:
            st.caption("Nothing due in the next 7 days. 🎉")
        else:
            for _, r in upcoming.iterrows():
                days_left = (r["due_date"] - today).days
                due_label = "Today" if days_left == 0 else ("Tomorrow" if days_left == 1 else f"in {days_left}d")
                st.markdown(
                    f'<div class="metric-card" style="padding:8px 10px;margin-bottom:6px;">'
                    f'<strong>{r["order_id"]}</strong> — {r["customer"]}<br>'
                    f'<span style="font-size:0.85em;color:#666">{r["item_type"]}</span><br>'
                    f'<span style="font-size:0.85em">📅 {r["due_date"].strftime("%d %b")} · {due_label}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("View full order →", key=f"deadline_{r['order_id']}", use_container_width=True):
                    st.session_state["order_search"]  = r["order_id"]
                    st.session_state["nav_request"]   = "📦 Orders"
                    st.rerun()
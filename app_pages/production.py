"""
pages/production.py
Production Management — Kanban board of active orders + a full
per-order timeline with jeweller override controls.

The jeweller is the sole actor for now (no auth). "user" is passed
through as a plain string ("Admin") so production_events already has
the right shape once real roles/auth land later.
"""
import streamlit as st

from config.settings import KANBAN_STAGES
from services.database import (
    get_all_orders,
    get_production_kpis,
    get_all_active_production,
    get_order_stages,
    init_production_pipeline,
)
from components.production_timeline import render_timeline
from components.stage_card import render_stage_card

CURRENT_USER = "Admin"  # placeholder until roles/auth (Phase 2+) exist


def _backfill_pipelines(orders: dict):
    """
    Any order that's already confirmed (not an Estimate) but doesn't have
    production_stages yet gets one created now. Makes this page safe to
    drop into an existing database with orders that pre-date Production.
    """
    for oid, o in orders.items():
        if o.get("status") not in ("Estimate", None) and not get_order_stages(oid):
            init_production_pipeline(oid)


def render():
    st.markdown("# 🏭 Production")
    st.markdown("---")

    orders = {o["order_id"]: o for o in get_all_orders()}
    _backfill_pipelines(orders)

    # ── KPI row ──────────────────────────────────────────────────────────────
    kpis = get_production_kpis()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Active Orders",       kpis["total_active"])
    k2.metric("⚠️ Delayed",          kpis["delayed"])
    k3.metric("📅 Due Today",        kpis["due_today"])
    k4.metric("⏳ Waiting Approval", kpis["waiting_approval"])
    st.markdown("---")

    # ── If an order was opened (from a card, or from Orders page), show its
    #    full timeline instead of the board ────────────────────────────────
    open_id = st.session_state.get("production_open_order")
    if open_id and open_id in orders:
        if st.button("← Back to Board"):
            st.session_state["production_open_order"] = None
            st.rerun()
        st.markdown(f"### {open_id} — {orders[open_id].get('customer', '')}")
        render_timeline(open_id, orders[open_id], user=CURRENT_USER)
        return

    # ── Kanban board ─────────────────────────────────────────────────────────
    active = get_all_active_production()
    cols = st.columns(len(KANBAN_STAGES))
    for col, stage_name in zip(cols, KANBAN_STAGES):
        with col:
            st.markdown(f"#### {stage_name}")
            bucket = [s for s in active if s["stage_name"] == stage_name]
            if not bucket:
                st.caption("No orders here.")
            for s in bucket:
                order_doc = orders.get(s["order_id"], {})
                if render_stage_card(s, order_doc):
                    st.session_state["production_open_order"] = s["order_id"]
                    st.rerun()

    # Orders sitting in a stage that isn't one of the four highlighted
    # Kanban columns (e.g. Filing, Polishing, Quality Check) still need to
    # be reachable — list them below the board.
    other = [s for s in active if s["stage_name"] not in KANBAN_STAGES]
    if other:
        st.markdown("---")
        st.markdown("### Other Active Stages")
        for s in other:
            order_doc = orders.get(s["order_id"], {})
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(
                    f"**{s['order_id']}** — {order_doc.get('customer', '')} · "
                    f"**{s['stage_name']}** ({s['status']})"
                )
            with c2:
                if st.button("Open", key=f"open_other_{s['order_id']}", use_container_width=True):
                    st.session_state["production_open_order"] = s["order_id"]
                    st.rerun()
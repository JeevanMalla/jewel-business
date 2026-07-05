"""
components/stage_card.py
Compact order card shown inside a Kanban column on the Production page.
"""
import streamlit as st
import pandas as pd
from datetime import date


def render_stage_card(stage_doc: dict, order_doc: dict) -> bool:
    """
    Renders one Kanban card for a single order's current stage.
    Returns True if the user clicked "Open" — caller decides what to do
    (typically: stash the order_id in session_state and switch to the
    timeline view).
    """
    oid      = stage_doc["order_id"]
    deadline = stage_doc.get("deadline")
    is_late  = False
    if deadline:
        try:
            is_late = pd.to_datetime(deadline).date() < date.today()
        except Exception:
            pass

    if is_late:
        border = "#c0392b"
    elif stage_doc.get("status") == "NEED_CHANGES":
        border = "#856404"
    else:
        border = "#1a1a2e"

    delay_html = ' &nbsp;⚠️ <strong style="color:#c0392b">DELAYED</strong>' if is_late else ""

    with st.container():
        st.markdown(
            f'<div style="border-left:4px solid {border};padding:10px 12px;'
            f'margin-bottom:8px;border-radius:6px;background:#fff;'
            f'color:#000;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.08)">'
            f'<strong>{oid}</strong> — {order_doc.get("customer", "")}<br>'
            f'<span style="color:#444;font-size:0.85em">{order_doc.get("item_type", "")}</span><br>'
            f'<span style="font-size:0.85em">👤 {stage_doc.get("assigned_to") or "Unassigned"}</span><br>'
            f'<span style="font-size:0.85em">📅 {deadline or "No deadline"}{delay_html}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return st.button(
            "Open →",
            key=f"open_{oid}_{stage_doc['stage_name']}",
            use_container_width=True,
        )
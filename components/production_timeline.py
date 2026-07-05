"""
components/production_timeline.py
Full 10-stage production timeline for one order, plus the jeweller's
override controls: move stage forward/backward, reassign karigar,
change deadline, add notes, attach a progress photo.

The jeweller can override anything, anytime — none of the buttons here
are gated by "is this the right stage" validation on purpose.
"""
import streamlit as st
from datetime import date

from services.database import (
    get_order_stages,
    move_stage,
    assign_karigar,
    set_stage_deadline,
    add_stage_note,
    flag_stage_needs_changes,
    add_stage_image,
    get_production_events,
    mark_order_delivered,
)
from services.cloudinary import upload_image_widget

STAGE_ICONS = {
    "COMPLETED":    "✅",
    "IN_PROGRESS":  "▶️",
    "NEED_CHANGES": "⚠️",
    "NOT_STARTED":  "⬜",
}


def render_timeline(order_id: str, order_doc: dict, user: str = "Admin"):
    stages = get_order_stages(order_id)
    if not stages:
        st.info("Production hasn't started for this order yet.")
        return

    st.markdown("#### 🧵 Production Timeline")
    st.markdown(
        "&nbsp;&nbsp;".join(
            f"{STAGE_ICONS.get(s['status'], '⬜')} {s['stage_name']}" for s in stages
        )
    )
    st.markdown("---")

    current = next((s for s in stages if s["status"] != "COMPLETED"), stages[-1])
    st.markdown(f"**Current stage:** {current['stage_name']}  ·  **Status:** {current['status']}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("⬅️ Move Back", use_container_width=True, key=f"back_{order_id}"):
            move_stage(order_id, "backward", user)
            st.rerun()
    with c2:
        if st.button("✅ Mark Complete / Move Forward", use_container_width=True, key=f"fwd_{order_id}"):
            move_stage(order_id, "forward", user)
            st.rerun()
    with c3:
        if current["stage_name"] == "Customer CAD Approval":
            if st.button("⚠️ Needs Changes", use_container_width=True, key=f"needs_{order_id}"):
                flag_stage_needs_changes(order_id, current["stage_name"], user=user)
                st.rerun()

    if current["stage_name"] != "Delivered":
        with st.expander("⏩ Skip straight to Delivered (override)"):
            st.caption(
                "Closes out every remaining stage immediately — use for rush "
                "jobs, walk-in pickups, or backfilling an order that was "
                "already completed before this system was in place."
            )
            if st.button("⏩ Mark as Delivered", key=f"deliver_{order_id}", use_container_width=True):
                mark_order_delivered(order_id, user)
                st.success("Order marked as Delivered.")
                st.rerun()

    st.markdown("---")
    st.markdown("##### ✏️ Update This Stage")

    e1, e2 = st.columns(2)
    with e1:
        karigar = st.text_input(
            "Assigned Karigar / Staff",
            value=current.get("assigned_to", ""),
            key=f"kar_{order_id}",
        )
        if st.button("Save Assignment", key=f"save_kar_{order_id}"):
            assign_karigar(order_id, current["stage_name"], karigar, user)
            st.success("Assigned.")
            st.rerun()
    with e2:
        raw_dl = current.get("deadline")
        try:
            dl_val = date.fromisoformat(str(raw_dl)[:10]) if raw_dl else date.today()
        except Exception:
            dl_val = date.today()
        new_dl = st.date_input("Deadline", value=dl_val, key=f"dl_{order_id}")
        if st.button("Save Deadline", key=f"save_dl_{order_id}"):
            set_stage_deadline(order_id, current["stage_name"], new_dl, user)
            st.success("Deadline updated.")
            st.rerun()

    note = st.text_area("Notes", value=current.get("notes", ""), key=f"note_{order_id}")
    if st.button("💾 Save Notes", key=f"save_note_{order_id}"):
        add_stage_note(order_id, current["stage_name"], note, user)
        st.success("Notes saved.")
        st.rerun()

    img_url = upload_image_widget(
        label="📷 Stage Progress Photo",
        order_id=order_id,
        img_key=f"stage_{current['stage_name']}",
        widget_key=f"stage_img_{order_id}_{current['stage_name']}",
    )
    if img_url:
        add_stage_image(order_id, current["stage_name"], img_url, user)
        st.success("Image attached to stage.")
        st.rerun()

    if current.get("images"):
        st.markdown("**Stage Images:**")
        st.image(current["images"], width=120)

    with st.expander("🕐 Full History"):
        events = get_production_events(order_id)
        if not events:
            st.caption("No events logged yet.")
        for ev in events:
            ts = ev.get("created_at")
            ts_str = ts.strftime("%d %b %Y %H:%M") if ts else "—"
            st.caption(
                f"{ts_str} — {ev.get('user','')} · {ev.get('action','')} "
                f"({ev.get('old_value','') or '—'} → {ev.get('new_value','') or '—'})"
            )
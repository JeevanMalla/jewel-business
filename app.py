import streamlit as st
from config.settings import PAGE_CONFIG, apply_global_css

# st.set_page_config must be the very first Streamlit command in the script.
st.set_page_config(**PAGE_CONFIG)


def check_password() -> bool:
    """
    Simple shared-password gate for the whole app. Add this to your
    .streamlit/secrets.toml (or the Secrets manager on Streamlit Cloud):

        app_password = "your-password-here"

    This is one password for everyone (jeweller, staff, karigar) — not
    per-user accounts. That's a Phase 2+ concern once real roles/auth
    land; for now this just keeps the app off the open internet.
    """
    def _on_submit():
        entered = st.session_state.get("password_input", "")
        if entered == st.secrets.get("app_password", ""):
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct"):
        return True

    st.markdown("## 🔒 Jewel Manager Pro")
    st.text_input(
        "Enter password",
        type="password",
        on_change=_on_submit,
        key="password_input",
    )
    if st.session_state.get("password_correct") is False:
        st.error("😕 Incorrect password")
    return False


if not check_password():
    st.stop()

apply_global_css()

from services.database import DatabaseError, get_db_error, clear_db_error
from components.sidebar import render_sidebar


def _render_page(page, gold_base, diamond_base, shape_dfs):
    if page == "🏠 Dashboard":
        from app_pages.dashboard import render
        render()

    elif page == "📋 New Estimation":
        from app_pages.estimation import render
        render(gold_base, diamond_base, shape_dfs)

    elif page == "📦 Orders":
        from app_pages.orders import render
        render()

    elif page == "🏭 Production":
        from app_pages.production import render
        render()

    elif page == "💰 Finance":
        from app_pages.finance import render
        render(gold_base)

    elif page == "⚙️ Settings":
        from app_pages.settings import render
        render(gold_base)


# Reads never raise — they record the failure and return empty. Clearing the
# marker before each run means the banner below only ever reflects *this* run,
# not a problem that has since resolved itself.
clear_db_error()

try:
    page, gold_base, diamond_base, shape_dfs = render_sidebar()
except DatabaseError as exc:
    st.error(f"### 🔌 Database unavailable\n\n{exc}")
    st.stop()

try:
    _render_page(page, gold_base, diamond_base, shape_dfs)
except DatabaseError as exc:
    # A write failed. Say so plainly — a silent no-op is far worse than a
    # visible error when the jeweller thinks they just saved an order.
    st.error(f"### ⚠️ That didn't save\n\n{exc}")
    st.caption("Nothing was changed. Fix the problem above and try again.")

# A read failed somewhere on this page: the page rendered, but with missing
# data. Say so, so an outage is never mistaken for an empty database.
_read_err = get_db_error()
if _read_err:
    st.warning(
        f"⚠️ **Some data couldn't be loaded** — what you see may be incomplete.\n\n"
        f"{_read_err['message']}"
    )
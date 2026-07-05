import streamlit as st
from config.settings import PAGE_CONFIG, apply_global_css
from components.sidebar import render_sidebar

st.set_page_config(**PAGE_CONFIG)
apply_global_css()

page, gold_base, diamond_base, shape_dfs = render_sidebar()

if page == "🏠 Dashboard":
    from pages.dashboard import render
    render()

elif page == "📋 New Estimation":
    from pages.estimation import render
    render(gold_base, diamond_base, shape_dfs)

elif page == "📦 Orders":
    from pages.orders import render
    render()

elif page == "💰 Finance":
    from pages.finance import render
    render(gold_base)

elif page == "⚙️ Settings":
    from pages.settings import render
    render(gold_base)
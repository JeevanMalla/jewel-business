"""
components/sidebar.py
Renders the sidebar navigation, price controls, and diamond sheet loader.
"""
import streamlit as st
from services.database import get_prices, save_prices


def render_sidebar():
    live      = get_prices()
    shape_dfs = {}

    with st.sidebar:
        st.markdown("## 💎 Jewel Manager Pro")
        st.markdown("---")

        page = st.radio(
            "Navigation",
            ["🏠 Dashboard", "📋 New Estimation", "📦 Orders",
             "💰 Finance", "⚙️ Settings"],
            label_visibility="collapsed",
        )
        st.markdown("---")

        # Price source
        st.markdown("### 💰 Price Source")
        price_mode = st.radio(
            "Mode", ["Manual", "From MongoDB"],
            label_visibility="collapsed",
        )

        if price_mode == "Manual":
            gold_base    = st.number_input("Gold 24K ₹/gram", value=live["gold"],    min_value=1.0, step=10.0)
            diamond_base = st.number_input("Diamond ₹/carat", value=live["diamond"], min_value=1.0, step=100.0)
            if st.button("💾 Save Prices", use_container_width=True):
                save_prices(gold_base, diamond_base)
                st.success("✅ Saved!")
        else:
            gold_base    = live["gold"]
            diamond_base = live["diamond"]
            if st.button("🔄 Refresh Prices", use_container_width=True):
                st.cache_resource.clear()
                st.rerun()
            st.markdown(f"📊 Gold: ₹{gold_base:,.2f}/g")
            st.markdown(f"💎 Diamond: ₹{diamond_base:,.0f}/ct")

        st.markdown("---")

        # Diamond price sheet (only shown if configured)
        try:
            diamond_sheet_id = st.secrets.get("diamond_sheet_id", "")
        except Exception:
            diamond_sheet_id = ""

        if diamond_sheet_id:
            from services.diamond_sheet import load_all_shapes
            st.markdown("### 📊 Diamond Sheet")
            try:
                shape_dfs = load_all_shapes(diamond_sheet_id)
                st.success(f"✅ {len(shape_dfs)} shape(s) loaded")
                if st.button("🔄 Refresh Diamond Prices", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()
            except Exception as e:
                st.warning(f"Sheet error: {e}")
                shape_dfs = {}
            st.markdown("---")

        st.caption(f"24K ₹{gold_base:,.2f}/g  ·  💎 ₹{diamond_base:,.0f}/ct")

    return page, gold_base, diamond_base, shape_dfs
"""
pages/settings.py
Business profile, logo upload, gold rate reference, secrets setup guide.
"""
import streamlit as st
import pandas as pd

from config.settings import GOLD_PURITY
from services.database import get_setting, set_setting


def render(gold_base: float):
    st.markdown("# ⚙️ Settings")
    st.markdown("---")

    # ── Business profile ──────────────────────────────────────────────────────
    st.markdown("### 🏢 Business Profile")
    current_name = get_setting("business_name", "Your Jewellery House")
    new_name = st.text_input("Business Name", value=current_name)
    if st.button("💾 Save Name", use_container_width=False):
        set_setting("business_name", new_name)
        st.success("✅ Business name saved!")

    st.markdown("---")

    # ── Logo upload ───────────────────────────────────────────────────────────
    st.markdown("### 🖼️ Logo (appears on PDF quotes)")
    st.caption("Logo is stored in session only — re-upload after restart.")
    logo_up = st.file_uploader("Upload Logo (PNG / JPG)", type=["png", "jpg", "jpeg"])
    if logo_up:
        st.session_state["logo_bytes"] = logo_up.read()
        st.image(st.session_state["logo_bytes"], width=200)
        st.success("✅ Logo ready — will appear on all PDF quotes this session.")

    st.markdown("---")

    # ── Gold rate table ───────────────────────────────────────────────────────
    st.markdown("### 🏅 Gold Rates by Purity (current session)")
    rate_df = pd.DataFrame([
        {"Purity": k, "Purity Factor": v, "Rate / gram": f"₹ {gold_base * v:,.2f}"}
        for k, v in GOLD_PURITY.items()
    ])
    st.dataframe(rate_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── Secrets setup guide ───────────────────────────────────────────────────
    st.markdown("### 🔑 Local Setup — `.streamlit/secrets.toml`")
    st.markdown("Create this file in your project root (never commit to Git):")
    st.code("""
# .streamlit/secrets.toml

# MongoDB Atlas
mongodb_uri = "mongodb+srv://USER:PASS@cluster.mongodb.net/?retryWrites=true&w=majority"
mongodb_db  = "jewel_manager"

# Cloudinary
cloudinary_cloud_name = "your_cloud_name"
cloudinary_api_key    = "your_api_key"
cloudinary_api_secret = "your_api_secret"

# Diamond Price Google Sheet (optional)
diamond_sheet_id = "your_sheet_id_from_url"

# Google Service Account (for diamond sheet)
[gcp_service_account]
type           = "service_account"
project_id     = "your-project-id"
private_key_id = "..."
private_key    = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
client_email   = "your-sa@your-project.iam.gserviceaccount.com"
client_id      = "..."
auth_uri       = "https://accounts.google.com/o/oauth2/auth"
token_uri      = "https://oauth2.googleapis.com/token"
    """, language="toml")

    with st.expander("📖 How to get each credential"):
        st.markdown("""
**MongoDB URI**
1. Go to [mongodb.com/atlas](https://cloud.mongodb.com) → your cluster
2. Click **Connect** → **Drivers** → copy the URI
3. Replace `<password>` with your DB user password

**Cloudinary**
1. Sign up free at [cloudinary.com](https://cloudinary.com)
2. Dashboard → copy **Cloud Name**, **API Key**, **API Secret**

**Diamond Sheet ID**
- From your sheet URL: `https://docs.google.com/spreadsheets/d/**THIS_PART**/edit`

**Google Service Account**
1. Google Cloud Console → APIs & Services → Credentials
2. Your service account → Keys → Add Key → JSON
3. Copy values from the downloaded JSON into secrets
4. **Share your diamond price sheet** with the `client_email` as Editor
        """)
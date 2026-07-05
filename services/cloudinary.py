"""
services/cloudinary.py
Image upload to Cloudinary via REST API (no SDK required).
"""
import hashlib
import time
import requests
import streamlit as st


FOLDER = "jewel_manager"


def upload_image(file_bytes: bytes, filename: str) -> dict:
    """
    Upload bytes to Cloudinary.
    Returns the full Cloudinary response dict (contains secure_url, etc.)
    Raises Exception on failure.
    """
    cloud_name = st.secrets["cloudinary_cloud_name"]
    api_key    = st.secrets["cloudinary_api_key"]
    api_secret = st.secrets["cloudinary_api_secret"]

    timestamp = str(int(time.time()))
    public_id = f"{FOLDER}/{filename}_{timestamp}"

    # SHA-1 signature required by Cloudinary
    sign_str  = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(sign_str.encode()).hexdigest()

    resp = requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload",
        data={
            "api_key":   api_key,
            "timestamp": timestamp,
            "signature": signature,
            "public_id": public_id,
        },
        files={"file": (filename, file_bytes, "image/jpeg")},
        timeout=30,
    )

    if resp.status_code == 200:
        return resp.json()
    raise Exception(f"Cloudinary {resp.status_code}: {resp.text}")


def upload_image_widget(
    label: str,
    order_id: str,
    img_key: str,
    widget_key: str,
) -> str | None:
    """
    Renders a single file uploader + preview.
    Returns the secure_url string if uploaded, else None.

    Streamlit reruns the entire script on every interaction anywhere on
    the page — not just when this widget changes — and st.tabs() runs
    both tabs' code every rerun regardless of which is visible. Without
    caching, the same already-uploaded file would get re-uploaded to
    Cloudinary on every unrelated keystroke/click elsewhere on the page.
    So: once a given physical file has been uploaded, its URL is cached
    in session_state and reused until a *different* file is selected.
    """
    st.markdown(f"**{label}**")
    uploaded = st.file_uploader(
        label,
        type=["jpg", "jpeg", "png", "webp"],
        key=widget_key,
        label_visibility="collapsed",
    )

    if not uploaded:
        return None

    cache_key = f"{widget_key}_cloudinary_url"
    id_key    = f"{widget_key}_file_id"

    # Same file as last run — reuse the cached URL, no re-upload.
    if st.session_state.get(id_key) == uploaded.file_id and st.session_state.get(cache_key):
        url = st.session_state[cache_key]
        st.success("✅ Uploaded")
        st.image(url, use_column_width=True)
        return url

    # New file (or first time) — actually upload.
    with st.spinner(f"Uploading {label}…"):
        try:
            result = upload_image(uploaded.read(), f"{order_id}_{img_key}")
            url = result["secure_url"]
            st.session_state[cache_key] = url
            st.session_state[id_key]    = uploaded.file_id
            st.success("✅ Uploaded")
            st.image(url, use_column_width=True)
            return url
        except Exception as e:
            st.error(f"Upload failed: {e}")
    return None
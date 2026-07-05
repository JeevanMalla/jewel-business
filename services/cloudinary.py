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
    """
    st.markdown(f"**{label}**")
    uploaded = st.file_uploader(
        label,
        type=["jpg", "jpeg", "png", "webp"],
        key=widget_key,
        label_visibility="collapsed",
    )
    if uploaded:
        with st.spinner(f"Uploading {label}…"):
            try:
                result = upload_image(
                    uploaded.read(),
                    f"{order_id}_{img_key}",
                )
                url = result["secure_url"]
                st.success("✅ Uploaded")
                st.image(url, use_column_width=True)
                return url
            except Exception as e:
                st.error(f"Upload failed: {e}")
    return None
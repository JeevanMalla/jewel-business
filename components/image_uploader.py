"""
components/image_uploader.py
Reusable 3-slot image upload widget (item / customer ref / CAD).
Used in both New Estimation and Orders pages.
"""
import streamlit as st
from services.cloudinary import upload_image_widget


IMAGE_SLOTS = [
    ("item_image",     "📷 Item / Product Image"),
    ("customer_image", "👤 Customer Reference Image"),
    ("cad_image",      "🖥️ CAD Design Image"),
]


def render_image_uploader(order_id: str, key_prefix: str) -> dict[str, str]:
    """
    Renders 3 upload widgets in columns.
    Returns {img_key: cloudinary_url} for any images uploaded this run.
    """
    uploaded: dict[str, str] = {}
    cols = st.columns(3)

    for (img_key, label), col in zip(IMAGE_SLOTS, cols):
        with col:
            url = upload_image_widget(
                label=label,
                order_id=order_id,
                img_key=img_key,
                widget_key=f"{key_prefix}_{img_key}",
            )
            if url:
                uploaded[img_key] = url

    return uploaded


def render_image_gallery(order_doc: dict):
    """
    Displays stored images from an order document.
    Shows a placeholder caption for missing slots.
    """
    cols = st.columns(3)
    has_any = False

    for (img_key, label), col in zip(IMAGE_SLOTS, cols):
        url = order_doc.get(img_key, "")
        with col:
            if url:
                has_any = True
                st.image(url, use_column_width=True)
                st.markdown(
                    f'<p class="img-label">{label}</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<p class="img-label">{label.split(" ", 1)[1]} — not uploaded</p>',
                    unsafe_allow_html=True,
                )

    if not has_any:
        st.caption("No images have been uploaded for this order yet.")
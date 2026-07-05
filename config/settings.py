import streamlit as st

# ── App metadata ──────────────────────────────────────────────────────────────
PAGE_CONFIG = dict(
    page_title="Jewel Manager Pro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Business constants ────────────────────────────────────────────────────────
GOLD_PURITY = {
    "24K (99.9%)": 1.000,
    "22K (91.6%)": 0.916,
    "18K (75.0%)": 0.760,
    "14K (58.3%)": 0.595,
    "10k (41.7%)": 0.430,
}

ORDER_STATUSES = [
    "Pending",
    "In Progress",
    "Quality Check",
    "Ready for Delivery",
    "Delivered",
]

ITEM_TYPES = [
    "Bangle", "Ring", "Necklace", "Earring",
    "Bracelet", "Pendant", "Chain", "Other",
]

DIAMOND_QUALITIES = [
    "VVS EF", "VVS GH", "VS EF", "VS FG", "VS GH",
    "SI EF", "SI GH", "Custom",
]

DIAMOND_SHAPES_DEFAULT = [
    "Round", "Princess", "Oval", "Marquise",
    "Pear", "Emerald", "Cushion",
]

CERTIFICATE_TYPES = ["None", "IGI", "GIA","SGL"]
HALLMARK_TYPES    = ["HUID", "BIS", "None"]

GST_RATE = 0.00   # 3% standard for gold jewellery in India

# ── Google Sheet column aliases ───────────────────────────────────────────────
# Handles slight header variations in your diamond price sheet
COL_ALIASES = {
    "sieve":  ["Seive", "Sieve", "Seive SizeMM", "Sieve Size", "SIEVE"],
    "vvs_ef": ["VVS EF (INR)", "VVS EF INR", "VVS EF", "VVSEF(INR)"],
    "vs_ef":  ["VVS VS EF", "VS EF (INR)", "VS EF INR", "VS EF", "VSEF(INR)"],
    "vs_fg":  ["VS FG (INR)", "VS FG INR", "VS FG", "VSFG(INR)"],
}

# ── Global CSS ────────────────────────────────────────────────────────────────
def apply_global_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    }
    [data-testid="stSidebar"] * { color: white !important; }

    /* ── Cards ── */
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        border-left: 4px solid #d4a843;
        margin-bottom: 12px;
    }
    .metric-card h3 {
        margin: 0; font-size: 12px; color: #888;
        font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .metric-card h2 { margin: 4px 0 0; font-size: 26px; color: #1a1a2e; font-weight: 700; }

    /* ── Section headers ── */
    .gold-header {
        background: linear-gradient(135deg, #d4a843, #f0c060);
        color: white !important;
        padding: 6px 16px; border-radius: 8px;
        font-weight: 600; display: inline-block;
        margin-bottom: 14px; font-size: 14px;
    }

    /* ── Total box ── */
    .total-box {
        background: linear-gradient(135deg, #1a1a2e, #0f3460);
        color: white; padding: 24px; border-radius: 12px;
        text-align: center; margin-top: 16px;
    }
    .total-box h1 { margin: 0; font-size: 40px; color: #d4a843 !important; }
    .total-box p  { margin: 6px 0 0; color: #aaa; font-size: 13px; }

    /* ── Image labels ── */
    .img-label {
        font-size: 11px; color: #888; text-align: center;
        margin-top: 4px; font-weight: 500;
        text-transform: uppercase; letter-spacing: 0.4px;
    }

    /* ── Buttons ── */
    .stButton button {
        background: linear-gradient(135deg, #d4a843, #f0c060) !important;
        color: #1a1a2e !important; font-weight: 600 !important;
        border: none !important; border-radius: 8px !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab"] { font-weight: 500; }
    .stTabs [aria-selected="true"] {
        color: #d4a843 !important;
        border-bottom-color: #d4a843 !important;
    }

    /* ── Price source badge ── */
    .price-badge-sheet  { background:#d4edda; color:#155724; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600; }
    .price-badge-manual { background:#fff3cd; color:#856404; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:600; }
    </style>
    """, unsafe_allow_html=True)

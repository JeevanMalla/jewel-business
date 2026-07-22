import streamlit as st

# ── App metadata ──────────────────────────────────────────────────────────────
PAGE_CONFIG = dict(
    page_title="Jewel Manager Pro",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRODUCTION_STAGES = [
    "Requirement Received",
    "CAD Design",
    "Customer CAD Approval",
    "STL / Wax Creation",
    "Casting",
    "Filing",
    "Stone Setting",
    "Polishing",
    "Quality Check",
    "Delivered",
]

PRODUCTION_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "NEED_CHANGES"]

# Stages surfaced as Kanban columns on the Production page.
# Add more stage names here any time — the board just gets wider.
KANBAN_STAGES = ["CAD Design", "STL / Wax Creation", "Casting", "Stone Setting"]

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

# Single source of truth for tax. Both the on-screen totals and the PDF
# tax lines (GST, and the CGST/SGST split on invoices) are derived from
# this, so net + tax always equals gross.
# Set to 0.03 for the standard 3% on gold jewellery in India.
GST_RATE = 0.00

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

    /* ── Sidebar form fields ──────────────────────────────────────────────
       The blanket `color: white` above also hits <input>, which keeps a light
       background — that is what made Gold ₹/gram and Diamond ₹/carat render
       white-on-white and unreadable.

       These fields are deliberately given an explicit WHITE background with
       DARK text rather than white text on a dark field. A dark field only
       stays readable while the sidebar gradient above also applies; if a
       Streamlit upgrade changes the sidebar markup, or the gradient is
       overridden by a theme, white-on-dark silently becomes white-on-white
       again. Dark text on an explicitly white field is readable on ANY
       background, so this cannot regress the same way.

       Selectors cover both the BaseWeb markup and the newer React Aria
       number input (data-testid="stNumberInputField"). */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-testid="stNumberInputField"],
    [data-testid="stSidebar"] [data-baseweb="base-input"],
    [data-testid="stSidebar"] [data-baseweb="input"],
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] [data-testid="stNumberInputContainer"] {
        background-color: #ffffff !important;
        background-image: none !important;
        color: #1a1a2e !important;
        -webkit-text-fill-color: #1a1a2e !important;
        caret-color: #1a1a2e !important;
        border-radius: 8px !important;
    }
    /* One border on the outer field only, so the nested wrappers don't stack. */
    [data-testid="stSidebar"] [data-baseweb="input"],
    [data-testid="stSidebar"] [data-testid="stNumberInputContainer"],
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        border: 1px solid rgba(0,0,0,0.15) !important;
    }
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] [data-testid="stNumberInputField"],
    [data-testid="stSidebar"] [data-baseweb="base-input"] {
        border: none !important;
    }
    [data-testid="stSidebar"] [data-baseweb="input"]:focus-within,
    [data-testid="stSidebar"] [data-testid="stNumberInputContainer"]:focus-within {
        border-color: #d4a843 !important;
        box-shadow: 0 0 0 1px #d4a843 !important;
    }
    [data-testid="stSidebar"] input::placeholder { color: #8a8a99 !important; }
    /* number_input +/- steppers sit on the same white field */
    [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"],
    [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"] {
        background-color: #f0f0f4 !important;
        color: #1a1a2e !important;
        border: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInputStepUp"] svg,
    [data-testid="stSidebar"] [data-testid="stNumberInputStepDown"] svg {
        fill: #1a1a2e !important;
    }
    /* Sidebar buttons use the gold gradient — keep their label dark. */
    [data-testid="stSidebar"] .stButton button,
    [data-testid="stSidebar"] .stButton button * {
        color: #1a1a2e !important;
        -webkit-text-fill-color: #1a1a2e !important;
    }

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

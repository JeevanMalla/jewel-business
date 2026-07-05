"""
services/diamond_sheet.py
Reads diamond price data from Google Sheets.
Each worksheet tab = one diamond shape (Round, Princess, etc.)
"""
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

from config.settings import COL_ALIASES


# ── Google Sheets auth ────────────────────────────────────────────────────────
@st.cache_resource
def _get_gsheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scopes
    )
    return gspread.authorize(creds)


# ── Load all shape tabs ───────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_all_shapes(sheet_id: str) -> dict[str, pd.DataFrame]:
    """
    Returns {tab_name: DataFrame} for every worksheet in the file.
    Cached for 1 hour — call st.cache_data.clear() to force refresh.
    """
    client = _get_gsheet_client()
    ss     = client.open_by_key(sheet_id)
    result = {}
    for ws in ss.worksheets():
        records = ws.get_all_records()
        if records:
            result[ws.title] = pd.DataFrame(records)
    return result


# ── Column finder ─────────────────────────────────────────────────────────────
def _find_col(df_cols: list, aliases: list) -> str | None:
    """Return first column name that matches any alias (case-insensitive)."""
    lower_cols = [c.strip().lower() for c in df_cols]
    for alias in aliases:
        a = alias.strip().lower()
        for i, lc in enumerate(lower_cols):
            if a == lc or a in lc:
                return df_cols[i]
    return None


# ── Price lookup ──────────────────────────────────────────────────────────────
def get_price(
    shape_dfs: dict,
    shape: str,
    sieve: str,
    quality: str,
) -> float | None:
    """
    Look up INR price per carat for shape / sieve / quality.
    Returns float or None if not found.
    """
    # Find the right tab
    df = None
    for tab, tab_df in shape_dfs.items():
        if shape.strip().lower() in tab.strip().lower():
            df = tab_df.copy()
            break
    if df is None:
        return None

    cols      = df.columns.tolist()
    sieve_col = _find_col(cols, COL_ALIASES["sieve"])
    if not sieve_col:
        return None

    # Map quality name → column alias key
    quality_map = {
        "VVS EF": "vvs_ef",
        "VVS GH": "vvs_ef",   # closest fallback
        "VS EF":  "vs_ef",
        "VS FG":  "vs_fg",
        "VS GH":  "vs_fg",
    }
    alias_key = quality_map.get(quality)
    if not alias_key:
        return None

    price_col = _find_col(cols, COL_ALIASES[alias_key])
    if not price_col:
        return None

    # Match sieve row
    df[sieve_col] = df[sieve_col].astype(str).str.strip()
    match = df[df[sieve_col] == str(sieve).strip()]
    if match.empty:
        return None

    try:
        raw = str(match.iloc[0][price_col])
        raw = raw.replace(",", "").replace("₹", "").replace(" ", "")
        return float(raw)
    except Exception:
        return None


# ── Sieve size list ───────────────────────────────────────────────────────────
def get_sieve_sizes(shape_dfs: dict, shape: str) -> list[str]:
    """Return list of sieve sizes available for a given shape tab."""
    for tab, df in shape_dfs.items():
        if shape.strip().lower() in tab.strip().lower():
            sieve_col = _find_col(df.columns.tolist(), COL_ALIASES["sieve"])
            if sieve_col:
                sizes = df[sieve_col].astype(str).str.strip().tolist()
                return [s for s in sizes if s and s.lower() != "nan"]
    return []

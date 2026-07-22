"""
services/estimate_image.py

Renders an estimate as a JPEG that mirrors the spreadsheet-style quote the
workshop already uses: colour-banded sections, a diamond price break-up at the
top, gold / making / certificate / hallmark blocks, and the gross amount in a
dark footer band.

Why an image rather than a PDF: this is the format the estimate is actually
sent in (WhatsApp), where a JPEG previews inline and a PDF does not.

Rupee rendering
---------------
The PDF path uses Helvetica, which has no U+20B9 glyph, so every ₹ came out as
a hollow box. Here the font is resolved at runtime from a list of candidates
across macOS / Linux / Windows, and each is *tested* for the glyph before use.
If nothing on the machine can draw ₹, `RUPEE` degrades to "Rs." rather than
printing a box.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

# ── Palette (sampled from the reference quote) ────────────────────────────────
WHITE   = (255, 255, 255)
BLACK   = (0, 0, 0)
GREY_HD = (217, 217, 217)     # column-header grey
PINK    = (242, 220, 219)     # section band
PEACH   = (252, 213, 180)     # input-ish cells
GREEN   = (216, 228, 188)     # computed value cells
YELLOW  = (255, 255, 0)       # diamond value highlight
BLUE    = (184, 204, 228)     # TCW cell
OLIVE   = (79, 91, 37)        # "Additional information" band
DARK    = (64, 64, 64)        # gross amount band
BORDER  = (128, 128, 128)
RED     = (192, 0, 0)
MUTED   = (128, 128, 128)

# ── Font resolution ───────────────────────────────────────────────────────────
# (regular_path, regular_index, bold_path, bold_index)
# NOTE: Arial and "Arial Unicode" are deliberately absent — neither actually
# contains U+20B9. They were silently drawing .notdef (a hollow box) where the
# rupee should be, which is the original symptom this module has to avoid.
_FONT_CANDIDATES = [
    # Linux (Streamlit Cloud / Debian)
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0,
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", 0,
     "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", 0),
    # macOS — Helvetica.ttc carries Regular at index 0 and Bold at index 1
    ("/System/Library/Fonts/Helvetica.ttc", 0,
     "/System/Library/Fonts/Helvetica.ttc", 1),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0,
     "/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/System/Library/Fonts/SFNS.ttf", 0, "/System/Library/Fonts/SFNS.ttf", 0),
    # Windows
    ("C:/Windows/Fonts/segoeui.ttf", 0, "C:/Windows/Fonts/segoeuib.ttf", 0),
    ("C:/Windows/Fonts/arial.ttf", 0, "C:/Windows/Fonts/arialbd.ttf", 0),
]


def _has_glyph(path: str, index: int, ch: str) -> bool:
    """
    True only if the font really contains `ch`.

    A missing glyph still rasterises — as .notdef, the hollow box — and so
    still has a bounding box. Testing for a non-empty bbox therefore reports
    false positives (this is exactly how Arial slipped through and printed
    boxes). Compare the rendered bitmap against .notdef instead, obtained by
    asking for a private-use codepoint no font defines.
    """
    try:
        f = ImageFont.truetype(path, 24, index=index)
        mark   = f.getmask(ch)
        notdef = f.getmask("")
        if not mark.getbbox():
            return False
        return (mark.size, bytes(mark)) != (notdef.size, bytes(notdef))
    except Exception:
        return False


def _resolve_font_pair():
    """
    First candidate that exists AND genuinely contains ₹. Falls back to any
    font that merely exists (with rupee_ok False, so callers print "Rs."),
    and finally to PIL's bundled default.
    Returns (reg_path, reg_idx, bold_path, bold_idx, rupee_ok).
    """
    fallback = None
    for reg, reg_i, bold, bold_i in _FONT_CANDIDATES:
        if not os.path.exists(reg):
            continue
        if not os.path.exists(bold):
            bold, bold_i = reg, reg_i
        if fallback is None:
            fallback = (reg, reg_i, bold, bold_i)
        if _has_glyph(reg, reg_i, "₹"):
            return reg, reg_i, bold, bold_i, True
    if fallback:
        return (*fallback, False)
    return None, 0, None, 0, False


_REG_PATH, _REG_IDX, _BOLD_PATH, _BOLD_IDX, _RUPEE_OK = _resolve_font_pair()

# Printed currency mark — never a box.
RUPEE = "₹" if _RUPEE_OK else "Rs."


def _font(size: int, bold: bool = False):
    path, idx = (_BOLD_PATH, _BOLD_IDX) if bold else (_REG_PATH, _REG_IDX)
    if not path:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(path, size, index=idx)
    except Exception:
        return ImageFont.load_default()


# ── Number formatting ─────────────────────────────────────────────────────────
def inr_group(value) -> str:
    """
    Indian digit grouping: 143512 -> '1,43,512' (not '143,512').
    This is what the workshop's existing quotes use.
    """
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        n = 0.0
    neg = n < 0
    s = str(int(round(abs(n))))
    if len(s) > 3:
        last3, rest = s[-3:], s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        s = ",".join(groups + [last3])
    return ("-" if neg else "") + s


def money(value) -> str:
    return f"{RUPEE} {inr_group(value)}"


def _num(value, dp=2) -> str:
    try:
        return f"{float(value or 0):,.{dp}f}"
    except (TypeError, ValueError):
        return "0"


# ── Drawing helpers ───────────────────────────────────────────────────────────
def _cell(d, box, text="", fill=None, font=None, color=BLACK,
          align="center", border=True, pad=6):
    """Draw one bordered cell with vertically-centred text."""
    x0, y0, x1, y1 = box
    if fill is not None:
        d.rectangle([x0, y0, x1, y1], fill=fill)
    if border:
        d.rectangle([x0, y0, x1, y1], outline=BORDER, width=1)
    if not text:
        return
    font = font or _font(13)
    bbox = d.textbbox((0, 0), str(text), font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if align == "center":
        tx = x0 + (x1 - x0 - tw) / 2
    elif align == "right":
        tx = x1 - tw - pad
    else:
        tx = x0 + pad
    ty = y0 + (y1 - y0 - th) / 2 - bbox[1]
    d.text((tx, ty), str(text), font=font, fill=color)


def _band(d, box, text, fill, color=BLACK, size=14):
    _cell(d, box, text, fill=fill, font=_font(size, bold=True), color=color)


def _row(d, x, y, widths, cells, h=26, font=None, fills=None,
         aligns=None, colors=None, bold=False):
    """Draw a horizontal run of cells; returns the y of the next row."""
    font = font or _font(13, bold=bold)
    cx = x
    for i, w in enumerate(widths):
        fill  = (fills[i] if fills and i < len(fills) else None)
        align = (aligns[i] if aligns and i < len(aligns) else "center")
        col   = (colors[i] if colors and i < len(colors) else BLACK)
        txt   = cells[i] if i < len(cells) else ""
        _cell(d, (cx, y, cx + w, y + h), txt, fill=fill, font=font,
              color=col, align=align)
        cx += w
    return y + h


def _fetch_image(url, max_w, max_h):
    """Product photo for the right-hand panel. Never fatal."""
    if not url:
        return None
    try:
        import requests
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((max_w, max_h))
        return im
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────
def generate_estimate_jpeg(e: dict, business_name: str = "", quality: int = 92) -> bytes:
    """
    Render the estimate dict (same shape passed to generate_estimation_pdf)
    as a JPEG and return the bytes.
    """
    W       = 1240
    M       = 20                      # outer margin
    CW      = W - 2 * M               # content width
    LEFT_W  = 700                     # left table column
    RIGHT_X = M + LEFT_W + 20

    rows      = e.get("diamond_rows") or []
    n_dia     = max(len(rows), 1)
    # height: diamond block + body + footer, grows with diamond rows
    H = 200 + n_dia * 26 + 620
    img = Image.new("RGB", (W, H), WHITE)
    d   = ImageDraw.Draw(img)

    f_sm   = _font(12)
    f_md   = _font(13)
    f_lbl  = _font(11)
    f_b    = _font(13, bold=True)
    f_hd   = _font(14, bold=True)

    order_date = str(e.get("order_date", ""))
    y = M

    # ── Business name (kept small; the sheet itself is the document) ─────────
    if business_name:
        _cell(d, (M, y, M + CW, y + 26), business_name,
              fill=None, font=_font(15, bold=True), align="left", border=False)
        y += 30

    # ══ Diamond price break-up ═══════════════════════════════════════════════
    first = rows[0] if rows else {}
    shape   = str(first.get("shape", "") or "").upper()
    dqual   = str(first.get("quality", "") or "")
    dtype   = str(first.get("diamond_type", "") or "")
    dtype   = f"({dtype} Diamond)" if dtype and "diamond" not in dtype.lower() else f"({dtype})" if dtype else ""

    hdr_w = [180, 180, 130, 170, 250, 290]
    hdr_w[-1] = CW - sum(hdr_w[:-1])
    y = _row(d, M, y, hdr_w,
             [shape, "Price Break up", dqual, dtype, "", order_date],
             h=26, font=f_hd, fills=[GREY_HD] * 6,
             aligns=["center", "center", "center", "center", "center", "center"])

    col_w = [180, 180, 130, 170, 250, 290]
    col_w[-1] = CW - sum(col_w[:-1])
    y = _row(d, M, y, col_w,
             ["Size", "Weight per pc", "PCS", "TCW", "Price per carat", "Value"],
             h=26, font=f_b, fills=[GREY_HD] * 6)

    tot_pcs = tot_tcw = tot_val = 0.0
    for r in rows:
        pcs  = float(r.get("pcs", 0) or 0)
        tcw  = float(r.get("tcw", 0) or 0)
        val  = float(r.get("value", 0) or 0)
        tot_pcs += pcs
        tot_tcw += tcw
        tot_val += val
        y = _row(d, M, y, col_w, [
                str(r.get("sieve", "") or ""),
                _num(r.get("wt_per_pc", 0), 2),
                f"{int(pcs)}",
                _num(tcw, 2),
                money(r.get("price_per_ct", 0)),
                money(val),
            ], h=26, font=f_md,
            fills=[None, None, PEACH, BLUE, None, YELLOW],
            aligns=["center", "center", "center", "center", "right", "right"])
    if not rows:
        y = _row(d, M, y, col_w, ["—", "—", "0", "0.00", money(0), money(0)],
                 h=26, font=f_md,
                 fills=[None, None, PEACH, BLUE, None, YELLOW],
                 aligns=["center", "center", "center", "center", "right", "right"])

    # totals strip
    y = _row(d, M, y, col_w,
             ["", "", f"{int(e.get('total_pcs', tot_pcs) or 0)}",
              _num(e.get("total_tcw", tot_tcw), 4), "",
              money(e.get("total_diamond_value", tot_val))],
             h=26, font=f_b,
             fills=[None, None, PEACH, BLUE, None, YELLOW],
             aligns=["center", "center", "center", "center", "right", "right"])

    y += 14
    body_top = y

    # ══ Left column ══════════════════════════════════════════════════════════
    lx = M
    # date chip
    _cell(d, (lx, y, lx + 300, y + 24), order_date, fill=PINK, font=f_b)
    y += 34

    def section(title, label_row, value_row, fills_v, band_fill=PINK,
                band_color=BLACK, y0=None):
        """A titled band + a label row + a value row (the repeating pattern)."""
        nonlocal y
        yy = y if y0 is None else y0
        _band(d, (lx, yy, lx + LEFT_W, yy + 24), title, band_fill, band_color)
        yy += 24
        w3 = [LEFT_W // 3, LEFT_W // 3, LEFT_W - 2 * (LEFT_W // 3)]
        yy = _row(d, lx, yy, w3, label_row, h=20, font=f_lbl,
                  fills=[None] * 3, colors=[MUTED] * 3)
        yy = _row(d, lx, yy, w3, value_row, h=26, font=f_md,
                  fills=fills_v,
                  aligns=["center", "center", "right"])
        y = yy + 8
        return yy

    # Gold
    purity_label = str(e.get("gold_purity", "") or "")
    purity_short = purity_label.split(" ")[0] if purity_label else ""
    section(f"{purity_short} Gold",
            ["Price per gram", "Gold weight", "Value"],
            [_num(e.get("gold_price_gram", 0), 2),
             _num(e.get("gold_weight", 0), 3),
             money(e.get("gold_value", 0))],
            [None, PEACH, GREEN])

    # Making
    section("Making",
            ["Price per gram", "Gold weight", "Value"],
            [_num(e.get("making_per_gram", 0), 2),
             _num(e.get("gold_weight", 0), 3),
             money(e.get("making_value", 0))],
            [None, PEACH, GREEN])

    # Additional information
    _band(d, (lx, y, lx + LEFT_W, y + 24), "Additional information", OLIVE, WHITE)
    y += 24
    note = str(e.get("notes", "") or "").strip()
    _cell(d, (lx, y, lx + LEFT_W, y + 26), note, fill=None, font=f_sm,
          align="left", color=BLACK)
    y += 34

    # Certificate
    section("Certificate",
            ["Certificate", "cost", "Value"],
            [str(e.get("cert_type", "") or ""), "",
             money(e.get("cert_cost", 0))],
            [PEACH, None, PEACH])

    # Hallmark — per-article price and count if the estimate carried them
    hm_per  = e.get("hallmark_per")
    hm_arts = e.get("hallmark_arts")
    section("Hallmark",
            ["Per Article Price", "Article", "Value"],
            [_num(hm_per, 2) if hm_per is not None else "",
             _num(hm_arts, 2) if hm_arts is not None else "",
             money(e.get("hallmark_value", 0))],
            [None, PEACH, GREEN])

    # Net / GST
    y += 4
    lbl_w, val_w = 240, LEFT_W - 240
    _cell(d, (lx, y, lx + lbl_w, y + 26), "Net Amount", font=f_b,
          align="right", color=(70, 90, 60), border=False)
    _cell(d, (lx + lbl_w, y, lx + LEFT_W, y + 26),
          money(e.get("net_amount", 0)), font=f_b, align="center")
    y += 26

    net = float(e.get("net_amount", 0) or 0)
    gst = float(e.get("gst_amount", 0) or 0)
    pct = round(gst / net * 100, 2) if net else 0
    _cell(d, (lx, y, lx + lbl_w, y + 26), "Gst", font=f_b,
          align="right", color=(70, 90, 60), border=False)
    _cell(d, (lx + lbl_w, y, lx + LEFT_W, y + 26),
          money(gst), font=f_md, align="center")
    _cell(d, (lx + LEFT_W, y, lx + LEFT_W + 46, y + 26),
          f"{pct:g}%", font=f_sm, align="left", border=False)
    y += 40

    # ══ Right column: 24K reference rate + product photo ═════════════════════
    ry = body_top
    rate_24k = None
    try:
        from config.settings import GOLD_PURITY
        pf = GOLD_PURITY.get(purity_label)
        if pf:
            rate_24k = float(e.get("gold_price_gram", 0) or 0) / pf * 10
    except Exception:
        rate_24k = None

    if rate_24k:
        rw = W - M - RIGHT_X
        _cell(d, (RIGHT_X, ry, RIGHT_X + rw, ry + 22),
              "24K Gold Rate / 10g", fill=None, font=f_lbl,
              color=MUTED, border=False)
        _cell(d, (RIGHT_X, ry + 22, RIGHT_X + rw, ry + 50),
              money(rate_24k), fill=GREEN, font=_font(15, bold=True))
        ry += 62

    photo = _fetch_image(e.get("item_image") or e.get("cad_image"),
                         W - M - RIGHT_X, 330)
    if photo:
        px = RIGHT_X + ((W - M - RIGHT_X) - photo.width) // 2
        img.paste(photo, (px, ry))
        d.rectangle([px, ry, px + photo.width, ry + photo.height],
                    outline=BORDER, width=1)

    # ══ Footer: gross amount + disclaimer ════════════════════════════════════
    y = max(y, ry + (photo.height if photo else 0)) + 16
    gw_lbl = 420
    _cell(d, (M, y, M + gw_lbl, y + 46), "Gross Amount", fill=DARK,
          font=_font(17, bold=True), color=WHITE)
    _cell(d, (M + gw_lbl, y, M + gw_lbl + 380, y + 46),
          money(e.get("gross_amount", 0)), fill=DARK,
          font=_font(22, bold=True), color=WHITE)
    y += 56

    _cell(d, (M, y, M + CW, y + 24),
          "This is an estimated quote, and the prices may vary depending on final CAD",
          fill=None, font=_font(13, bold=True), color=RED, border=False)
    y += 30

    _cell(d, (M, y, M + 300, y + 20), "Engraving", fill=None, font=f_sm,
          align="left", color=BLACK, border=False)
    y += 26

    # trim to content
    img = img.crop((0, 0, W, min(H, y + M)))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, subsampling=0)
    buf.seek(0)
    return buf.read()

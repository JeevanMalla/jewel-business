"""
services/estimate_pdf.py

An aesthetic, branded estimate / quotation PDF for OVURA FINE JEWELLERY.

Design notes
------------
- Palette is sampled from the logo (image.png): deep emerald #102321 and
  gold #D0B078 on cream, so the letterhead band and the logo's own background
  blend seamlessly.
- The logo IS the wordmark (per the brand), so no brand-name text is printed.
- Customer-facing: only SELL prices appear. Every cost / margin / profit field
  on the estimate document is deliberately excluded.
- Rupee: ReportLab's built-in Helvetica has no U+20B9 glyph (that is why the
  old PDF printed a box). A Unicode TTF is registered here; the same
  glyph-aware resolver used by the JPEG path picks a font that genuinely
  contains ₹, and if none does the amount formatter falls back to "Rs.".
- Built with Platypus flowables so long diamond lists paginate cleanly; the
  letterhead is drawn per-page via onFirstPage / onLaterPages.
"""
import io
import os

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from services.estimate_image import (
    _REG_PATH, _REG_IDX, _BOLD_PATH, _BOLD_IDX, inr_group,
)

# ── Palette ───────────────────────────────────────────────────────────────────
EMERALD   = colors.HexColor("#102321")
EMERALD2  = colors.HexColor("#1C463D")
GOLD      = colors.HexColor("#D0B078")
GOLD_DK   = colors.HexColor("#A9834B")
CREAM     = colors.HexColor("#F6F1E7")
CREAM_2   = colors.HexColor("#FBF8F1")
INK       = colors.HexColor("#20211E")
MUTED     = colors.HexColor("#6E7671")
LINE      = colors.HexColor("#E4DAC6")

_LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image.png"
)

# ── Fonts (register a ₹-capable TTF into ReportLab) ───────────────────────────
_BODY, _BOLD = "Helvetica", "Helvetica-Bold"
_SERIF, _SERIF_B = "Helvetica", "Helvetica-Bold"
_HAS_RUPEE = False


def _register_fonts():
    global _BODY, _BOLD, _SERIF, _SERIF_B, _HAS_RUPEE
    if _REG_PATH:
        try:
            pdfmetrics.registerFont(TTFont("OvuraBody", _REG_PATH, subfontIndex=_REG_IDX))
            pdfmetrics.registerFont(TTFont("OvuraBody-Bold", _BOLD_PATH or _REG_PATH,
                                           subfontIndex=_BOLD_IDX))
            _BODY, _BOLD = "OvuraBody", "OvuraBody-Bold"
            # ₹ works only if the registered TTF actually carries the glyph.
            from services.estimate_image import _has_glyph
            _HAS_RUPEE = _has_glyph(_REG_PATH, _REG_IDX, "₹")
        except Exception:
            _BODY, _BOLD, _HAS_RUPEE = "Helvetica", "Helvetica-Bold", False

    # Optional serif for display headings — falls back to the body bold.
    serifs = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 0,
         "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 0),
        ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0,
         "/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 0),
        ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", 0,
         "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", 0),
        ("/Library/Fonts/Georgia.ttf", 0, "/Library/Fonts/Georgia Bold.ttf", 0),
        ("C:/Windows/Fonts/georgia.ttf", 0, "C:/Windows/Fonts/georgiab.ttf", 0),
    ]
    for reg, ri, bold, bi in serifs:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont("OvuraSerif", reg, subfontIndex=ri))
                pdfmetrics.registerFont(TTFont("OvuraSerif-Bold",
                                               bold if os.path.exists(bold) else reg,
                                               subfontIndex=bi))
                _SERIF, _SERIF_B = "OvuraSerif", "OvuraSerif-Bold"
                break
            except Exception:
                continue
    if _SERIF == "Helvetica":            # no serif found — use the body font
        _SERIF, _SERIF_B = _BODY, _BOLD


_register_fonts()
RUPEE = "₹" if _HAS_RUPEE else "Rs."


def _money(v) -> str:
    return f"{RUPEE} {inr_group(v)}"


def _num(v, dp=2) -> str:
    try:
        return f"{float(v or 0):,.{dp}f}"
    except (TypeError, ValueError):
        return "0"


def _sp(text: str) -> str:
    """
    Uppercase eyebrow / label text. Real letter-spacing (a thin space between
    every character) collapses unpredictably at small sizes in the embedded
    TTF, so elegance comes from case + colour + size, not fake tracking.
    """
    return str(text).upper()


# ── Styles ────────────────────────────────────────────────────────────────────
def _styles():
    return {
        "eyebrow": ParagraphStyle("eyebrow", fontName=_BOLD, fontSize=7.5,
                                  textColor=GOLD_DK, leading=10, spaceAfter=2),
        "h": ParagraphStyle("h", fontName=_SERIF_B, fontSize=12.5,
                             textColor=EMERALD, leading=15),
        "body": ParagraphStyle("body", fontName=_BODY, fontSize=9,
                               textColor=INK, leading=13),
        "muted": ParagraphStyle("muted", fontName=_BODY, fontSize=8,
                                textColor=MUTED, leading=11),
        "label": ParagraphStyle("label", fontName=_BOLD, fontSize=7.5,
                                textColor=MUTED, leading=10),
        "val": ParagraphStyle("val", fontName=_BODY, fontSize=10,
                              textColor=INK, leading=13),
        "valb": ParagraphStyle("valb", fontName=_BOLD, fontSize=10,
                               textColor=EMERALD, leading=13),
        "th": ParagraphStyle("th", fontName=_BOLD, fontSize=8,
                             textColor=CREAM, leading=11),
        "td": ParagraphStyle("td", fontName=_BODY, fontSize=8.5,
                             textColor=INK, leading=12),
        "tdr": ParagraphStyle("tdr", fontName=_BODY, fontSize=8.5,
                              textColor=INK, leading=12, alignment=TA_RIGHT),
        "foot": ParagraphStyle("foot", fontName=_BODY, fontSize=7.5,
                               textColor=MUTED, leading=10, alignment=TA_CENTER),
    }


# ── Image loading (URL or local path) ─────────────────────────────────────────
def _load_image_reader(src):
    if not src:
        return None
    try:
        if os.path.exists(src):
            data = open(src, "rb").read()
        elif str(src).startswith(("http://", "https://")):
            import requests
            r = requests.get(src, timeout=10)
            if r.status_code != 200:
                return None
            data = r.content
        else:
            return None
        from PIL import Image as PILImage
        im = PILImage.open(io.BytesIO(data)).convert("RGB")
        return im
    except Exception:
        return None


def _square_crop(pil_im, side_px=900):
    """Centre-crop to a square so the framed card is always tidy."""
    w, h = pil_im.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    im = pil_im.crop((left, top, left + s, top + s))
    if im.width > side_px:
        im.thumbnail((side_px, side_px))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf


# ── Page furniture (drawn per page) ───────────────────────────────────────────
def _first_page(canvas, doc):
    _letterhead(canvas, doc, band_h=54 * mm, big=True)
    _footer(canvas, doc)


def _later_page(canvas, doc):
    _letterhead(canvas, doc, band_h=22 * mm, big=False)
    _footer(canvas, doc)


def _letterhead(canvas, doc, band_h, big):
    W, H = A4
    canvas.saveState()
    # emerald band (matches the logo's own background)
    canvas.setFillColor(EMERALD)
    canvas.rect(0, H - band_h, W, band_h, stroke=0, fill=1)
    # soft highlight to echo the logo's gradient
    canvas.setFillColor(EMERALD2)
    canvas.rect(W * 0.62, H - band_h, W * 0.38, band_h, stroke=0, fill=1)
    canvas.setFillColor(EMERALD)
    canvas.setFillAlpha(0.55)
    canvas.rect(W * 0.62, H - band_h, W * 0.38, band_h, stroke=0, fill=1)
    canvas.setFillAlpha(1)

    # logo, centred, aspect-preserved
    if os.path.exists(_LOGO_PATH):
        try:
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(_LOGO_PATH)
            iw, ih = ir.getSize()
            target_h = band_h * (0.62 if big else 0.70)
            target_w = target_h * iw / ih
            max_w = W * (0.52 if big else 0.34)
            if target_w > max_w:
                target_w = max_w
                target_h = target_w * ih / iw
            canvas.drawImage(ir, (W - target_w) / 2, H - band_h + (band_h - target_h) / 2,
                             width=target_w, height=target_h, mask="auto")
        except Exception:
            pass

    # gold hairline under the band
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.2)
    canvas.line(0, H - band_h, W, H - band_h)
    canvas.setStrokeColor(GOLD_DK)
    canvas.setLineWidth(0.4)
    canvas.line(0, H - band_h - 1.4, W, H - band_h - 1.4)
    canvas.restoreState()


def _footer(canvas, doc):
    W, _ = A4
    canvas.saveState()
    y = 14 * mm
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, y + 6 * mm, W - doc.rightMargin, y + 6 * mm)
    canvas.setFont(_BODY, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(
        W / 2, y + 2.6 * mm,
        "This is an estimated quotation. Final pricing may vary with the final CAD "
        "and prevailing metal & stone rates.")
    canvas.setFont(_BODY, 7)
    canvas.setFillColor(GOLD_DK)
    canvas.drawCentredString(W / 2, y - 1 * mm, "OVURA FINE JEWELLERY")
    canvas.drawRightString(W - doc.rightMargin, y - 1 * mm, f"Page {doc.page}")
    canvas.restoreState()


# ── Reusable blocks ───────────────────────────────────────────────────────────
def _eyebrow(text, st):
    return Paragraph(_sp(text), st["eyebrow"])


def _kv_table(pairs, st, col_w):
    """Label-over-value cells in a clean grid (used for the meta + at-a-glance)."""
    cells = []
    for label, value in pairs:
        cells.append([
            Paragraph(_sp(label), st["label"]),
        ])
    # two-row stack per column looks best as a small table per pair
    data = [[Paragraph(_sp(l), st["label"])] for l, _ in pairs]
    return data


def _meta_block(e, st):
    def cell(label, value):
        return [Paragraph(_sp(label), st["label"]),
                Paragraph(value or "—", st["val"])]
    left = [
        cell("Prepared for", e.get("customer", "")),
        cell("Contact", e.get("phone", "")),
    ]
    right = [
        cell("Estimate no.", e.get("order_id", "")),
        cell("Date", str(e.get("order_date", ""))),
    ]
    # flatten each column into a mini table
    def mini(rows):
        flat = []
        for r in rows:
            flat.append([r[0]])
            flat.append([r[1]])
            flat.append([Spacer(1, 3)])
        t = Table(flat, colWidths=["*"])
        t.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        return t

    outer = Table([[mini(left), mini(right)]], colWidths=["55%", "45%"])
    outer.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return outer


def _hero(e, st, content_w):
    """Item image (left, framed) + at-a-glance specs (right)."""
    pil = _load_image_reader(e.get("item_image") or e.get("customer_image") or e.get("cad_image"))
    img_w = 62 * mm

    if pil:
        buf = _square_crop(pil)
        pic = RLImage(buf, width=img_w, height=img_w)
        cap = Table([[pic],
                     [Paragraph("REFERENCE IMAGE", ParagraphStyle(
                         "cap", fontName=_BOLD, fontSize=6.5, textColor=CREAM,
                         alignment=TA_CENTER, leading=12))]],
                    colWidths=[img_w])
        cap.setStyle(TableStyle([
            ("BACKGROUND", (0, 1), (0, 1), EMERALD),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ("TOPPADDING", (0, 1), (0, 1), 3),
            ("BOTTOMPADDING", (0, 1), (0, 1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOX", (0, 0), (0, 0), 1.2, GOLD),
            ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
        ]))
        left_cell = cap
    else:
        left_cell = Table([[Paragraph("Image will be shared separately", st["muted"])]],
                          colWidths=[img_w], rowHeights=[img_w])
        left_cell.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, LINE),
            ("BACKGROUND", (0, 0), (-1, -1), CREAM_2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

    tcw = e.get("total_tcw", 0)
    glance = [
        ("Item", f"{e.get('item_type','')}".strip() or "—"),
        ("Description", e.get("item_desc", "") or "—"),
        ("Metal", f"{e.get('gold_purity','')}  ·  {e.get('gold_color','')}".strip(" ·")),
        ("Gross gold weight", f"{_num(e.get('gold_weight',0),3)} g"),
        ("Diamonds", f"{int(e.get('total_pcs',0) or 0)} pcs  ·  {_num(tcw,3)} ct"),
        ("Certification", e.get("cert_type", "") or "—"),
    ]
    rows = [[_eyebrow("At a glance", st)], [Spacer(1, 3)]]
    for label, value in glance:
        rows.append([Table(
            [[Paragraph(_sp(label), st["label"]),
              Paragraph(str(value), ParagraphStyle("gv", fontName=_BODY, fontSize=9,
                                                   textColor=INK, alignment=TA_RIGHT,
                                                   leading=12))]],
            colWidths=["45%", "55%"],
        )])
        rows[-1][0].setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
    right = Table(rows, colWidths=["*"])
    right.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    hero = Table([[left_cell, Spacer(1, 1), right]],
                 colWidths=[img_w, 8 * mm, content_w - img_w - 8 * mm])
    hero.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return hero


def _section_title(text, st):
    t = Table([[Paragraph(_sp(text), ParagraphStyle(
        "sect", fontName=_BOLD, fontSize=9, textColor=EMERALD, leading=12))]],
        colWidths=["*"])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 1, GOLD),
    ]))
    return t


def _table(header, rows, col_w, st, right_cols=()):
    data = [[Paragraph(h, st["th"]) for h in header]]
    for r in rows:
        line = []
        for i, cell in enumerate(r):
            if hasattr(cell, "wrap"):            # already a flowable — keep as-is
                line.append(cell)
            else:
                style = st["tdr"] if i in right_cols else st["td"]
                line.append(Paragraph(str(cell), style))
        data.append(line)
    t = Table(data, colWidths=col_w, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), EMERALD),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CREAM_2]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 0.3, LINE),
        ("LINEAFTER", (-1, 0), (-1, -1), 0.3, LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.6, GOLD),
    ]
    return t, style


# ── Public API ────────────────────────────────────────────────────────────────
def generate_estimate_pdf(estimation: dict, business_name: str = "") -> bytes:
    """
    Render a branded estimate/quotation PDF (SELL prices only) and return bytes.
    `estimation` is the same dict shape saved by the Estimation builder.
    """
    e = estimation
    st = _styles()
    buf = io.BytesIO()

    left = right = 16 * mm
    doc = BaseDocTemplate(
        buf, pagesize=A4, leftMargin=left, rightMargin=right,
        topMargin=62 * mm, bottomMargin=24 * mm, title="Estimate", author="OVURA FINE JEWELLERY",
    )
    content_w = A4[0] - left - right
    frame = Frame(left, doc.bottomMargin, content_w,
                  A4[1] - doc.topMargin - doc.bottomMargin, id="main",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame], onPage=_first_page),
        PageTemplate(id="later", frames=[frame], onPage=_later_page),
    ])

    s = []
    # Title
    title = Table([[
        Paragraph("Estimate", ParagraphStyle("title", fontName=_SERIF_B, fontSize=22,
                                              textColor=EMERALD, leading=24)),
        Paragraph(_sp("Quotation"), ParagraphStyle("sub", fontName=_BOLD, fontSize=8,
                                                    textColor=GOLD_DK, alignment=TA_RIGHT,
                                                    leading=24)),
    ]], colWidths=["*", "40%"])
    title.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    s += [title, Spacer(1, 2),
          HRFlowable(width="100%", thickness=0.6, color=LINE), Spacer(1, 8)]

    # Meta
    s += [_meta_block(e, st), Spacer(1, 10)]

    # Hero
    s += [_hero(e, st, content_w), Spacer(1, 14)]

    # Gold
    gold_rows = [[
        e.get("gold_purity", ""), e.get("gold_color", ""),
        _money(e.get("gold_price_gram", 0)), f"{_num(e.get('gold_weight',0),3)} g",
        _money(e.get("gold_value", 0)),
    ]]
    gt, gstyle = _table(
        ["PURITY", "COLOUR", "RATE / GRAM", "WEIGHT", "VALUE"], gold_rows,
        [content_w * w for w in (0.20, 0.22, 0.22, 0.16, 0.20)], st, right_cols=(2, 3, 4))
    gt.setStyle(TableStyle(gstyle))
    s += [KeepTogether([_section_title("Gold", st), Spacer(1, 5), gt]), Spacer(1, 12)]

    # Diamonds
    drows = []
    for r in (e.get("diamond_rows") or []):
        drows.append([
            r.get("label", "") or "—",
            f"{r.get('shape','')} · {r.get('quality','')}".strip(" ·"),
            str(r.get("sieve", "") or "—"),
            str(int(r.get("pcs", 0) or 0)),
            _num(r.get("tcw", 0), 3),
            _money(r.get("price_per_ct", 0)),
            _money(r.get("value", 0)),
        ])
    if drows:
        drows.append([
            "<b>TOTAL</b>", "", "",
            f"<b>{int(e.get('total_pcs',0) or 0)}</b>",
            f"<b>{_num(e.get('total_tcw',0),3)}</b>", "",
            f"<b>{_money(e.get('total_diamond_value',0))}</b>",
        ])
        dt, dstyle = _table(
            ["GROUP", "SHAPE / QUALITY", "SIEVE", "PCS", "TCW (ct)", "RATE / CT", "VALUE"],
            drows, [content_w * w for w in (0.18, 0.24, 0.11, 0.08, 0.13, 0.13, 0.13)],
            st, right_cols=(3, 4, 5, 6))
        dstyle += [
            ("BACKGROUND", (0, -1), (-1, -1), CREAM),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, GOLD),
            ("FONTNAME", (0, -1), (-1, -1), _BOLD),
        ]
        dt.setStyle(TableStyle(dstyle))
        s += [_section_title("Diamonds", st), Spacer(1, 5), dt, Spacer(1, 12)]

    # Making & charges
    charge_rows = [
        ["Making charges", f"{_money(e.get('making_per_gram',0))} / g  ·  "
                           f"{_num(e.get('gold_weight',0),3)} g", _money(e.get("making_value", 0))],
    ]
    if float(e.get("cert_cost", 0) or 0) or e.get("cert_type"):
        charge_rows.append(["Certificate", e.get("cert_type", "") or "—",
                            _money(e.get("cert_cost", 0))])
    if float(e.get("hallmark_value", 0) or 0) or e.get("hallmark_type"):
        hm = e.get("hallmark_type", "") or "—"
        if e.get("hallmark_per") is not None and e.get("hallmark_arts") is not None:
            hm = f"{hm}  ·  {_money(e.get('hallmark_per',0))} × {int(e.get('hallmark_arts',0) or 0)}"
        charge_rows.append(["Hallmark", hm, _money(e.get("hallmark_value", 0))])
    ct, cstyle = _table(
        ["CHARGE", "DETAIL", "VALUE"], charge_rows,
        [content_w * w for w in (0.26, 0.52, 0.22)], st, right_cols=(2,))
    ct.setStyle(TableStyle(cstyle))
    s += [KeepTogether([_section_title("Making & Charges", st), Spacer(1, 5), ct]),
          Spacer(1, 14)]

    # Totals
    net = float(e.get("net_amount", 0) or 0)
    gst = float(e.get("gst_amount", 0) or 0)
    pct = round(gst / net * 100, 2) if net else 0
    tot = Table([
        [Paragraph("Net amount", ParagraphStyle("tl", fontName=_BODY, fontSize=9.5,
                                                textColor=CREAM, alignment=TA_RIGHT)),
         Paragraph(_money(net), ParagraphStyle("tv", fontName=_BODY, fontSize=9.5,
                                               textColor=CREAM, alignment=TA_RIGHT))],
        [Paragraph(f"GST ({pct:g}%)", ParagraphStyle("tl2", fontName=_BODY, fontSize=9.5,
                                                     textColor=CREAM, alignment=TA_RIGHT)),
         Paragraph(_money(gst), ParagraphStyle("tv2", fontName=_BODY, fontSize=9.5,
                                               textColor=CREAM, alignment=TA_RIGHT))],
        [Paragraph(_sp("Total payable"), ParagraphStyle("gl", fontName=_BOLD, fontSize=10,
                                                        textColor=GOLD, alignment=TA_RIGHT)),
         Paragraph(_money(e.get("gross_amount", 0)),
                   ParagraphStyle("gv", fontName=_BOLD, fontSize=16,
                                  textColor=GOLD, alignment=TA_RIGHT))],
    ], colWidths=[content_w * 0.42, content_w * 0.28])
    tot.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), EMERALD),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("LINEBELOW", (0, 0), (-1, 1), 0.4, EMERALD2),
        ("TOPPADDING", (0, 2), (-1, 2), 8), ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    totwrap = Table([[Spacer(1, 1), tot]], colWidths=[content_w * 0.30, content_w * 0.70])
    totwrap.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                 ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    s += [totwrap]

    # Notes
    if str(e.get("notes", "") or "").strip():
        s += [Spacer(1, 12), _section_title("Notes", st), Spacer(1, 4),
              Paragraph(str(e["notes"]).strip(), st["body"])]

    s += [Spacer(1, 16),
          Paragraph("Thank you for considering OVURA FINE JEWELLERY.",
                    ParagraphStyle("ty", fontName=_SERIF, fontSize=10.5,
                                   textColor=EMERALD, alignment=TA_CENTER, leading=14))]

    # Page 1 uses the tall letterhead ("first"); every later page auto-flows
    # onto the compact one. The templates carry their own onPage handlers, so
    # build() just needs the story.
    from reportlab.platypus import NextPageTemplate
    story = [NextPageTemplate("later")] + s
    doc.build(story)
    buf.seek(0)
    return buf.read()

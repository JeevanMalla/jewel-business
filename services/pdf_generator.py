"""
services/pdf_generator.py

Two document types:
  generate_estimation_pdf()  — quote with "ESTIMATION" watermark, disclaimer footer
  generate_invoice_pdf()     — formal tax invoice with invoice number, HSN code, CGST/SGST split

Both handle multi-diamond rows (centre stone + side diamonds etc.)
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, Image as RLImage, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


# ── Colour palette ────────────────────────────────────────────────────────────
GOLD  = colors.HexColor("#d4a843")
DARK  = colors.HexColor("#1a1a2e")
LIGHT = colors.HexColor("#f8f4ef")
GREY  = colors.HexColor("#dddddd")
LGREY = colors.HexColor("#eeeeee")
WHITE = colors.white
RED   = colors.HexColor("#c0392b")


# ── Shared helpers ────────────────────────────────────────────────────────────
def _styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("RightAlign",  alignment=TA_RIGHT,  fontSize=9))
    s.add(ParagraphStyle("CenterAlign", alignment=TA_CENTER, fontSize=9))
    s.add(ParagraphStyle("Small",       fontSize=8,          textColor=colors.HexColor("#666")))
    s.add(ParagraphStyle("SmallCenter", fontSize=8,          alignment=TA_CENTER, textColor=colors.HexColor("#999")))
    s.add(ParagraphStyle("Bold10",      fontSize=10,         fontName="Helvetica-Bold"))
    return s


def _section_header(text: str, styles) -> Table:
    t = Table(
        [[Paragraph(f"<font color='white'><b>{text}</b></font>", styles["Normal"])]],
        colWidths=[180 * mm],
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    return t


def _data_table(rows: list, col_widths: list,
                header_row: bool = False) -> Table:
    t = Table(rows, colWidths=col_widths)
    style = [
        ("FONTSIZE",       (0, 0), (-1, -1), 9),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT]),
        ("BOX",            (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID",      (0, 0), (-1, -1), 0.3, LGREY),
    ]
    if header_row:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style))
    return t


def _build_header(e: dict, doc_type: str, doc_number: str,
                  business_name: str, logo_bytes, styles) -> list:
    """Returns list of flowables for the document header."""
    info_text = (
        f"<font size=9>"
        f"<b>{doc_type} No:</b> {doc_number}<br/>"
        f"<b>Date:</b> {e['order_date']}<br/>"
        f"<b>Due / Delivery:</b> {e['due_date']}"
        f"</font>"
    )
    title_text = (
        f"<font size=18><b>{business_name}</b></font><br/>"
        f"<font size=9 color='#888'>{doc_type}</font>"
    )

    if logo_bytes:
        logo = RLImage(io.BytesIO(logo_bytes), width=35*mm, height=18*mm)
        hrow = [[logo,
                 Paragraph(title_text, styles["Normal"]),
                 Paragraph(info_text,  styles["Normal"])]]
        ht   = Table(hrow, colWidths=[40*mm, None, 65*mm])
    else:
        hrow = [[Paragraph(title_text, styles["Normal"]),
                 Paragraph(info_text,  styles["Normal"])]]
        ht   = Table(hrow, colWidths=[None, 75*mm])

    ht.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (-1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0,  -1), 12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
    ]))
    return [ht, Spacer(1, 5*mm)]


def _build_customer_table(e: dict, styles) -> list:
    ct = Table([
        [Paragraph("<b>Customer</b>", styles["Normal"]), e["customer"],
         Paragraph("<b>Phone</b>",    styles["Normal"]), e.get("phone", "")],
        [Paragraph("<b>Item</b>",     styles["Normal"]), e.get("item_desc", ""),
         Paragraph("<b>Type</b>",     styles["Normal"]), e.get("item_type", "")],
    ], colWidths=[28*mm, 75*mm, 22*mm, 55*mm])
    ct.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",      (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LGREY),
    ]))
    return [ct, Spacer(1, 4*mm)]


def _build_gold_section(e: dict, styles) -> list:
    return [
        _section_header("🥇 Gold Details", styles),
        _data_table([[
            "Purity",  e["gold_purity"],
            "Weight",  f"{e['gold_weight']:.3f} g",
            "Rate/g",  f"₹ {e['gold_price_gram']:,.2f}",
            "Value",   f"₹ {e['gold_value']:,.0f}",
        ]], [35*mm, 38*mm, 22*mm, 26*mm, 22*mm, 26*mm, 18*mm, 28*mm]),
        Spacer(1, 3*mm),
    ]


def _build_diamond_section(e: dict, styles) -> list:
    """Multi-row diamond table — one row per diamond group."""
    rows = e.get("diamond_rows", [])

    header = ["Group / Label", "Type", "Shape", "Sieve", "Quality",
              "PCS", "TCW (ct)", "₹/ct", "Value (₹)"]
    cw     = [32*mm, 18*mm, 18*mm, 14*mm, 14*mm,
              10*mm, 18*mm, 20*mm, 22*mm]

    table_rows = [header]
    for r in rows:
        table_rows.append([
            r.get("label", ""),
            r.get("diamond_type", ""),
            r.get("shape", ""),
            str(r.get("sieve", "")),
            r.get("quality", ""),
            str(r.get("pcs", "")),
            f"{r.get('tcw', 0):.4f}",
            f"₹ {r.get('price_per_ct', 0):,.0f}",
            f"₹ {r.get('value', 0):,.0f}",
        ])

    # Totals row
    table_rows.append([
        Paragraph("<b>TOTAL</b>", styles["Normal"]), "", "", "", "",
        str(e.get("total_pcs", "")),
        f"{e.get('total_tcw', 0):.4f}",
        "",
        Paragraph(f"<b>₹ {e.get('total_diamond_value', 0):,.0f}</b>", styles["Normal"]),
    ])

    t = Table(table_rows, colWidths=cw)
    t.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        # Header
        ("BACKGROUND",  (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR",   (0, 0), (-1, 0), WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT]),
        # Totals row
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0e6c8")),
        ("FONTNAME",   (0, -1), (-1, -1), "Helvetica-Bold"),
        # Grid
        ("BOX",       (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LGREY),
    ]))
    return [
        _section_header("💎 Diamond Details", styles),
        t,
        Spacer(1, 3*mm),
    ]


def _build_making_others(e: dict, styles) -> list:
    return [
        _section_header("🔨 Making & Others", styles),
        _data_table([
            ["Making/g", f"₹ {e['making_per_gram']:,.0f}",
             "Weight",   f"{e['gold_weight']:.3f} g",
             "Making Total", f"₹ {e['making_value']:,.0f}", "", ""],
            ["Certificate", e["cert_type"],
             "Cost",        f"₹ {e['cert_cost']:,.0f}",
             "Hallmark",    e["hallmark_type"],
             "Value",       f"₹ {e['hallmark_value']:,.0f}"],
        ], [25*mm, 35*mm, 22*mm, 28*mm, 28*mm, 26*mm, 18*mm, 28*mm]),
        Spacer(1, 5*mm),
    ]


def _build_totals_table(e: dict, styles, show_tax_split: bool = False) -> list:
    """
    show_tax_split=False → single GST 3% line  (estimation)
    show_tax_split=True  → CGST 1.5% + SGST 1.5% split  (invoice)
    """
    net = e["net_amount"]
    gst = e["gst_amount"]

    if show_tax_split:
        cgst = round(net * 0.015, 0)
        sgst = round(net * 0.015, 0)
        tax_rows = [
            [f"CGST @ 1.5%  (HSN 7113)", f"₹ {cgst:,.0f}"],
            [f"SGST @ 1.5%  (HSN 7113)", f"₹ {sgst:,.0f}"],
        ]
    else:
        tax_rows = [["GST @ 3%", f"₹ {gst:,.0f}"]]

    rows = (
        [["Net Amount", f"₹ {net:,.0f}"]]
        + tax_rows
        + [[
            Paragraph("<b>GROSS AMOUNT</b>", styles["Normal"]),
            Paragraph(
                f"<font size=13 color='#d4a843'><b>₹ {e['gross_amount']:,.0f}</b></font>",
                styles["Normal"],
            ),
        ]]
    )
    t = Table(rows, colWidths=[130*mm, 50*mm])
    t.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("ALIGN",         (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND",    (0, -1), (-1, -1), DARK),
        ("TEXTCOLOR",     (0, -1), (-1, -1), WHITE),
        ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOX",           (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, LGREY),
    ]))
    return [t]


# ── Public API ────────────────────────────────────────────────────────────────
def generate_estimation_pdf(
    estimation: dict,
    business_name: str,
    logo_bytes: bytes | None,
) -> bytes:
    """
    Branded estimation quote PDF.
    Footer says: "This is an estimated quote — prices may vary."
    """
    e      = estimation
    buf    = io.BytesIO()
    styles = _styles()
    doc    = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm,  bottomMargin=15*mm,
    )

    story = []
    story += _build_header(e, "ESTIMATION", e["order_id"], business_name, logo_bytes, styles)
    story += _build_customer_table(e, styles)
    story += _build_gold_section(e, styles)
    story += _build_diamond_section(e, styles)
    story += _build_making_others(e, styles)
    story += _build_totals_table(e, styles, show_tax_split=False)

    if e.get("notes"):
        story += [
            Spacer(1, 4*mm),
            Paragraph(f"<font size=9 color='#666'><b>Notes:</b> {e['notes']}</font>", styles["Normal"]),
        ]

    story += [
        Spacer(1, 6*mm),
        HRFlowable(width="100%", thickness=0.5, color=GREY),
        Spacer(1, 2*mm),
        Paragraph(
            "This is an estimated quote. Prices may vary depending on final CAD and prevailing market rates.",
            styles["SmallCenter"],
        ),
    ]

    doc.build(story)
    buf.seek(0)
    return buf.read()


def generate_invoice_pdf(
    estimation: dict,
    business_name: str,
    logo_bytes: bytes | None,
) -> bytes:
    """
    Formal tax invoice PDF.
    - Invoice number = INV-{order_id}
    - CGST 1.5% + SGST 1.5% split instead of combined GST
    - HSN code 7113 (articles of jewellery)
    - "TAX INVOICE" heading
    - Authorised signature block at bottom
    """
    e          = estimation
    invoice_no = f"INV-{e['order_id']}"
    buf        = io.BytesIO()
    styles     = _styles()
    doc        = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm,  bottomMargin=15*mm,
    )

    story = []
    story += _build_header(e, "TAX INVOICE", invoice_no, business_name, logo_bytes, styles)

    # Invoice meta row (HSN, invoice date)
    meta = Table([[
        Paragraph(f"<font size=9><b>HSN Code:</b> 7113 (Jewellery)</font>", styles["Normal"]),
        Paragraph(f"<font size=9><b>Invoice Date:</b> {e['order_date']}</font>", styles["Normal"]),
        Paragraph(f"<font size=9><b>Invoice No:</b> {invoice_no}</font>",   styles["Normal"]),
    ]], colWidths=[60*mm, 60*mm, 60*mm])
    meta.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f0e6c8")),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",      (0, 0), (-1, -1), 0.5, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LGREY),
    ]))
    story += [meta, Spacer(1, 4*mm)]

    story += _build_customer_table(e, styles)
    story += _build_gold_section(e, styles)
    story += _build_diamond_section(e, styles)
    story += _build_making_others(e, styles)
    story += _build_totals_table(e, styles, show_tax_split=True)

    if e.get("notes"):
        story += [
            Spacer(1, 4*mm),
            Paragraph(f"<font size=9 color='#666'><b>Notes:</b> {e['notes']}</font>", styles["Normal"]),
        ]

    # Signature block
    story += [
        Spacer(1, 12*mm),
        HRFlowable(width="100%", thickness=0.5, color=GREY),
        Spacer(1, 2*mm),
    ]

    sig = Table([[
        Paragraph("<font size=9>Customer Signature</font>", styles["Normal"]),
        Paragraph(
            f"<font size=9>For <b>{business_name}</b><br/><br/>Authorised Signatory</font>",
            ParagraphStyle("RightSig", alignment=TA_RIGHT, fontSize=9),
        ),
    ]], colWidths=[90*mm, 90*mm])
    sig.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 20),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 0),
        ("ALIGN",  (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    story.append(sig)

    story += [
        Spacer(1, 3*mm),
        Paragraph(
            "This is a computer-generated invoice. No separate signature required unless specified.",
            styles["SmallCenter"],
        ),
    ]

    doc.build(story)
    buf.seek(0)
    return buf.read()
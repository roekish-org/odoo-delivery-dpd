# Copyright 2026 ROEKISH
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Specimen label rendered locally by the demo label mode.

No carrier is called: the PDF only shows what a real label would carry so
the whole delivery flow can be demonstrated without a carrier account.
"""

import io

from reportlab.graphics.barcode import code128
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

DEMO_TRACKING_PREFIX = "DEMO"
# Longest line drawn on the 10x15 label before it is cut.
MAX_LINE = 46


def demo_tracking_number(picking):
    """Fake, recognizable tracking number for ``picking``."""
    return "%s%010d" % (DEMO_TRACKING_PREFIX, picking.id)


def is_demo_tracking(reference):
    return (reference or "").startswith(DEMO_TRACKING_PREFIX)


def partner_lines(partner):
    """Postal address of ``partner`` as label lines."""
    company = partner.commercial_company_name
    lines = [
        company if company != partner.name else "",
        partner.name,
        partner.street,
        partner.street2,
        " ".join(filter(None, (partner.zip, partner.city))),
        partner.country_id.name,
    ]
    return [line for line in lines if line]


def render_demo_label(heading, watermark, carrier, sections, tracking, footer):
    """Return a 10x15 PDF specimen label.

    ``sections`` is a list of (title, lines) drawn top to bottom; the
    ``tracking`` number is printed as a Code 128 barcode.
    """
    width, height = 100 * mm, 150 * mm
    margin = 6 * mm
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, height))
    pdf.setTitle(tracking)

    pdf.saveState()
    pdf.setFillGray(0.85)
    pdf.setFont("Helvetica-Bold", 50)
    pdf.translate(width / 2, height / 2)
    pdf.rotate(60)
    pdf.drawCentredString(0, -18, watermark)
    pdf.restoreState()

    pdf.setLineWidth(1.5)
    pdf.rect(margin / 2, margin / 2, width - margin, height - margin)
    y = height - 11 * mm
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(width / 2, y, heading[:MAX_LINE])
    y -= 8 * mm
    # Shrink the carrier title until it fits the label width.
    size = 14
    while size > 8 and pdf.stringWidth(carrier, "Helvetica-Bold", size) > (
        width - 2 * margin
    ):
        size -= 0.5
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(margin, y, carrier[:70])
    y -= 3 * mm
    for title, lines in sections:
        y -= 6 * mm
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(margin, y, title.upper()[:MAX_LINE])
        pdf.setFont("Helvetica", 9)
        for line in lines:
            y -= 4.2 * mm
            pdf.drawString(margin, y, str(line)[:MAX_LINE])

    barcode = code128.Code128(tracking, barHeight=16 * mm, barWidth=0.33 * mm)
    barcode.drawOn(pdf, (width - barcode.width) / 2, 20 * mm)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawCentredString(width / 2, 15 * mm, tracking)
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawCentredString(width / 2, 7 * mm, footer[:70])
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()

"""Small, reusable PDF response helpers for company-scoped operational exports."""

from io import BytesIO
from typing import Iterable, Mapping, Sequence

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value) -> str:
    if value is None:
        return '-'
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def pdf_table_response(
    *,
    title: str,
    filename: str,
    columns: Sequence[tuple[str, str]],
    rows: Iterable[Mapping[str, object]],
    totals: Mapping[str, object] | None = None,
    subtitle: str = '',
) -> HttpResponse:
    """Return a compact, printable table PDF without writing company data to disk."""
    buffer = BytesIO()
    page_size = landscape(A4) if len(columns) > 4 else A4
    document = SimpleDocTemplate(
        buffer, pagesize=page_size, leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=15 * mm, bottomMargin=14 * mm,
        title=title, author='ConstructSaaS',
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('export-title', parent=styles['Heading1'], fontSize=16, leading=19, textColor=colors.HexColor('#10233f'), spaceAfter=3 * mm)
    subtitle_style = ParagraphStyle('export-subtitle', parent=styles['BodyText'], fontSize=8.5, leading=11, textColor=colors.HexColor('#516173'), spaceAfter=5 * mm)
    cell_style = ParagraphStyle('export-cell', parent=styles['BodyText'], fontSize=7.3, leading=9)
    header_style = ParagraphStyle('export-header', parent=cell_style, fontName='Helvetica-Bold', textColor=colors.white)
    total_label_style = ParagraphStyle('export-total-label', parent=cell_style, fontName='Helvetica-Bold')
    total_value_style = ParagraphStyle('export-total-value', parent=cell_style, alignment=TA_RIGHT)

    content = [Paragraph(title, title_style)]
    if subtitle:
        content.append(Paragraph(subtitle, subtitle_style))
    table_data = [[Paragraph(_text(label), header_style) for _, label in columns]]
    for row in rows:
        table_data.append([Paragraph(_text(row.get(key)), cell_style) for key, _ in columns])
    if len(table_data) == 1:
        table_data.append([Paragraph('No records match the selected filters.', cell_style)] + [''] * (len(columns) - 1))
    available_width = page_size[0] - document.leftMargin - document.rightMargin
    widths = [available_width / len(columns)] * len(columns)
    table = Table(table_data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#173b67')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#d7dee8')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f6f8fb')]),
    ]))
    content.append(table)
    if totals:
        content.extend([Spacer(1, 4 * mm), Paragraph('Summary', total_label_style)])
        total_rows = [[Paragraph(_text(key).replace('_', ' ').title(), total_label_style), Paragraph(_text(value), total_value_style)] for key, value in totals.items()]
        totals_table = Table(total_rows, colWidths=[available_width * .65, available_width * .35], hAlign='LEFT')
        totals_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#eef3f8')),
            ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#d7dee8')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        content.append(totals_table)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#65758a'))
        canvas.drawString(document.leftMargin, 8 * mm, 'ConstructSaaS - company operational record')
        canvas.drawRightString(page_size[0] - document.rightMargin, 8 * mm, f'Page {doc.page}')
        canvas.restoreState()

    document.build(content, onFirstPage=footer, onLaterPages=footer)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}.pdf"'
    return response

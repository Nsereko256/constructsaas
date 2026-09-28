"""Read-only, company-scoped move-order documents. No stock is posted by export."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import math
import re
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def clean(value):
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value if value is not None else ''))


def number(value):
    return Decimal(value) if value is not None else None


def display(value):
    if value is None or value == '':
        return '-'
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime('%d %b %Y %H:%M') if timezone.is_aware(value) else value.strftime('%d %b %Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d %b %Y')
    if isinstance(value, Decimal):
        return f'{value:,.2f}'.rstrip('0').rstrip('.')
    return clean(value)


def column_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xlsx_response(*, title, company, filename, sections, metadata=()):
    """Native XLSX, following the existing application's dependency-free export approach.

    Text is always inline text (never a formula); quantities and dates remain typed.
    Each section is a distinct auditable table, with a repeated header and frozen rows.
    """
    output = BytesIO()
    generated = timezone.localtime(timezone.now()).replace(tzinfo=None)

    def cell(ref, value, style=0):
        if isinstance(value, datetime):
            if timezone.is_aware(value):
                value = timezone.localtime(value).replace(tzinfo=None)
            serial = (value - datetime(1899, 12, 30)).total_seconds() / 86400
            return f'<c r="{ref}" s="4"><v>{serial}</v></c>'
        if isinstance(value, date):
            return f'<c r="{ref}" s="3"><v>{(value - date(1899, 12, 30)).days}</v></c>'
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return f'<c r="{ref}" s="2"><v>{value}</v></c>'
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(clean(value))}</t></is></c>'

    styles = '''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="dd mmm yyyy"/><numFmt numFmtId="166" formatCode="dd mmm yyyy hh:mm"/></numFmts>
      <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/></font></fonts>
      <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F7077"/><bgColor indexed="64"/></patternFill></fill></fills>
      <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
      <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
      <cellXfs count="5">
      <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
      <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
      <xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top"/></xf>
      <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
      <xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
      </cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        overrides, sheets, relationships = [], [], []
        for index, (name, headers, data) in enumerate(sections, 1):
            preamble = [[title], ['Company', company], ['Generated', generated]] + list(metadata) + [[]]
            header_row = len(preamble) + 1
            rows = preamble + [headers] + data
            widths = [min(46, max(17, len(str(label)) + 3)) for label in headers]
            widths[0] = max(25, widths[0])
            if len(widths) > 1:
                widths[1] = max(32, widths[1])
            xml_rows = []
            for row_index, values in enumerate(rows, 1):
                height = min(409, max(28, max((math.ceil(len(display(v)) / max(10, widths[min(i, len(widths) - 1)] - 2)) * 15 + 6 for i, v in enumerate(values)), default=28)))
                cells = ''.join(cell(f'{column_name(i)}{row_index}', v, 1 if row_index in {1, header_row} else 0) for i, v in enumerate(values, 1))
                xml_rows.append(f'<row r="{row_index}" ht="{height}" customHeight="1">{cells}</row>')
            last_col = column_name(len(headers))
            cols = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths, 1))
            archive.writestr(f'xl/worksheets/sheet{index}.xml', f'''<?xml version="1.0" encoding="UTF-8"?>
              <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetViews><sheetView workbookViewId="0"><pane ySplit="{header_row}" topLeftCell="A{header_row + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
              <cols>{cols}</cols><sheetData>{''.join(xml_rows)}</sheetData>
              <autoFilter ref="A{header_row}:{last_col}{max(header_row, len(rows))}"/>
              <pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
              <pageSetup orientation="landscape" paperSize="9"/>
              </worksheet>''')
            sheets.append(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>')
            relationships.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
            overrides.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        archive.writestr('[Content_Types].xml', f'''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{''.join(overrides)}</Types>''')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{"".join(sheets)}</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{"".join(relationships)}<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', styles)
    return attachment(output.getvalue(), filename, 'xlsx')


def attachment(content, filename, kind):
    response = HttpResponse(content, content_type='application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}.{kind}"'
    response['Cache-Control'] = 'private, no-store'
    return response


def pdf_response(*, title, company, filename, sections, metadata=()):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=15 * mm, title=title, author=clean(company))
    styles = getSampleStyleSheet()
    body = ParagraphStyle('move-body', parent=styles['BodyText'], fontSize=9, leading=12, spaceAfter=5)
    header = ParagraphStyle('move-header', parent=body, textColor=colors.white, fontName='Helvetica-Bold')
    heading = ParagraphStyle('move-heading', parent=styles['Heading2'], textColor=colors.HexColor('#0f7077'), spaceBefore=12, keepWithNext=True)
    record_heading = ParagraphStyle('move-record', parent=styles['Heading3'], keepWithNext=True)
    para = lambda value, style=body: Paragraph(escape(display(value)).replace('\n', '<br/>'), style)
    story = [para(title, styles['Title']), para(company, heading), para(f'Generated {display(timezone.now())}')]
    short_fields = [(label, value) for label, value in metadata if value is not None and value != '' and len(display(value)) < 100]
    field_rows = []
    for index in range(0, len(short_fields), 2):
        row = [para(f'{label}: {display(value)}') for label, value in short_fields[index:index + 2]]
        field_rows.append(row + [''] * (2 - len(row)))
    if field_rows:
        summary = Table(field_rows, colWidths=[doc.width / 2] * 2, hAlign='LEFT')
        summary.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        story.append(summary)
    story.extend(para(f'{label}: {display(value)}') for label, value in metadata if len(display(value)) >= 100)
    for name, headers, rows in sections:
        section_heading = para(name, heading)
        if not rows:
            story.extend([section_heading, para('No records.')])
            continue
        # Wide audit sections are rendered as readable records, not miniature tables.
        if len(headers) > 8:
            for index, row in enumerate(rows):
                record = ([section_heading] if index == 0 else []) + [para(f'{headers[0]}: {display(row[0])}', record_heading)]
                record.extend(para(f'{label}: {display(value)}') for label, value in zip(headers[1:], row[1:]) if value is not None and value != '')
                story.append(KeepTogether(record))
                story.append(Spacer(1, 4 * mm))
            continue
        story.append(section_heading)
        widths = [doc.width / len(headers)] * len(headers)
        table = Table([[para(h, header) for h in headers]] + [[para(v) for v in row] for row in rows], colWidths=widths, repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f7077')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f7f8')]),
            ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#d9e2e5')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ]))
        story.append(table)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#52636c'))
        canvas.drawString(doc.leftMargin, 8 * mm, 'ConstructSaaS - move order record, not a purchase invoice')
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f'Page {document.page}')
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return attachment(buffer.getvalue(), filename, 'pdf')


def export_detail(*, order, company, kind):
    borrowed = order['ownership'] == 'BORROWED'
    lines = order['lines']
    material_names = {line['id']: f"{line['material_name']} ({line['material_code']}, {line['unit']})" for line in lines}
    metadata = [
        ['Sender', order['sender']], ['Sender reference', order['reference']],
        ['Ownership', 'Borrowed - sender-owned' if borrowed else 'Permanent transfer'],
        ['Warehouse', order['warehouse_name']], ['Stage', order['status']],
        ['Expected arrival', date.fromisoformat(str(order['expected_date']))],
        ['Return due', date.fromisoformat(str(order['return_due_date'])) if order['return_due_date'] else None],
        ['Created by', order['created_by_name']], ['Notes', order['notes']],
    ]
    sections = [('Materials', ['Material / unit', 'Bin', 'Expected', 'Posted receipts', 'Pending approval', 'Still to receive', 'Returned to sender'], [
        [material_names[l['id']], l['bin_code'], *[number(l[key]) for key in ('quantity', 'received', 'pending', 'remaining', 'returned')]] for l in lines])]
    if borrowed:
        sections.append(('Borrowed balances', ['Material / unit', 'Held in warehouse', 'Still owed to sender'], [
            [material_names[l['id']], number(l['held']), number(l['outstanding'])] for l in lines]))
        metadata.append(['Stock treatment', 'Borrowed stock is excluded from owned inventory value. Project issues do not reduce amounts owed.'])
    else:
        sections.append(('Unit values', ['Material / unit', 'Unit value (UGX)', 'Basis'], [
            [material_names[l['id']], number(l['unit_cost']), 'Latest approved value' if number(l['received']) > 0 else 'Proposed value'] for l in lines]))
        metadata.append(['Value treatment', 'Unit values are proposed until approval. Historical posted values are shown per receipt; these are not current stock balances.'])
    receipt_headers = ['Receipt', 'Date', 'Status', 'Material / unit', 'Accepted', 'Damaged', 'Rejected']
    if not borrowed:
        receipt_headers.append('Posted unit value (UGX)')
    receipt_headers += ['Received by', 'Reviewed by', 'Count notes', 'Review reason']
    receipt_rows = []
    for receipt in order['receipts']:
        for line in receipt['lines']:
            row = [receipt['reference'], date.fromisoformat(str(receipt['received_date'])), receipt['status'], material_names[line['order_line']],
                   number(line['accepted']), number(line['damaged']), number(line['rejected'])]
            if not borrowed:
                row.append(number(line['posted_unit_cost']))
            receipt_rows.append(row + [receipt['received_by'], receipt['reviewed_by'], receipt['notes'], receipt['review_reason']])
    sections.append(('Receipts', receipt_headers, receipt_rows))
    history = sorted(((datetime.fromisoformat(event['created_at']), material_names[line['id']], event) for line in lines for event in line['events']), key=lambda row: (row[0], row[2]['id']))
    sections.append(('History', ['Date / time', 'Material / unit', 'Action', 'Quantity', 'Project', 'Actor', 'Reason'], [
        [when, material, event['action'], number(event['quantity']), event['project_name'] or order['warehouse_name'], event['actor'], event['reason']] for when, material, event in history]))
    renderer = pdf_response if kind == 'pdf' else xlsx_response
    return renderer(title=f"Move order MO-{order['id']}", company=company, filename=f"move-order-MO-{order['id']}", metadata=metadata, sections=sections)


def export_register(*, orders, company, kind, filters):
    headers = ['Move order', 'Sender / reference', 'Ownership', 'Warehouse', 'Stage', 'Expected arrival', 'Return due']
    rows = [[f"MO-{o['id']}", f"{o['sender']} / {o['reference']}", 'Borrowed' if o['ownership'] == 'BORROWED' else 'Permanent',
             o['warehouse_name'], o['status'], date.fromisoformat(str(o['expected_date'])),
             date.fromisoformat(str(o['return_due_date'])) if o['return_due_date'] else None] for o in orders]
    renderer = pdf_response if kind == 'pdf' else xlsx_response
    return renderer(title='External move orders', company=company, filename='move-orders',
                    metadata=[['Filters', filters or 'All move orders'], ['Order count', len(rows)]], sections=[('Move orders', headers, rows)])

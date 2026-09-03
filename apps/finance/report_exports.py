import csv
import io
import json
import zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from django.http import HttpResponse

from apps.pdf_exports import pdf_table_response


def _display(value):
    if value is None:
        return ''
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, separators=(',', ':'))
    return str(value)


def csv_response(report, filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    columns = report['columns']
    writer.writerow([column['label'] for column in columns])
    for row in report['rows']:
        writer.writerow([_display(row.get(column['key'])) for column in columns])
    writer.writerow([])
    writer.writerow(['Summary'])
    for key, value in report['totals'].items():
        writer.writerow([key, _display(value)])
    return response


def _cell(reference, value):
    if isinstance(value, (Decimal, int)) and not isinstance(value, bool):
        return f'<c r="{reference}"><v>{escape(_display(value))}</v></c>'
    text = escape(_display(value))
    return f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'


def _column_name(index):
    name = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def xlsx_response(report, filename):
    columns = report['columns']
    table = [[column['label'] for column in columns]]
    table.extend([[row.get(column['key']) for column in columns] for row in report['rows']])
    table.append([])
    table.append(['Summary'])
    table.extend([[key, value] for key, value in report['totals'].items()])

    rows = []
    for row_number, values in enumerate(table, start=1):
        cells = ''.join(
            _cell(f'{_column_name(column_number)}{row_number}', value)
            for column_number, value in enumerate(values, start=1)
        )
        rows.append(f'<row r="{row_number}">{cells}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(rows)}</sheetData></worksheet>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr('[Content_Types].xml', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'
        ))
        workbook.writestr('_rels/.rels', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        workbook.writestr('xl/workbook.xml', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Finance Report" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ))
        workbook.writestr('xl/_rels/workbook.xml.rels', (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ))
        workbook.writestr('xl/worksheets/sheet1.xml', sheet)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
    return response


def pdf_response(report, filename):
    return pdf_table_response(
        title=report['title'],
        filename=filename,
        columns=[(column['key'], column['label']) for column in report['columns']],
        rows=report['rows'],
        totals=report['totals'],
        subtitle='Company-scoped finance report generated from the active filters.',
    )

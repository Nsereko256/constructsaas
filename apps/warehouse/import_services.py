import hashlib
import io
import posixpath
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.finance.configuration_services import record_finance_audit_event
from apps.finance.models import FinanceAuditEvent
from apps.materials.models import Category, Material

from .models import StockMovement, Warehouse
from .valuation_services import record_opening_balance


HEADERS = [
    ('material_code', 'Material code'), ('material_name', 'Material name'),
    ('category', 'Category'), ('unit', 'Unit'), ('warehouse_code', 'Warehouse code'),
    ('opening_quantity', 'Opening quantity'), ('unit_cost', 'Unit cost'),
    ('minimum_stock', 'Minimum stock'), ('description', 'Description'),
]
HEADER_ALIASES = {re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_'): key for key, label in HEADERS}
HEADER_ALIASES.update({key: key for key, _ in HEADERS})
UNIT_ALIASES = {
    'bag': 'bag', 'bags': 'bag', 'ton': 'ton', 'tons': 'ton', 'tonne': 'ton', 'tonnes': 'ton',
    'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg', 'litre': 'litre', 'litres': 'litre',
    'liter': 'litre', 'liters': 'litre', 'piece': 'piece', 'pieces': 'piece', 'pcs': 'piece',
    'metre': 'metre', 'metres': 'metre', 'meter': 'metre', 'meters': 'metre',
    'sqm': 'sqm', 'm2': 'sqm', 'cbm': 'cbm', 'm3': 'cbm',
}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024


def _column_name(index):
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_material_opening_stock_template(rows=None, warehouses=None):
    headers = [label for _, label in HEADERS]
    widths = [18, 28, 20, 14, 20, 18, 16, 18, 34]
    header_cells = ''.join(
        f'<c r="{_column_name(index)}4" s="2" t="inlineStr"><is><t>{escape(label)}</t></is></c>'
        for index, label in enumerate(headers, 1)
    )
    template_rows = rows if rows is not None else [[
        'MAT-001', 'Hima Cement 50kg', 'Cement', 'bag', 'MAIN', 100, 38000, 20,
        'Opening inventory example; replace or remove this row.',
    ]]
    data_xml = []
    for row_number, row in enumerate(template_rows, 5):
        cells = []
        for index, value in enumerate(row, 1):
            reference = f'{_column_name(index)}{row_number}'
            if isinstance(value, (int, float, Decimal)):
                cells.append(f'<c r="{reference}" s="{3 if index in (6, 7, 8) else 0}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        data_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    columns = ''.join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(widths, 1))
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cols>{columns}</cols><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetData>'
        '<row r="1" ht="24"><c r="A1" s="1" t="inlineStr"><is><t>Materials with opening stock</t></is></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>Replace the example row. Use warehouse codes already configured in ConstructSaaS. Supported units: bag, ton, kg, litre, piece, metre, sqm, cbm.</t></is></c></row>'
        f'<row r="4">{header_cells}</row>{"".join(data_xml)}</sheetData>'
        '<autoFilter ref="A4:I1004"/><dataValidations count="1"><dataValidation type="list" allowBlank="0" sqref="D5:D1004"><formula1>"bag,ton,kg,litre,piece,metre,sqm,cbm"</formula1></dataValidation></dataValidations>'
        '</worksheet>'
    )
    styles = ('<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="3"><font><sz val="10"/><name val="Arial"/></font><font><b/><sz val="15"/><color rgb="FF243442"/><name val="Arial"/></font><font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/></font></fonts>'
              '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0F7075"/></patternFill></fill></fills>'
              '<borders count="2"><border/><border><bottom style="thin"><color rgb="FFDCE3E8"/></bottom></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0"/></cellXfs></styleSheet>')
    warehouse_rows = []
    for row_number, warehouse in enumerate(warehouses or [], 3):
        values = [warehouse.code, warehouse.name, warehouse.location or '', 'Yes' if warehouse.is_default else 'No']
        cells = ''.join(
            f'<c r="{_column_name(index)}{row_number}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            for index, value in enumerate(values, 1)
        )
        warehouse_rows.append(f'<row r="{row_number}">{cells}</row>')
    reference_headers = ''.join(
        f'<c r="{_column_name(index)}2" s="2" t="inlineStr"><is><t>{label}</t></is></c>'
        for index, label in enumerate(['Warehouse code', 'Warehouse name', 'Location', 'Default'], 1)
    )
    reference_sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols><col min="1" max="1" width="20" customWidth="1"/><col min="2" max="2" width="30" customWidth="1"/><col min="3" max="3" width="36" customWidth="1"/><col min="4" max="4" width="14" customWidth="1"/></cols>'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        '<sheetData><row r="1"><c r="A1" s="1" t="inlineStr"><is><t>Active company warehouses</t></is></c></row>'
        f'<row r="2">{reference_headers}</row>{"".join(warehouse_rows)}</sheetData></worksheet>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as book:
        book.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        book.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        book.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Materials" sheetId="1" r:id="rId1"/><sheet name="Warehouse reference" sheetId="2" r:id="rId2"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        book.writestr('xl/styles.xml', styles)
        book.writestr('xl/worksheets/sheet1.xml', sheet)
        book.writestr('xl/worksheets/sheet2.xml', reference_sheet)
    return output.getvalue()


def _cell_value(cell, shared_strings, namespace):
    kind = cell.get('t')
    if kind == 'inlineStr':
        return ''.join(node.text or '' for node in cell.findall('.//main:t', namespace)).strip()
    value = cell.findtext('main:v', default='', namespaces=namespace)
    if kind == 's' and value:
        return shared_strings[int(value)].strip()
    return value.strip()


def parse_xlsx(upload):
    raw = upload.read()
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError({'file': ['The workbook must be 5 MB or smaller.']})
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as book:
            names = set(book.namelist())
            if sum(item.file_size for item in book.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError('Workbook contents are too large.')
            if 'xl/workbook.xml' not in names:
                raise ValueError('Workbook metadata is missing.')
            shared = []
            namespace = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            if 'xl/sharedStrings.xml' in names:
                root = ET.fromstring(book.read('xl/sharedStrings.xml'))
                shared = [''.join(node.text or '' for node in item.findall('.//main:t', namespace)) for item in root.findall('main:si', namespace)]
            workbook = ET.fromstring(book.read('xl/workbook.xml'))
            sheet = workbook.find('.//main:sheet', namespace)
            rel_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            rels = ET.fromstring(book.read('xl/_rels/workbook.xml.rels'))
            rel = next(item for item in rels if item.get('Id') == rel_id)
            target = rel.get('Target').lstrip('/')
            sheet_path = target if target.startswith('xl/') else posixpath.normpath(posixpath.join('xl', target))
            root = ET.fromstring(book.read(sheet_path))
            rows = []
            for row in root.findall('.//main:sheetData/main:row', namespace):
                values = {}
                for cell in row.findall('main:c', namespace):
                    match = re.match(r'([A-Z]+)', cell.get('r', ''))
                    if not match:
                        continue
                    index = 0
                    for char in match.group(1):
                        index = index * 26 + ord(char) - 64
                    values[index - 1] = _cell_value(cell, shared, namespace)
                if values:
                    rows.append((int(row.get('r', len(rows) + 1)), [values.get(i, '') for i in range(max(values) + 1)]))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, StopIteration, ValueError, IndexError) as exc:
        raise ValidationError({'file': ['Use a valid .xlsx workbook based on the downloadable template.']}) from exc
    return raw, rows


def _decimal(value, label, errors, *, required=False):
    if value in ('', None):
        if required:
            errors.append(f'{label} is required.')
        return Decimal('0')
    try:
        number = Decimal(str(value).replace(',', '').strip())
    except InvalidOperation:
        errors.append(f'{label} must be a number.')
        return Decimal('0')
    if number < 0:
        errors.append(f'{label} cannot be negative.')
    return number


def validate_material_import(*, user, upload):
    raw, rows = parse_xlsx(upload)
    header_index = None
    headers = {}
    for index, (row_number, values) in enumerate(rows[:20]):
        mapped = {HEADER_ALIASES.get(re.sub(r'[^a-z0-9]+', '_', str(value).lower()).strip('_')): position for position, value in enumerate(values)}
        mapped.pop(None, None)
        if {'material_code', 'material_name', 'category', 'unit', 'warehouse_code', 'opening_quantity', 'unit_cost'}.issubset(mapped):
            header_index, headers = index, mapped
            break
    if header_index is None:
        raise ValidationError({'file': ['The required template headers were not found. Download a fresh template and paste your data into it.']})
    data_rows = rows[header_index + 1:]
    if len(data_rows) > MAX_ROWS:
        raise ValidationError({'file': [f'Import at most {MAX_ROWS} rows at a time.']})
    company = user.company
    warehouses = {item.code.casefold(): item for item in Warehouse.objects.filter(company=company, is_active=True)}
    categories = {item.name.casefold(): item for item in Category.objects.filter(company=company)}
    materials_by_code = {item.code.casefold(): item for item in Material.objects.filter(company=company)}
    materials_by_name = {item.name.casefold(): item for item in Material.objects.filter(company=company)}
    seen_locations = set()
    seen_materials = {}
    seen_names = {}
    preview = []
    for row_number, values in data_rows:
        def value(key):
            position = headers.get(key)
            return str(values[position]).strip() if position is not None and position < len(values) else ''
        if not any(value(key) for key, _ in HEADERS):
            continue
        code, name, category_name = value('material_code').upper(), value('material_name'), value('category')
        unit = UNIT_ALIASES.get(value('unit').casefold(), '')
        warehouse_code = value('warehouse_code').upper()
        errors = []
        if not code: errors.append('Material code is required.')
        if not name: errors.append('Material name is required.')
        if not category_name: errors.append('Category is required.')
        if not unit: errors.append('Unit is not supported.')
        if not warehouse_code: errors.append('Warehouse code is required.')
        material_key = code.casefold()
        location_key = (material_key, warehouse_code.casefold())
        if location_key in seen_locations:
            errors.append('This material and warehouse combination is duplicated in the workbook.')
        seen_locations.add(location_key)
        prior_definition = seen_materials.get(material_key)
        if prior_definition and prior_definition != (name.casefold(), category_name.casefold(), unit):
            errors.append('Rows using the same material code must use the same name, category and unit.')
        elif material_key:
            seen_materials[material_key] = (name.casefold(), category_name.casefold(), unit)
        prior_code = seen_names.get(name.casefold())
        if prior_code and prior_code != material_key:
            errors.append('Rows using the same material name must use the same material code.')
        elif name:
            seen_names[name.casefold()] = material_key
        warehouse = warehouses.get(warehouse_code.casefold())
        if not warehouse: errors.append('Warehouse code does not match an active company warehouse.')
        material = materials_by_code.get(code.casefold())
        name_match = materials_by_name.get(name.casefold())
        if name_match and not material: errors.append(f'Material name already exists with code {name_match.code}.')
        if material and material.name.casefold() != name.casefold(): errors.append(f'Code belongs to existing material “{material.name}”.')
        if material and unit and material.unit != unit: errors.append(f'Existing material uses unit “{material.unit}”.')
        if material and category_name and material.category.name.casefold() != category_name.casefold():
            errors.append(f'Existing material belongs to category “{material.category.name}”.')
        quantity = _decimal(value('opening_quantity'), 'Opening quantity', errors, required=True)
        unit_cost = _decimal(value('unit_cost'), 'Unit cost', errors, required=quantity > 0)
        minimum = _decimal(value('minimum_stock'), 'Minimum stock', errors)
        if material and warehouse and quantity > 0 and StockMovement.objects.filter(company=company, material=material, warehouse=warehouse).exists():
            errors.append('Opening stock is blocked because this material/location already has ledger activity.')
        preview.append({
            'row': row_number, 'material_code': code, 'material_name': name, 'category': category_name,
            'unit': unit or value('unit'), 'warehouse_code': warehouse_code,
            'opening_quantity': str(quantity), 'unit_cost': str(unit_cost), 'minimum_stock': str(minimum),
            'description': value('description'), 'material_status': 'Existing' if material else 'New',
            'category_status': 'Existing' if category_name.casefold() in categories else 'New', 'errors': errors,
        })
    if not preview:
        raise ValidationError({'file': ['No material rows were found.']})
    return raw, preview


@transaction.atomic
def confirm_material_import(*, user, upload, opening_date: date, reason):
    # Serialize company onboarding imports so concurrent uploads cannot create
    # duplicate case-variant categories/materials or race the empty-ledger guard.
    user.company.__class__.objects.select_for_update().get(pk=user.company_id)
    raw = upload.read()
    file_hash = hashlib.sha256(raw).hexdigest()
    if FinanceAuditEvent.objects.filter(company=user.company, action='inventory.opening_stock.imported', object_id=file_hash).exists():
        raise ValidationError({'file': ['This workbook has already been imported.']})
    upload.seek(0)
    raw, rows = validate_material_import(user=user, upload=upload)
    errors = [row for row in rows if row['errors']]
    if errors:
        raise ValidationError({'rows': errors, 'detail': 'Correct every row error before confirming the import.'})
    created_materials = created_categories = opening_balances = 0
    for row in rows:
        category = Category.objects.filter(company=user.company, name__iexact=row['category']).first()
        if category is None:
            category = Category.objects.create(company=user.company, name=row['category'])
            created_categories += 1
        material = Material.objects.filter(company=user.company, code__iexact=row['material_code']).first()
        if not material:
            material = Material.objects.create(
                company=user.company, category=category, name=row['material_name'], code=row['material_code'],
                unit=row['unit'], unit_price=row['unit_cost'], min_stock_level=row['minimum_stock'],
                description=row['description'],
            )
            created_materials += 1
        warehouse = Warehouse.objects.get(company=user.company, code__iexact=row['warehouse_code'], is_active=True)
        if Decimal(row['opening_quantity']) > 0:
            record_opening_balance(
                user=user, material=material, warehouse=warehouse, quantity=row['opening_quantity'],
                unit_cost=row['unit_cost'], date=opening_date, reason=reason,
            )
            opening_balances += 1
    summary = {'rows': len(rows), 'materials_created': created_materials, 'materials_matched': len(rows) - created_materials, 'categories_created': created_categories, 'opening_balances': opening_balances}
    record_finance_audit_event(
        company=user.company, actor=user, action='inventory.opening_stock.imported', object_type='InventoryImport',
        object_id=file_hash, message=f'Imported {len(rows)} material rows with {opening_balances} opening balances.',
        metadata={**summary, 'filename': upload.name, 'opening_date': str(opening_date), 'file_hash': file_hash},
    )
    return summary

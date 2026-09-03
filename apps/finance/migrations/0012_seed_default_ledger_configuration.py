from django.db import migrations


ACCOUNTS = (
    ('1000', 'Cash and Bank', 'ASSET', 'CASH'),
    ('1200', 'Inventory', 'ASSET', 'INVENTORY'),
    ('1300', 'Supplier Advances', 'ASSET', 'SUPPLIER_ADVANCE'),
    ('1400', 'Staff Advances', 'ASSET', 'STAFF_ADVANCE'),
    ('2100', 'GRN Clearing', 'LIABILITY', 'GRN_CLEARING'),
    ('2000', 'Accounts Payable', 'LIABILITY', 'ACCOUNTS_PAYABLE'),
    ('5100', 'Inventory Adjustments', 'EXPENSE', 'INVENTORY_ADJUSTMENT'),
    ('5200', 'Inventory Write-offs', 'EXPENSE', 'INVENTORY_WRITE_OFF'),
    ('5300', 'Landed Cost Clearing', 'LIABILITY', 'LANDED_COST_CLEARING'),
    ('5000', 'Project Material Cost', 'EXPENSE', 'PROJECT_COST'),
)

MAPPINGS = {
    'CASH': 'CASH',
    'INVENTORY': 'INVENTORY',
    'SUPPLIER_ADVANCE': 'SUPPLIER_ADVANCE',
    'STAFF_ADVANCE': 'STAFF_ADVANCE',
    'GRN_CLEARING': 'GRN_CLEARING',
    'ACCOUNTS_PAYABLE': 'ACCOUNTS_PAYABLE',
    'PROJECT_MATERIAL_COST': 'PROJECT_COST',
    'INVENTORY_ADJUSTMENT': 'INVENTORY_ADJUSTMENT',
    'INVENTORY_WRITE_OFF': 'INVENTORY_WRITE_OFF',
    'LANDED_COST_CLEARING': 'LANDED_COST_CLEARING',
    'PROJECT_EXPENSE': 'PROJECT_COST',
    'PETTY_CASH': 'CASH',
}

RULES = (
    ('GRN_RECEIPT', 'GRN inventory receipt', 'INVENTORY', 'GRN_CLEARING'),
    ('SUPPLIER_INVOICE', 'Supplier invoice', 'GRN_CLEARING', 'ACCOUNTS_PAYABLE'),
    ('SUPPLIER_PAYMENT', 'Supplier payment', 'ACCOUNTS_PAYABLE', 'CASH'),
    ('PROJECT_ISSUE', 'Material issue to project', 'PROJECT_MATERIAL_COST', 'INVENTORY'),
    ('INVENTORY_ADJUSTMENT', 'Inventory adjustment', 'INVENTORY', 'INVENTORY_ADJUSTMENT'),
    ('INVENTORY_WRITE_OFF', 'Inventory write-off', 'INVENTORY_WRITE_OFF', 'INVENTORY'),
    ('SUPPLIER_RETURN', 'Supplier return', 'GRN_CLEARING', 'INVENTORY'),
    ('CREDIT_NOTE', 'Supplier credit note', 'ACCOUNTS_PAYABLE', 'INVENTORY'),
    ('LANDED_COST', 'Landed cost', 'INVENTORY', 'LANDED_COST_CLEARING'),
    ('PROJECT_EXPENSE', 'Project expense', 'PROJECT_EXPENSE', 'CASH'),
    ('PETTY_CASH', 'Petty-cash transaction', 'PETTY_CASH', 'CASH'),
)


def seed_configuration(apps, schema_editor):
    Company = apps.get_model('accounts', 'Company')
    Account = apps.get_model('finance', 'Account')
    AccountMapping = apps.get_model('finance', 'AccountMapping')
    PostingRule = apps.get_model('finance', 'PostingRule')
    for company in Company.objects.iterator():
        accounts = {}
        for code, name, account_type, system_key in ACCOUNTS:
            account = Account.objects.filter(company=company, system_key=system_key).first()
            if not account:
                available_code = code
                suffix = 1
                while Account.objects.filter(company=company, code=available_code).exists():
                    suffix += 1
                    available_code = f'{code}-L{suffix}'
                account = Account.objects.create(
                    company=company,
                    system_key=system_key,
                    code=available_code,
                    name=name,
                    account_type=account_type,
                )
            accounts[system_key] = account
        for mapping_key, system_key in MAPPINGS.items():
            AccountMapping.objects.get_or_create(
                company=company,
                mapping_key=mapping_key,
                defaults={'account': accounts[system_key]},
            )
        for event_type, name, debit_key, credit_key in RULES:
            PostingRule.objects.get_or_create(
                company=company,
                event_type=event_type,
                defaults={
                    'name': name,
                    'debit_mapping_key': debit_key,
                    'credit_mapping_key': credit_key,
                },
            )


class Migration(migrations.Migration):
    dependencies = [('finance', '0011_alter_journalentry_status')]

    operations = [migrations.RunPython(seed_configuration, migrations.RunPython.noop)]

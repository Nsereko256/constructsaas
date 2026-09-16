import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.finance.models import FinanceAuditEvent
from apps.materials.models import Category, Material

from .import_services import build_material_opening_stock_template
from .models import StockMovement, Warehouse


class MaterialOpeningStockImportApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Opening Stock Import Co', slug='opening-stock-import')
        self.storekeeper = User.objects.create_user(
            username='opening-stock-storekeeper', password='pass', company=self.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.procurement = User.objects.create_user(
            username='opening-stock-procurement', password='pass', company=self.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.admin = User.objects.create_user(
            username='opening-stock-admin', password='pass', company=self.company,
            role=User.ROLE_ADMIN,
        )
        self.main = Warehouse.objects.create(
            company=self.company, name='Main Warehouse', code='MAIN', is_default=True,
        )
        self.secondary = Warehouse.objects.create(
            company=self.company, name='Secondary Warehouse', code='SECONDARY',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.storekeeper)

    @staticmethod
    def workbook(rows, name='opening-stock.xlsx'):
        return SimpleUploadedFile(
            name,
            build_material_opening_stock_template(rows=rows),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def row(self, *, code='CEM-001', name='Cement 50kg', category='Cement', unit='bag', warehouse='MAIN', quantity=10, cost=35000, minimum=2):
        return [code, name, category, unit, warehouse, quantity, cost, minimum, 'Verified onboarding count.']

    def submit_and_approve(self, rows, name='opening-stock.xlsx'):
        submitted = self.client.post(
            '/api/materials/opening-stock-import-confirm/',
            {
                'file': self.workbook(rows, name=name),
                'opening_date': str(timezone.localdate()),
                'reason': 'Verified company onboarding stock count.',
            },
            format='multipart',
        )
        self.assertEqual(submitted.status_code, 202, submitted.data)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 0)
        self.client.force_authenticate(self.admin)
        approved = self.client.post(
            '/api/materials/opening-stock-import-approve/',
            {'confirmation_id': submitted.data['confirmation_id'], 'comments': 'Verified against the signed onboarding count.'},
        )
        self.client.force_authenticate(self.storekeeper)
        return approved

    def test_template_and_import_actions_are_restricted_to_storekeepers_and_admins(self):
        response = self.client.get('/api/materials/opening-stock-template/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'PK'))
        self.assertIn('materials-opening-stock-template.xlsx', response['Content-Disposition'])
        with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
            reference = workbook.read('xl/worksheets/sheet2.xml').decode('utf-8')
        self.assertIn('MAIN', reference)
        self.assertIn('SECONDARY', reference)
        self.assertIn('Main Warehouse', reference)

        self.client.force_authenticate(self.procurement)
        denied = self.client.post(
            '/api/materials/opening-stock-import-preview/',
            {'file': self.workbook([self.row()])},
            format='multipart',
        )
        self.assertEqual(denied.status_code, 403)

    def test_preview_is_non_destructive_and_reports_resolution(self):
        response = self.client.post(
            '/api/materials/opening-stock-import-preview/',
            {'file': self.workbook([self.row()])},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['valid_rows'], 1)
        self.assertEqual(response.data['invalid_rows'], 0)
        self.assertEqual(response.data['new_materials'], 1)
        self.assertEqual(response.data['new_categories'], 1)
        self.assertEqual(Material.objects.filter(company=self.company).count(), 0)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 0)

    def test_only_admin_can_approve_and_post_opening_stock(self):
        submitted = self.client.post(
            '/api/materials/opening-stock-import-confirm/',
            {
                'file': self.workbook([self.row()]),
                'opening_date': str(timezone.localdate()),
                'reason': 'Verified company onboarding stock count.',
            },
            format='multipart',
        )
        self.assertEqual(submitted.status_code, 202, submitted.data)

        denied = self.client.post(
            '/api/materials/opening-stock-import-approve/',
            {'confirmation_id': submitted.data['confirmation_id']},
        )
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 0)

        self.client.force_authenticate(self.admin)
        approved = self.client.post(
            '/api/materials/opening-stock-import-approve/',
            {
                'confirmation_id': submitted.data['confirmation_id'],
                'comments': 'Verified against the signed onboarding count.',
            },
        )
        self.assertEqual(approved.status_code, 201, approved.data)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 1)

    def test_confirm_creates_material_once_and_posts_balances_to_each_warehouse(self):
        rows = [
            self.row(warehouse='MAIN', quantity=10, cost=35000),
            self.row(warehouse='SECONDARY', quantity=4, cost=36000),
        ]
        response = self.submit_and_approve(rows)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['materials_created'], 1)
        self.assertEqual(response.data['materials_matched'], 1)
        self.assertEqual(response.data['categories_created'], 1)
        self.assertEqual(response.data['opening_balances'], 2)
        material = Material.objects.get(company=self.company, code='CEM-001')
        self.assertEqual(material.category.name, 'Cement')
        movements = StockMovement.objects.filter(company=self.company, material=material)
        self.assertEqual(movements.count(), 2)
        self.assertEqual(set(movements.values_list('transaction_type', flat=True)), {StockMovement.TRANSACTION_OPENING})
        self.assertEqual(set(movements.values_list('warehouse__code', flat=True)), {'MAIN', 'SECONDARY'})
        self.assertTrue(FinanceAuditEvent.objects.filter(
            company=self.company, action='inventory.opening_stock.imported',
        ).exists())

    def test_reimporting_the_same_workbook_is_idempotently_rejected(self):
        workbook_bytes = build_material_opening_stock_template(rows=[self.row()])
        payload = {
            'opening_date': str(timezone.localdate()),
            'reason': 'Verified company onboarding stock count.',
        }
        first = self.submit_and_approve([self.row()], name='opening.xlsx')
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post(
            '/api/materials/opening-stock-import-confirm/',
            {**payload, 'file': SimpleUploadedFile('opening.xlsx', workbook_bytes)},
            format='multipart',
        )
        self.assertEqual(second.status_code, 400)
        self.assertIn('already been imported', str(second.data))
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 1)

    def test_invalid_row_blocks_the_entire_import(self):
        rows = [self.row(), self.row(code='STEEL-001', name='Rebar', category='Steel', unit='ton', warehouse='UNKNOWN')]
        response = self.client.post(
            '/api/materials/opening-stock-import-confirm/',
            {
                'file': self.workbook(rows),
                'opening_date': str(timezone.localdate()),
                'reason': 'Verified company onboarding stock count.',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Material.objects.filter(company=self.company).count(), 0)
        self.assertEqual(Category.objects.filter(company=self.company).count(), 0)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 0)

    def test_warehouse_and_existing_ledger_validation_are_company_scoped(self):
        other = Company.objects.create(name='Other Import Co', slug='other-import')
        Warehouse.objects.create(company=other, name='Other Warehouse', code='OTHER', is_default=True)
        wrong_company = self.client.post(
            '/api/materials/opening-stock-import-preview/',
            {'file': self.workbook([self.row(warehouse='OTHER')])},
            format='multipart',
        )
        self.assertEqual(wrong_company.status_code, 200)
        self.assertEqual(wrong_company.data['invalid_rows'], 1)
        self.assertIn('active company warehouse', ' '.join(wrong_company.data['rows'][0]['errors']))

        confirmed = self.submit_and_approve([self.row()])
        self.assertEqual(confirmed.status_code, 201, confirmed.data)
        conflict = self.client.post(
            '/api/materials/opening-stock-import-preview/',
            {'file': self.workbook([self.row(quantity=3, cost=36000)], name='changed-opening.xlsx')},
            format='multipart',
        )
        self.assertEqual(conflict.status_code, 200)
        self.assertEqual(conflict.data['invalid_rows'], 1)
        self.assertIn('ledger activity', ' '.join(conflict.data['rows'][0]['errors']))

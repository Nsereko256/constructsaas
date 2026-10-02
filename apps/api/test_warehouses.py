import io
import zipfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.materials.models import Material
from apps.warehouse.import_services import build_material_opening_stock_template
from apps.warehouse.models import Warehouse, StockMovement


class WarehouseOnboardingTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Warehouse onboarding QA')
        self.other = Company.objects.create(name='Other warehouse company')
        self.admin = User.objects.create_user(username='warehouse-admin', company=self.company, role=User.ROLE_ADMIN)
        self.store = User.objects.create_user(username='warehouse-store', company=self.company, role=User.ROLE_STOREKEEPER)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def register(self, code='MAIN', **kwargs):
        return self.client.post('/api/warehouses/', {'name': 'Receiving warehouse', 'code': code, 'is_default': True, **kwargs}, format='json')

    def test_register_normalizes_code_and_rejects_duplicate(self):
        response = self.register(' main ')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['code'], 'MAIN')
        self.assertEqual(response.data['company'], self.company.pk)
        duplicate = self.register('Main')
        self.assertEqual(duplicate.status_code, 400, duplicate.data)
        self.assertIn('code', duplicate.data)
        self.assertEqual(Warehouse.objects.filter(company=self.company).count(), 1)
        ready = self.client.get('/api/company-readiness/').data
        warehouse = next(row for row in ready['checks'] if row['key'] == 'warehouse')
        self.assertEqual(warehouse['status'], 'ready')
        self.assertEqual(warehouse['href'], '/inventory/warehouses')

    def test_only_admin_can_register_or_change_warehouse(self):
        warehouse = self.register().data
        self.client.force_authenticate(self.store)
        self.assertEqual(self.register('NEW').status_code, 403)
        self.assertEqual(self.client.patch(f"/api/warehouses/{warehouse['id']}/", {'name': 'Changed'}).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouses/').status_code, 200)

    def test_company_scope_and_default_switch_preserve_existing_warehouse(self):
        foreign = Warehouse.objects.create(company=self.other, name='Foreign', code='MAIN', is_default=True)
        first = self.register(company=self.other.pk).data
        second = self.register('SECOND').data
        self.assertEqual(Warehouse.objects.get(pk=first['id']).is_default, False)
        self.assertTrue(Warehouse.objects.get(pk=second['id']).is_default)
        foreign.refresh_from_db()
        self.assertTrue(foreign.is_default)
        self.assertEqual(self.client.patch(f'/api/warehouses/{foreign.pk}/', {'name': 'No'}).status_code, 404)
        listed = self.client.get('/api/warehouses/').data['results']
        self.assertEqual({row['id'] for row in listed}, {first['id'], second['id']})
        denied = self.client.patch(f"/api/warehouses/{second['id']}/", {'is_active': False}, format='json')
        self.assertEqual(denied.status_code, 400)
        self.assertTrue(Warehouse.objects.get(pk=second['id']).is_active)

    def test_invalid_default_creation_rolls_back_default_switch(self):
        first = self.register().data
        response = self.register('FAIL', is_active=False)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Warehouse.objects.get(pk=first['id']).is_default)
        self.assertFalse(Warehouse.objects.filter(code='FAIL').exists())

    def test_blank_company_to_warehouse_excel_import_and_admin_posting(self):
        rows = [['ONBOARD-CEM', 'Onboarding cement', 'Cement', 'bag', 'ONBOARD', 12, 35000, 2, 'Physical count']]
        workbook = build_material_opening_stock_template(rows=rows)

        def upload():
            return SimpleUploadedFile('onboarding.xlsx', workbook, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        self.client.force_authenticate(self.store)
        preview = self.client.post('/api/materials/opening-stock-import-preview/', {'file': upload()}, format='multipart')
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data['invalid_rows'], 1)
        self.assertIn('Warehouse code', ' '.join(preview.data['rows'][0]['errors']))
        self.client.force_authenticate(self.admin)
        created = self.register('ONBOARD')
        self.assertEqual(created.status_code, 201, created.data)
        template = self.client.get('/api/materials/opening-stock-template/')
        with zipfile.ZipFile(io.BytesIO(template.content)) as archive:
            self.assertIn('ONBOARD', archive.read('xl/worksheets/sheet2.xml').decode())
        self.client.force_authenticate(self.store)
        preview = self.client.post('/api/materials/opening-stock-import-preview/', {'file': upload()}, format='multipart')
        self.assertEqual(preview.data['invalid_rows'], 0, preview.data)
        self.assertEqual(Material.objects.filter(company=self.company).count(), 0)
        submitted = self.client.post('/api/materials/opening-stock-import-confirm/', {'file': upload(), 'opening_date': timezone.localdate().isoformat(), 'reason': 'Verified onboarding count'}, format='multipart')
        self.assertEqual(submitted.status_code, 202, submitted.data)
        self.assertFalse(StockMovement.objects.filter(company=self.company).exists())
        payload = {'confirmation_id': submitted.data['confirmation_id'], 'comments': 'Independent Admin verified physical stock.'}
        self.assertEqual(self.client.post('/api/materials/opening-stock-import-approve/', payload, format='json').status_code, 403)
        self.client.force_authenticate(self.admin)
        posted = self.client.post('/api/materials/opening-stock-import-approve/', payload, format='json')
        self.assertEqual(posted.status_code, 201, posted.data)
        movement = StockMovement.objects.get(company=self.company)
        self.assertEqual(movement.warehouse_id, created.data['id'])
        self.assertEqual(movement.quantity_effect, Decimal('12'))
        self.assertEqual(movement.value_effect, Decimal('420000'))
        self.assertEqual(self.client.post('/api/materials/opening-stock-import-approve/', payload, format='json').status_code, 400)
        self.assertEqual(StockMovement.objects.filter(company=self.company).count(), 1)

from decimal import Decimal
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User

from ..factories import FinanceFixtureFactory
from ..models import (
    FinanceAuditEvent,
    InvoiceApproval,
    InvoiceAttachment,
    JournalEntry,
    SupplierCreditNote,
    SupplierInvoice,
    TaxCode,
)


class SupplierPayablesApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('AP')
        self.other = FinanceFixtureFactory('APX')
        self.po, self.po_item = self.fixture.received_purchase_order()
        self.tax = TaxCode.objects.create(
            company=self.fixture.company, code='VAT18', name='VAT 18%', rate_percent=Decimal('18.0000'),
        )
        self.client = APIClient()
        self.media = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        self.media.cleanup()

    def payload(self, *, number=None, quantity=None, key='ap-invoice', taxes=True):
        item = {
            'purchase_order_item': self.po_item.pk,
            'quantity': str(quantity or self.po_item.quantity),
            'unit_price': str(self.po_item.unit_price),
            'tax_amount': '999999.99',
        }
        if taxes:
            item['taxes'] = [{'tax_code': self.tax.pk}]
        return {
            'supplier': self.fixture.supplier.pk,
            'purchase_order': self.po.pk,
            'invoice_number': number or f'INV-{key}',
            'invoice_date': str(timezone.localdate()),
            'currency': 'UGX',
            'exchange_rate': '1.000000',
            'discount_amount': '10000.00',
            'withholding_amount': '3000.00',
            'subtotal': '1.00',
            'tax_amount': '1.00',
            'total_amount': '1.00',
            'idempotency_key': key,
            'items': [item],
        }

    def create_invoice(self, **kwargs):
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post('/api/v1/finance/supplier-invoices/', self.payload(**kwargs), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def post_invoice(self, **kwargs):
        response = self.create_invoice(**kwargs)
        invoice_id = response.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/').status_code, 200)
        verified = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/verify/',
            {'idempotency_key': f'verify-{invoice_id}'}, format='json',
        )
        self.assertEqual(verified.status_code, 201, verified.data)
        self.assertEqual(verified.data['status'], 'MATCHED')
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/approve/').status_code, 200)
        posted = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/post/',
            {'idempotency_key': f'post-{invoice_id}'}, format='json',
        )
        self.assertEqual(posted.status_code, 201, posted.data)
        return invoice_id, posted

    def test_server_calculates_configured_multiple_tax_totals(self):
        local_tax = TaxCode.objects.create(
            company=self.fixture.company, code='LEVY2', name='Levy', rate_percent=Decimal('2.0000'),
        )
        payload = self.payload()
        payload['items'][0]['taxes'].append({'tax_code': local_tax.pk})
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post('/api/v1/finance/supplier-invoices/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['subtotal'], '350000.00')
        self.assertEqual(response.data['tax_amount'], '70000.00')
        self.assertEqual(response.data['total_amount'], '407000.00')
        self.assertEqual(len(response.data['items'][0]['taxes']), 2)

    def test_supplier_invoice_preparation_is_reserved_for_finance_officer(self):
        procurement_officer = User.objects.create_user(
            username='ap-procurement', password='password', company=self.fixture.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.client.force_authenticate(procurement_officer)

        response = self.client.post(
            '/api/v1/finance/supplier-invoices/', self.payload(key='procurement-blocked'), format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_duplicate_supplier_invoice_number_is_rejected(self):
        self.create_invoice(number='DUP-1', key='dup-one')
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post(
            '/api/v1/finance/supplier-invoices/', self.payload(number=' dup-1 ', key='dup-two'), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue('non_field_errors' in response.data or 'invoice_number' in response.data)

    def test_withdraw_and_draft_line_update_recalculate_totals(self):
        created = self.create_invoice(taxes=False)
        invoice_id = created.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/').status_code, 200)
        withdrawn = self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/withdraw-submission/')
        self.assertEqual(withdrawn.status_code, 200, withdrawn.data)
        payload = {'discount_amount': '0.00', 'withholding_amount': '0.00', 'items': [{
            'purchase_order_item': self.po_item.pk, 'quantity': '4.00',
            'unit_price': '35000.00', 'taxes': [],
        }]}
        updated = self.client.patch(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/', payload, format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['total_amount'], '140000.00')
        self.assertEqual(InvoiceApproval.objects.filter(invoice_id=invoice_id).count(), 2)

    def test_partial_invoices_verify_against_remaining_received_quantity(self):
        first = self.create_invoice(number='PART-1', quantity=Decimal('4.00'), key='part-1')
        first_id = first.data['id']
        self.client.post(f'/api/v1/finance/supplier-invoices/{first_id}/submit/')
        first_verify = self.client.post(f'/api/v1/finance/supplier-invoices/{first_id}/verify/', {}, format='json')
        self.assertEqual(first_verify.data['status'], 'MATCHED')

        second = self.create_invoice(number='PART-2', quantity=Decimal('6.00'), key='part-2')
        second_id = second.data['id']
        self.client.post(f'/api/v1/finance/supplier-invoices/{second_id}/submit/')
        second_verify = self.client.post(f'/api/v1/finance/supplier-invoices/{second_id}/verify/', {}, format='json')
        self.assertEqual(second_verify.data['status'], 'MATCHED')

    def test_post_is_idempotent_and_approved_invoice_rejects_patch(self):
        invoice_id, first = self.post_invoice(key='postable')
        second = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/post/',
            {'idempotency_key': f'post-{invoice_id}'}, format='json',
        )
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(JournalEntry.objects.filter(source_type='INVOICE', source_object_id=invoice_id).count(), 1)
        self.client.force_authenticate(self.fixture.finance_officer)
        patch = self.client.patch(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/', {'notes': 'illegal'}, format='json',
        )
        self.assertEqual(patch.status_code, 400)
        self.assertTrue(FinanceAuditEvent.objects.filter(object_id=str(invoice_id), action='invoice.post').exists())

    def test_credit_note_is_calculated_posted_and_read_only(self):
        invoice_id, _ = self.post_invoice(key='creditable')
        response = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/create-credit-note/',
            {
                'credit_note_number': 'CN-100', 'credit_note_date': str(timezone.localdate()),
                'reason': 'Damaged bag', 'idempotency_key': 'credit-100',
                'items': [{'invoice_item': SupplierInvoice.objects.get(pk=invoice_id).items.get().pk,
                           'quantity': '1.00', 'unit_price': '35000.00', 'tax_code': self.tax.pk}],
            }, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_amount'], '41300.00')
        self.assertEqual(response.data['status'], SupplierCreditNote.STATUS_POSTED)
        self.assertIn(self.client.patch(
            f"/api/v1/finance/supplier-credit-notes/{response.data['id']}/", {'reason': 'changed'}, format='json',
        ).status_code, {403, 405})

    def test_attachment_metadata_hides_storage_path_and_is_company_isolated(self):
        invoice_id = self.create_invoice(key='attachment').data['id']
        upload = SimpleUploadedFile(b'invoice.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        response = self.client.post(
            '/api/v1/finance/invoice-attachments/', {'invoice': invoice_id, 'file': upload}, format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn('file', response.data)
        self.assertNotIn(self.media.name, str(response.data))
        attachment_id = response.data['id']
        self.assertEqual(InvoiceAttachment.objects.get(pk=attachment_id).company, self.fixture.company)
        self.client.force_authenticate(self.other.finance_viewer)
        self.assertEqual(
            self.client.get(f'/api/v1/finance/invoice-attachments/{attachment_id}/download/').status_code, 404,
        )

    def test_finance_viewer_is_read_only(self):
        self.client.force_authenticate(self.fixture.finance_viewer)
        self.assertEqual(self.client.get('/api/v1/finance/supplier-invoices/').status_code, 200)
        self.assertEqual(
            self.client.post('/api/v1/finance/supplier-invoices/', self.payload(), format='json').status_code, 403,
        )

import json

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .notification_services import check_finance_deadlines_for_company
from .permissions import FinanceAdminPermission
from .serializers import (
    DraftJournalSerializer,
    ExpenseClaimSerializer,
    LandedCostDocumentSerializer,
    PaymentSerializer,
    ProjectBudgetSerializer,
    StaffAdvanceSerializer,
    SupplierInvoiceSerializer,
)
from .sync_serializers import FinanceDeadlineCheckSerializer, FinanceDraftSyncSerializer
from .sync_services import atomic_sync, begin_draft_sync, finish_draft_sync


SYNC_SERIALIZERS = {
    'project_budget': ProjectBudgetSerializer,
    'supplier_invoice': SupplierInvoiceSerializer,
    'payment': PaymentSerializer,
    'landed_cost': LandedCostDocumentSerializer,
    'expense_claim': ExpenseClaimSerializer,
    'staff_advance': StaffAdvanceSerializer,
    'journal_entry': DraftJournalSerializer,
}

IDEMPOTENT_DOCUMENTS = {
    'supplier_invoice', 'payment', 'expense_claim', 'staff_advance',
}


def _json_safe(value):
    return json.loads(JSONRenderer().render(value).decode('utf-8'))


class FinanceDraftSyncAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['Finance - Offline synchronization'],
        summary='Synchronize one offline finance draft',
        description=(
            'Creates or version-checks and updates a draft using a client UUID and idempotency key. '
            'Approvals, posting, overrides, reversals, and all non-draft records are rejected.'
        ),
        request=FinanceDraftSyncSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        envelope = FinanceDraftSyncSerializer(data=request.data)
        envelope.is_valid(raise_exception=True)
        values = envelope.validated_data
        record_type = values['record_type']
        client_uuid = values['client_uuid']
        idempotency_key = values['idempotency_key']
        expected_version = values.get('version')
        document_data = dict(values['data'])

        with atomic_sync():
            state = begin_draft_sync(
                user=request.user,
                record_type=record_type,
                client_uuid=client_uuid,
                idempotency_key=idempotency_key,
                version=expected_version,
                data=document_data,
            )
            if 'replay' in state:
                replay = dict(state['replay'])
                replay['replayed'] = True
                return Response(replay)

            sync_user = state['user']
            request.user = sync_user
            instance = state['instance']
            serializer_data = dict(document_data)
            serializer_data['client_uuid'] = str(client_uuid)
            if record_type in IDEMPOTENT_DOCUMENTS:
                serializer_data['idempotency_key'] = f'sync:{client_uuid}'
            document_serializer = SYNC_SERIALIZERS[record_type](
                instance,
                data=serializer_data,
                context={'request': request},
            )
            document_serializer.is_valid(raise_exception=True)
            document = document_serializer.save()
            response_status = 201 if instance is None else 200
            response_data = {
                'replayed': False,
                'operation': 'created' if instance is None else 'updated',
                'record_type': record_type,
                'client_uuid': str(client_uuid),
                'version': document.version,
                'data': document_serializer.data,
            }
            safe_response = _json_safe(response_data)
            finish_draft_sync(
                user=sync_user,
                record_type=record_type,
                client_uuid=client_uuid,
                idempotency_key=idempotency_key,
                request_hash_value=state['request_hash'],
                response_data=safe_response,
                response_status=response_status,
            )
        return Response(response_data, status=response_status)


class FinanceDeadlineCheckAPIView(APIView):
    permission_classes = [FinanceAdminPermission]

    @extend_schema(
        tags=['Finance - Notifications'],
        summary='Publish due-invoice and overdue-advance notifications',
        description='Authenticated server action intended for manual use or a future external scheduler.',
        request=FinanceDeadlineCheckSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        payload = FinanceDeadlineCheckSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        notifications = check_finance_deadlines_for_company(
            request.user.company, **payload.validated_data,
        )
        return Response({
            'created_count': len(notifications),
            'notification_ids': [notification.pk for notification in notifications],
        })

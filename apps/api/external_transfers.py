from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.warehouse import external_services as service
from apps.warehouse.models import ExternalMoveOrder
from apps.warehouse.external_exports import export_detail, export_register
from .permissions import HasCompanyAndRole


class ExternalTransferPermission(HasCompanyAndRole):
    allowed_roles = service.OPERATORS | {'finance_manager', 'finance_officer', 'finance_viewer'}


class MoveLineInput(serializers.Serializer):
    material = serializers.IntegerField(min_value=1)
    bin_location = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('.01'))
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal(0), default=Decimal(0))


class MoveOrderInput(serializers.Serializer):
    sender = serializers.CharField(max_length=160)
    reference = serializers.CharField(max_length=100)
    ownership = serializers.ChoiceField(choices=['PERMANENT', 'BORROWED'])
    warehouse = serializers.IntegerField(min_value=1)
    expected_date = serializers.DateField()
    return_due_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    lines = MoveLineInput(many=True, allow_empty=False, max_length=100)


class ReceiptLineInput(serializers.Serializer):
    order_line = serializers.IntegerField(min_value=1)
    accepted = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal(0), default=Decimal(0))
    damaged = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal(0), default=Decimal(0))
    rejected = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal(0), default=Decimal(0))


class ReceiptInput(serializers.Serializer):
    reference = serializers.CharField(max_length=100)
    received_date = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    lines = ReceiptLineInput(many=True, allow_empty=False, max_length=100)


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=4000)


class ReviewInput(ReasonInput):
    receipt_id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=['post', 'reject'])
    costs = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal(0)), required=False)


class ReverseInput(ReasonInput):
    receipt_id = serializers.IntegerField(min_value=1)


class StockActionInput(ReasonInput):
    line_id = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=['ISSUE', 'PROJECT_RETURN', 'OWNER_RETURN'])
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('.01'))
    request_key = serializers.UUIDField()
    project = serializers.IntegerField(min_value=1, required=False, allow_null=True)


def actor_name(user):
    return user.get_full_name() or user.username


class MoveOrderOutput(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name')
    created_by_name = serializers.SerializerMethodField()
    lines = serializers.SerializerMethodField()
    receipts = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    pending_receipts = serializers.SerializerMethodField()

    class Meta:
        model = ExternalMoveOrder
        fields = ['id', 'sender', 'reference', 'ownership', 'warehouse', 'warehouse_name', 'expected_date',
                  'return_due_date', 'notes', 'closed', 'created_at', 'created_by_name', 'status', 'pending_receipts', 'lines', 'receipts']

    def get_created_by_name(self, obj):
        return actor_name(obj.created_by)

    def get_pending_receipts(self, obj):
        return sum(r.status == 'PENDING' for r in obj.receipts.all())

    def get_status(self, obj):
        if self.get_pending_receipts(obj):
            return 'Awaiting admin'
        if obj.closed:
            return 'Closed to receipts'
        lines = list(obj.lines.all())
        accepted = [service.line_balances(line)['received'] for line in lines]
        if all(q >= line.quantity for q, line in zip(accepted, lines)):
            return 'Fully received'
        return 'Part received' if any(accepted) else 'Awaiting receipt'

    def get_lines(self, obj):
        data = []
        for line in obj.lines.all():
            balances = service.line_balances(line)
            pending = sum((i.accepted for i in line.receipt_lines.all() if i.receipt.status == 'PENDING'), Decimal(0))
            events = [{
                'id': event.pk, 'action': event.get_action_display(), 'quantity': str(event.quantity),
                'project': event.project_id, 'project_name': event.project.name if event.project_id else '',
                'reason': event.reason, 'actor': actor_name(event.actor), 'created_at': event.created_at.isoformat(),
            } for event in line.events.all()]
            data.append({
                'id': line.pk, 'material': line.material_id, 'material_name': line.material.name,
                'material_code': line.material.code, 'unit': line.material.unit, 'bin_location': line.bin_location_id,
                'bin_code': line.bin_location.code if line.bin_location_id else '',
                'quantity': str(line.quantity), 'unit_cost': str(line.unit_cost),
                'received': str(balances['received']), 'pending': str(pending),
                'remaining': str(max(Decimal(0), line.quantity - balances['received'] - pending)),
                'held': str(balances['held']) if obj.ownership == 'BORROWED' else None,
                'outstanding': str(balances['outstanding']) if obj.ownership == 'BORROWED' else None,
                'returned': str(balances['returned']),
                'projects': {str(k): str(v) for k, v in balances['projects'].items() if v}, 'events': events,
            })
        return data

    def get_receipts(self, obj):
        return [{
            'id': receipt.pk, 'reference': receipt.reference, 'status': receipt.status,
            'received_date': receipt.received_date, 'received_by': actor_name(receipt.received_by),
            'reviewed_by': actor_name(receipt.reviewed_by) if receipt.reviewed_by_id else '',
            'reviewed_at': receipt.reviewed_at, 'notes': receipt.notes, 'review_reason': receipt.review_reason,
            'lines': [{'order_line': item.order_line_id, 'accepted': str(item.accepted), 'damaged': str(item.damaged),
                       'rejected': str(item.rejected), 'movement': item.movement_id,
                       'posted_unit_cost': str(item.movement.unit_cost) if item.movement_id else None,
                       'reversal': item.reversal_id} for item in receipt.lines.all()],
        } for receipt in obj.receipts.all()]


class ExternalMoveOrderViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ExternalTransferPermission]
    serializer_class = MoveOrderOutput
    http_method_names = ['get', 'post', 'head', 'options']
    filter_backends = []

    def get_queryset(self):
        qs = ExternalMoveOrder.objects.filter(company=self.request.user.company).select_related('warehouse', 'created_by').prefetch_related(
            'lines__material', 'lines__bin_location', 'lines__events__project', 'lines__events__actor',
            'lines__receipt_lines__receipt', 'receipts__lines__movement', 'receipts__received_by', 'receipts__reviewed_by')
        if self.action in {'list', 'download_register'}:
            search = self.request.query_params.get('search', '').strip()
            if search:
                qs = qs.filter(Q(sender__icontains=search) | Q(reference__icontains=search) | Q(lines__material__name__icontains=search)).distinct()
            ownership = self.request.query_params.get('ownership')
            if ownership in {'PERMANENT', 'BORROWED'}:
                qs = qs.filter(ownership=ownership)
            if self.request.query_params.get('pending') == 'true':
                qs = qs.filter(receipts__status='PENDING').distinct()
            if self.request.query_params.get('project_site'):
                qs = qs.filter(warehouse__project_site_id=self.request.query_params['project_site'])
        return qs

    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download_register(self, request, kind=None):
        orders = self.get_serializer(self.get_queryset(), many=True).data
        filters = ', '.join(f'{key}: {request.query_params[key]}' for key in ('search', 'ownership', 'pending', 'project_site') if request.query_params.get(key))
        return export_register(orders=orders, company=request.user.company.name, kind=kind, filters=filters)

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        return export_detail(order=self.get_serializer(self.get_object()).data, company=request.user.company.name, kind=kind)

    def create(self, request):
        data = MoveOrderInput(data=request.data)
        data.is_valid(raise_exception=True)
        order = service.create_order(user=request.user, **data.validated_data)
        return Response(self.get_serializer(order).data, status=201)

    def execute(self, request, input_class, handler):
        order = self.get_object()
        data = input_class(data=request.data)
        data.is_valid(raise_exception=True)
        handler(user=request.user, order_id=order.pk, **data.validated_data)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        return self.execute(request, ReceiptInput, service.confirm_receipt)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        return self.execute(request, ReviewInput, service.review_receipt)

    @action(detail=True, methods=['post'], url_path='stock-action')
    def stock_action(self, request, pk=None):
        return self.execute(request, StockActionInput, service.stock_action)

    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        return self.execute(request, ReverseInput, service.reverse_receipt)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        return self.execute(request, ReasonInput, service.close_order)

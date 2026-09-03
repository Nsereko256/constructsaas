from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from apps.finance.budget_services import budget_line_summary, money
from apps.finance.models import BudgetApproval, BudgetTransaction


class PurchaseOrderAmendmentSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    amendment_type = serializers.CharField(read_only=True)
    reason = serializers.CharField(read_only=True)
    original_values = serializers.JSONField(read_only=True)
    proposed_values = serializers.JSONField(read_only=True)
    status = serializers.CharField(read_only=True)
    submitted_by = serializers.IntegerField(source='submitted_by_id', read_only=True)
    decided_by = serializers.IntegerField(source='decided_by_id', read_only=True)
    decision_reason = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    decided_at = serializers.DateTimeField(read_only=True)
    budget_impact = serializers.SerializerMethodField()

    def get_budget_impact(self, amendment):
        """Give Finance an explicit before/after budget view before deciding."""
        original_items = amendment.original_values.get('items', [])
        original_total = money(sum((
            Decimal(str(item.get('quantity', 0))) * Decimal(str(item.get('unit_price', 0)))
            for item in original_items
        ), Decimal('0')))
        proposed = amendment.proposed_values
        if 'items' in proposed:
            projected_total = money(sum((
                Decimal(str(item.get('quantity', 0))) * Decimal(str(item.get('unit_price', 0)))
                for item in proposed['items']
            ), Decimal('0')))
        else:
            price_delta = sum((
                Decimal(str(item.get('proposed_line_total', 0))) - Decimal(str(item.get('original_line_total', 0)))
                for item in proposed.get('price_lines', [])
            ), Decimal('0'))
            projected_total = money(original_total + price_delta)

        approval = BudgetApproval.objects.filter(
            company_id=amendment.company_id,
            purchase_request_id=amendment.purchase_order.purchase_request_id,
            budget_line__isnull=False,
        ).select_related('budget_line__category').first()
        result = {
            'current_po_total': str(original_total),
            'proposed_po_total': str(projected_total),
            'change_amount': str(money(projected_total - original_total)),
            'has_budget_line': bool(approval),
        }
        if not approval:
            return result

        current_commitment = money(BudgetTransaction.objects.filter(
            purchase_order_id=amendment.purchase_order_id,
            transaction_type__in=[BudgetTransaction.TYPE_COMMITMENT, BudgetTransaction.TYPE_COMMITMENT_RELEASE],
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0'))
        summary = budget_line_summary(approval.budget_line)
        available_before = money(summary['available_balance'])
        result.update({
            'budget_line_name': str(approval.budget_line),
            'available_before': str(available_before),
            'current_po_commitment': str(current_commitment),
            'projected_available_after': str(money(available_before + current_commitment - projected_total)),
            'budget_override': approval.status == BudgetApproval.STATUS_OVERRIDDEN,
        })
        return result


class PurchaseOrderAmendmentRequestSerializer(serializers.Serializer):
    reason = serializers.CharField()
    supplier = serializers.IntegerField(required=False)
    delivery_destination = serializers.ChoiceField(choices=['WAREHOUSE', 'SITE'], required=False)
    expected_delivery_date = serializers.DateField(required=False, allow_null=True)
    # Notes are a controlled commercial change and must remain visible to
    # Finance instead of being silently discarded as an unknown field.
    notes = serializers.CharField(required=False, allow_blank=True)
    # Price amendments reference immutable PO line IDs. Quantities and
    # materials remain unchanged, protecting the approved scope and matching.
    price_lines = serializers.ListField(child=serializers.DictField(), required=False)
    items = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, attrs):
        if len(attrs) == 1:
            raise serializers.ValidationError('Provide at least one changed value.')
        if 'items' in attrs and not attrs['items']:
            raise serializers.ValidationError({'items': 'Provide at least one PO line when changing items.'})
        if 'price_lines' in attrs and not attrs['price_lines']:
            raise serializers.ValidationError({'price_lines': 'Provide at least one changed price line.'})
        return attrs


class PurchaseOrderPreApprovalEditSerializer(serializers.Serializer):
    """Commercial corrections before the PO's first Finance approval."""
    expected_delivery_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    price_lines = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Provide at least one value to update.')
        if 'price_lines' in attrs and not attrs['price_lines']:
            raise serializers.ValidationError({'price_lines': 'Provide at least one price line.'})
        return attrs


class PurchaseOrderAmendmentDecisionSerializer(serializers.Serializer):
    comments = serializers.CharField(required=True)

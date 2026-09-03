from rest_framework import serializers


FINANCE_DRAFT_TYPES = [
    'project_budget',
    'supplier_invoice',
    'payment',
    'landed_cost',
    'expense_claim',
    'staff_advance',
    'journal_entry',
]


class FinanceDraftSyncSerializer(serializers.Serializer):
    record_type = serializers.ChoiceField(choices=FINANCE_DRAFT_TYPES)
    client_uuid = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)
    version = serializers.IntegerField(required=False, min_value=1)
    data = serializers.JSONField()

    def validate_data(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError('Must be a JSON object.')
        forbidden = {
            'company', 'client_uuid', 'version',
            'status', 'approved_by', 'approved_at', 'posted_by', 'posted_at',
            'reversal_of', 'reviewed_by', 'reviewed_at',
        }
        supplied = sorted(forbidden.intersection(value))
        if supplied:
            raise serializers.ValidationError(
                f'Workflow fields cannot be synchronized: {", ".join(supplied)}.'
            )
        return value


class FinanceDeadlineCheckSerializer(serializers.Serializer):
    as_of = serializers.DateField(required=False)
    due_soon_days = serializers.IntegerField(required=False, min_value=0, max_value=90, default=7)

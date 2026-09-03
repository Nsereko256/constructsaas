from rest_framework import serializers


class PurchaseOrderDeliveryUpdateSerializer(serializers.Serializer):
    supplier_confirmed_delivery_date = serializers.DateField(required=False, allow_null=True)
    revised_delivery_date = serializers.DateField(required=False, allow_null=True)
    delivery_revision_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs.get('revised_delivery_date') and not attrs.get('delivery_revision_reason', '').strip():
            raise serializers.ValidationError({'delivery_revision_reason': 'Explain the revised delivery date.'})
        return attrs

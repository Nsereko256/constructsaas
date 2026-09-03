from decimal import Decimal

from django.db.models import Case, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce


def annotate_project_costs(queryset):
    from apps.procurement.models import GoodsReceivedNote, GoodsReceivedNoteItem, PurchaseOrder
    from apps.warehouse.models import StockMovement

    cost_field = DecimalField(max_digits=16, decimal_places=2)
    warehouse_costs = (
        StockMovement.objects.filter(
            project_id=OuterRef('pk'),
            transaction_type__in=[
                StockMovement.TRANSACTION_PROJECT_ISSUE,
                StockMovement.TRANSACTION_PROJECT_RETURN,
            ],
        )
        .values('project_id')
        .annotate(total=Sum(Case(
            When(transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE, then=F('total_cost')),
            default=-F('total_cost'),
            output_field=cost_field,
        )))
        .values('total')[:1]
    )

    # Direct-to-site cost is based on accepted GRN quantities, not the full PO
    # quantity. Rejected and damaged goods must not become project cost merely
    # because the PO was later marked received.
    item_cost = ExpressionWrapper(
        F('accepted_quantity') * F('purchase_order_item__unit_price'),
        output_field=cost_field,
    )
    site_costs = (
        GoodsReceivedNoteItem.objects.filter(
            goods_received_note__purchase_order__project_id=OuterRef('pk'),
            goods_received_note__purchase_order__delivery_destination=PurchaseOrder.DELIVERY_SITE,
            goods_received_note__status=GoodsReceivedNote.STATUS_ACCEPTED,
            accepted_quantity__gt=0,
        )
        .values('goods_received_note__purchase_order__project_id')
        .annotate(total=Sum(item_cost))
        .values('total')[:1]
    )

    return queryset.annotate(
        warehouse_material_cost=Coalesce(Subquery(warehouse_costs, output_field=cost_field), Value(Decimal('0.00'))),
        direct_site_material_cost=Coalesce(Subquery(site_costs, output_field=cost_field), Value(Decimal('0.00'))),
    ).annotate(
        total_material_cost=ExpressionWrapper(
            F('warehouse_material_cost') + F('direct_site_material_cost'),
            output_field=cost_field,
        )
    )

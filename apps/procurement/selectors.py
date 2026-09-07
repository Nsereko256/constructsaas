"""Reusable company-scoped procurement read queries.

Selectors keep query shape out of API views. They intentionally do not apply
action queues; queue filters are request-specific and remain in the view layer.
"""

from apps.projects.access import accessible_purchase_orders, accessible_purchase_requests

from .models import PurchaseOrder, PurchaseRequest


def purchase_requests_for_user(user):
    """Return the base purchase-request queryset visible to ``user``."""
    return (
        accessible_purchase_requests(user, PurchaseRequest.objects.all())
        .select_related(
            'project', 'requested_by', 'technical_approved_by', 'manager_approved_by',
            'work_order', 'work_order_site', 'budget_approval__budget_line',
            'budget_approval__reviewed_by',
        )
        .prefetch_related('items__material', 'purchase_orders')
    )


def purchase_orders_for_user(user):
    """Return the base purchase-order queryset visible to ``user``."""
    return (
        accessible_purchase_orders(user, PurchaseOrder.objects.all())
        .select_related(
            'purchase_request',
            'project',
            'supplier',
            'received_by',
            'dispatch_confirmed_by',
            'delivery_follow_up_owner',
        )
        .prefetch_related('items__material', 'project__site_engineers', 'goods_received_notes__items')
    )

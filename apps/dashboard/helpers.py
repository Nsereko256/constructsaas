from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.materials.models import Material
from apps.procurement.models import PurchaseRequest
from apps.projects.models import Project
from apps.warehouse.models import StockMovement


def format_decimal(value):
    return f'{value:,.2f}'.rstrip('0').rstrip('.')


def decimal_string(value):
    text = f'{value:f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def get_dashboard_payload(company):
    materials = Material.objects.for_company(company).with_current_stock().with_inventory_value().select_related('category')
    active_materials = materials.filter(is_active=True)
    low_stock_materials = active_materials.filter(current_stock_value__lte=F('min_stock_level'))
    today = timezone.localdate()

    stock_in_today = StockMovement.objects.filter(
        company=company,
        date=today,
        movement_type=StockMovement.MOVEMENT_IN,
    ).aggregate(total=Coalesce(Sum('quantity'), Decimal('0.00')))['total']

    inventory_value = active_materials.aggregate(
        total=Coalesce(Sum('stock_value'), Decimal('0.00')),
    )['total']

    recent_movements = [
        {
            'id': movement.id,
            'material': {
                'id': movement.material_id,
                'name': movement.material.name,
                'code': movement.material.code,
            },
            'project': {
                'id': movement.project_id,
                'name': movement.project.name,
                'code': movement.project.code,
            }
            if movement.project_id
            else None,
            'movement_type': movement.movement_type,
            'movement_type_display': movement.get_movement_type_display(),
            'source': movement.source,
            'source_display': movement.get_source_display(),
            'quantity': format_decimal(movement.quantity),
            'unit_price': format_decimal(movement.unit_price),
            'date': movement.date.isoformat(),
            'notes': movement.notes,
        }
        for movement in StockMovement.objects.filter(company=company)
        .select_related('material', 'project')
        .order_by('-date', '-created_at')[:5]
    ]

    return {
        'total_active_materials': active_materials.count(),
        'active_projects': Project.objects.filter(company=company, is_active=True).count(),
        'low_stock_count': low_stock_materials.count(),
        'pending_purchase_requests': PurchaseRequest.objects.filter(
            company=company,
            status=PurchaseRequest.STATUS_PENDING,
        ).count(),
        'stock_in_today': decimal_string(stock_in_today),
        'inventory_value': decimal_string(inventory_value),
        'recent_stock_movements': recent_movements,
    }


def push_dashboard_update(company):
    if not company:
        return

    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    async_to_sync(channel_layer.group_send)(
        f'dashboard_company_{company.id}',
        {
            'type': 'dashboard_update',
            'payload': get_dashboard_payload(company),
        },
    )

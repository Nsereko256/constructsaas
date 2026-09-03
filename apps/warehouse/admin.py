from django.contrib import admin

from .models import StockMovement, Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'company', 'is_default', 'is_active')
    list_filter = ('company', 'is_default', 'is_active')
    search_fields = ('code', 'name', 'location')


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'material', 'warehouse', 'company', 'transaction_type', 'movement_type',
        'quantity', 'valuation_rate', 'total_cost', 'date',
    )
    list_filter = ('company', 'warehouse', 'transaction_type', 'movement_type', 'source')
    search_fields = ('material__name', 'material__code', 'purchase_order__number', 'notes')

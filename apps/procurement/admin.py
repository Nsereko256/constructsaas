from django.contrib import admin

from .models import PurchaseOrder, PurchaseOrderItem, PurchaseRequest, PurchaseRequestItem


class PurchaseRequestItemInline(admin.TabularInline):
    model = PurchaseRequestItem
    extra = 0


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ('number', 'company', 'project', 'priority', 'status', 'requested_by', 'created_at')
    list_filter = ('company', 'priority', 'status')
    search_fields = ('number', 'title', 'project__name')
    inlines = [PurchaseRequestItemInline]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('number', 'company', 'supplier_name', 'status', 'purchase_request', 'created_at')
    list_filter = ('company', 'status')
    search_fields = ('number', 'supplier_name')
    inlines = [PurchaseOrderItemInline]

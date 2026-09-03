from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.accounts.models import Company


class CompanyScopedQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class Warehouse(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='warehouses')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30)
    location = models.CharField(max_length=255, blank=True)
    project = models.OneToOneField(
        'projects.Project', on_delete=models.PROTECT, null=True, blank=True,
        related_name='site_store',
    )
    project_site = models.ForeignKey(
        'projects.ProjectSite', on_delete=models.PROTECT, null=True, blank=True,
        related_name='warehouses',
    )
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedQuerySet.as_manager()

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['company', 'code'], name='unique_company_warehouse_code'),
            models.UniqueConstraint(
                fields=['company'], condition=models.Q(is_default=True),
                name='one_default_warehouse_per_company',
            ),
        ]

    def clean(self):
        if self.is_default and not self.is_active:
            raise ValidationError({'is_active': 'The default warehouse must be active.'})
        if self.project_id:
            if self.project.company_id != self.company_id:
                raise ValidationError({'project': 'A site store must belong to a project in the same company.'})
            if self.is_default:
                raise ValidationError({'is_default': 'A project site store cannot be the company default warehouse.'})
        if self.project_site_id:
            if self.project_site.project.company_id != self.company_id:
                raise ValidationError({'project_site': 'A site store must belong to a project in the same company.'})
            if self.project_id and self.project_site.project_id != self.project_id:
                raise ValidationError({'project_site': 'Project site must belong to the selected project.'})
            if self.is_default:
                raise ValidationError({'is_default': 'A project site store cannot be the company default warehouse.'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} - {self.name}'


class BinLocation(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='bin_locations')
    code = models.CharField(max_length=40)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['warehouse__name', 'code']
        constraints = [models.UniqueConstraint(fields=['warehouse', 'code'], name='unique_warehouse_bin_code')]

    def save(self, *args, **kwargs):
        self.code = self.code.upper().strip()
        return super().save(*args, **kwargs)


class StockMovement(models.Model):
    MOVEMENT_IN = 'IN'
    MOVEMENT_OUT = 'OUT'
    MOVEMENT_ADJUSTMENT_IN = 'ADJUST_IN'
    MOVEMENT_ADJUSTMENT_OUT = 'ADJUST_OUT'

    MOVEMENT_TYPE_CHOICES = [
        (MOVEMENT_IN, 'Stock In'),
        (MOVEMENT_OUT, 'Stock Out'),
        (MOVEMENT_ADJUSTMENT_IN, 'Adjustment In'),
        (MOVEMENT_ADJUSTMENT_OUT, 'Adjustment Out'),
    ]

    SOURCE_SUPPLIER = 'SUPPLIER'
    SOURCE_INTERNAL = 'INTERNAL'
    SOURCE_SITE = 'SITE'
    SOURCE_ADJUSTMENT = 'ADJUSTMENT'

    SOURCE_CHOICES = [
        (SOURCE_SUPPLIER, 'Supplier'),
        (SOURCE_INTERNAL, 'Internal'),
        (SOURCE_SITE, 'Site'),
        (SOURCE_ADJUSTMENT, 'Adjustment'),
    ]

    TRANSACTION_LEGACY = 'LEGACY'
    TRANSACTION_OPENING = 'OPENING'
    TRANSACTION_RECEIPT = 'RECEIPT'
    TRANSACTION_PROJECT_ISSUE = 'PROJECT_ISSUE'
    TRANSACTION_PROJECT_RETURN = 'PROJECT_RETURN'
    TRANSACTION_SITE_TRANSFER_OUT = 'SITE_TRANSFER_OUT'
    TRANSACTION_SITE_TRANSFER_IN = 'SITE_TRANSFER_IN'
    TRANSACTION_SITE_CONSUMPTION = 'SITE_CONSUMPTION'
    TRANSACTION_SITE_RETURN_OUT = 'SITE_RETURN_OUT'
    TRANSACTION_SITE_RETURN_IN = 'SITE_RETURN_IN'
    TRANSACTION_SUPPLIER_RETURN = 'SUPPLIER_RETURN'
    TRANSACTION_DAMAGE = 'DAMAGE'
    TRANSACTION_WRITE_OFF = 'WRITE_OFF'
    TRANSACTION_QUANTITY_ADJUSTMENT = 'QUANTITY_ADJUSTMENT'
    TRANSACTION_VALUATION_ADJUSTMENT = 'VALUATION_ADJUSTMENT'
    TRANSACTION_LANDED_COST = 'LANDED_COST'
    TRANSACTION_LANDED_COST_REVERSAL = 'LANDED_COST_REVERSAL'
    TRANSACTION_CHOICES = [
        (TRANSACTION_LEGACY, 'Legacy movement'),
        (TRANSACTION_OPENING, 'Opening balance'),
        (TRANSACTION_RECEIPT, 'Valued receipt'),
        (TRANSACTION_PROJECT_ISSUE, 'Project issue'),
        (TRANSACTION_PROJECT_RETURN, 'Project return'),
        (TRANSACTION_SITE_TRANSFER_OUT, 'Transfer dispatched to site'),
        (TRANSACTION_SITE_TRANSFER_IN, 'Transfer acknowledged at site'),
        (TRANSACTION_SITE_CONSUMPTION, 'Site consumption'),
        (TRANSACTION_SITE_RETURN_OUT, 'Return dispatched from site'),
        (TRANSACTION_SITE_RETURN_IN, 'Return received into warehouse'),
        (TRANSACTION_SUPPLIER_RETURN, 'Supplier return'),
        (TRANSACTION_DAMAGE, 'Damage'),
        (TRANSACTION_WRITE_OFF, 'Write off'),
        (TRANSACTION_QUANTITY_ADJUSTMENT, 'Quantity adjustment'),
        (TRANSACTION_VALUATION_ADJUSTMENT, 'Valuation adjustment'),
        (TRANSACTION_LANDED_COST, 'Landed cost'),
        (TRANSACTION_LANDED_COST_REVERSAL, 'Landed cost reversal'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='stock_movements')
    material = models.ForeignKey('materials.Material', on_delete=models.PROTECT, related_name='movements')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_CHOICES, default=TRANSACTION_LEGACY)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    work_order = models.ForeignKey(
        'workorders.WorkOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    work_order_site = models.ForeignKey(
        'workorders.WorkOrderSite', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='stock_movements',
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    valuation_rate = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    quantity_effect = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    value_effect = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    purchase_order_item = models.ForeignKey(
        'procurement.PurchaseOrderItem',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    purchase_request = models.ForeignKey(
        'procurement.PurchaseRequest',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    purchase_request_item = models.ForeignKey(
        'procurement.PurchaseRequestItem',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    goods_received_note_item = models.OneToOneField(
        'procurement.GoodsReceivedNoteItem',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='stock_movement',
    )
    original_movement = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='return_movements',
    )
    authorization_reason = models.TextField(blank=True)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='authorized_stock_valuations',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name='stock_movement_quantity_nonnegative'),
            models.CheckConstraint(condition=models.Q(unit_cost__gte=0), name='stock_movement_unit_cost_nonnegative'),
            models.CheckConstraint(condition=models.Q(valuation_rate__gte=0), name='stock_valuation_rate_nonnegative'),
            models.CheckConstraint(condition=models.Q(total_cost__gte=0), name='stock_total_cost_nonnegative'),
        ]

    def __str__(self):
        return f'{self.material.code} - {self.get_movement_type_display()}'

    def get_absolute_url(self):
        return f'/api/stock-movements/{self.pk}/'

    def clean(self):
        if self.material_id and self.company_id and self.material.company_id != self.company_id:
            raise ValidationError({'material': 'Selected material must belong to the same company.'})

        if self.warehouse_id and self.warehouse.company_id != self.company_id:
            raise ValidationError({'warehouse': 'Selected warehouse must belong to the same company.'})

        if self.project_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Selected project must belong to the same company.'})
        if self.work_order_id:
            if self.work_order.company_id != self.company_id:
                raise ValidationError({'work_order': 'Work order must belong to the same company.'})
            if self.project_id != self.work_order.project_id:
                raise ValidationError({'work_order': 'Work order must belong to the selected project.'})
        if self.work_order_site_id:
            if self.work_order_site.work_order_id != self.work_order_id or self.project_id != self.work_order_site.project_id:
                raise ValidationError({'work_order_site': 'Site package must match the selected work order and project.'})

        if self.purchase_order_id and self.purchase_order.company_id != self.company_id:
            raise ValidationError({'purchase_order': 'Selected purchase order must belong to the same company.'})
        if self.purchase_order_item_id:
            if self.purchase_order_item.purchase_order.company_id != self.company_id:
                raise ValidationError({'purchase_order_item': 'PO item must belong to the same company.'})
            if self.purchase_order_id and self.purchase_order_item.purchase_order_id != self.purchase_order_id:
                raise ValidationError({'purchase_order_item': 'PO item must belong to the selected purchase order.'})
            if self.purchase_order_item.material_id != self.material_id:
                raise ValidationError({'purchase_order_item': 'PO item material must match the movement material.'})
        if self.purchase_request_id and self.purchase_request.company_id != self.company_id:
            raise ValidationError({'purchase_request': 'Purchase request must belong to the same company.'})
        if self.purchase_request_item_id:
            if self.purchase_request_item.purchase_request.company_id != self.company_id:
                raise ValidationError({'purchase_request_item': 'PR item must belong to the same company.'})
            if self.purchase_request_id and self.purchase_request_item.purchase_request_id != self.purchase_request_id:
                raise ValidationError({'purchase_request_item': 'PR item must belong to the selected purchase request.'})
            if self.purchase_request_item.material_id != self.material_id:
                raise ValidationError({'purchase_request_item': 'PR item material must match the movement material.'})

        if self.goods_received_note_item_id:
            grn_item = self.goods_received_note_item
            if grn_item.company_id != self.company_id:
                raise ValidationError({'goods_received_note_item': 'GRN item must belong to the same company.'})
            if grn_item.purchase_order_item.material_id != self.material_id:
                raise ValidationError({'goods_received_note_item': 'GRN item material must match the movement material.'})
        if self.original_movement_id:
            if self.original_movement.company_id != self.company_id:
                raise ValidationError({'original_movement': 'Original movement must belong to the same company.'})
            if self.original_movement.material_id != self.material_id:
                raise ValidationError({'original_movement': 'Original movement material must match.'})
        for field in ('created_by', 'authorized_by'):
            value = getattr(self, field, None)
            if value and value.company_id != self.company_id:
                raise ValidationError({field: 'User must belong to the same company.'})

        zero_quantity_types = {
            self.TRANSACTION_VALUATION_ADJUSTMENT,
            self.TRANSACTION_LANDED_COST,
            self.TRANSACTION_LANDED_COST_REVERSAL,
        }
        if self.quantity is not None and self.quantity <= 0 and self.transaction_type not in zero_quantity_types:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

    def save(self, *args, **kwargs):
        if self._state.adding and not getattr(self, '_valuation_prepared', False):
            from .valuation_services import save_legacy_movement

            return save_legacy_movement(self, save_args=args, save_kwargs=kwargs)
        if self.pk and StockMovement.objects.filter(pk=self.pk).exists():
            raise ValidationError('Valued stock movements are immutable; create a controlled correction.')
        self.full_clean()
        return super().save(*args, **kwargs)


class SiteTransfer(models.Model):
    STATUS_DISPATCHED = 'DISPATCHED'
    STATUS_ACKNOWLEDGED = 'ACKNOWLEDGED'
    STATUS_CHOICES = [(STATUS_DISPATCHED, 'Dispatched'), (STATUS_ACKNOWLEDGED, 'Acknowledged')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='site_transfers')
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, related_name='site_transfers')
    material = models.ForeignKey('materials.Material', on_delete=models.PROTECT, related_name='site_transfers')
    source_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='outbound_site_transfers')
    destination_store = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='inbound_site_transfers')
    quantity = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DISPATCHED)
    reason = models.TextField()
    dispatched_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='dispatched_site_transfers')
    dispatched_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='acknowledged_site_transfers')
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    outbound_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name='outbound_site_transfer')
    inbound_movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name='inbound_site_transfer')

    class Meta:
        ordering = ['-dispatched_at']

    def clean(self):
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Project must belong to this company.'})
        if self.destination_store_id and self.destination_store.project_id != self.project_id:
            raise ValidationError({'destination_store': 'Destination must be this project’s site store.'})
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

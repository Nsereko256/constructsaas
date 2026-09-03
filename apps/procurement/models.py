from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.accounts.models import Company


class PurchaseRequest(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_RETURNED = 'RETURNED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_PO_CREATED = 'PO_CREATED'
    STATUS_STOCK_ISSUE_REQUESTED = 'STOCK_ISSUE_REQUESTED'
    STATUS_PARTIAL_STOCK_ISSUED = 'PARTIAL_STOCK_ISSUED'
    STATUS_STOCK_ISSUED = 'STOCK_ISSUED'

    PRIORITY_LOW = 'LOW'
    PRIORITY_NORMAL = 'NORMAL'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RETURNED, 'Returned for Correction'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_PO_CREATED, 'PO Created'),
        (STATUS_STOCK_ISSUE_REQUESTED, 'Stock Issue Requested'),
        (STATUS_PARTIAL_STOCK_ISSUED, 'Partially Stock Issued'),
        (STATUS_STOCK_ISSUED, 'Stock Issued'),
    ]

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, 'Low'),
        (PRIORITY_NORMAL, 'Normal'),
        (PRIORITY_HIGH, 'High'),
        (PRIORITY_URGENT, 'Urgent'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_requests')
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_requests',
    )
    work_order = models.ForeignKey(
        'workorders.WorkOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_requests',
    )
    work_order_site = models.ForeignKey(
        'workorders.WorkOrderSite', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='purchase_requests',
    )
    number = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_PENDING)
    justification = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_requests',
    )
    technical_approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='technically_approved_purchase_requests',
    )
    manager_approved_by = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='manager_approved_purchase_requests',
    )
    rejection_reason = models.TextField(blank=True)
    technical_return_reason = models.TextField(blank=True)
    # Supplied by offline clients.  It makes a reconnect retry safe without
    # weakening the normal server-side workflow.
    client_uuid = models.UUIDField(null=True, blank=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('company', 'number')
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'],
                condition=Q(client_uuid__isnull=False),
                name='unique_company_purchase_request_client_uuid',
            )
        ]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return f'/api/purchase-requests/{self.pk}/'

    def clean(self):
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Selected project must belong to the same company.'})
        if self.work_order_id:
            if self.work_order.company_id != self.company_id:
                raise ValidationError({'work_order': 'Work order must belong to the same company.'})
            if self.work_order.project_id and self.project_id != self.work_order.project_id:
                raise ValidationError({'project': 'Project must match the linked work order.'})
        if self.work_order_site_id:
            if self.work_order_site.work_order_id != self.work_order_id:
                raise ValidationError({'work_order_site': 'Site package must belong to the linked work order.'})
            if self.project_id != self.work_order_site.project_id:
                raise ValidationError({'project': 'Project must match the linked work order site package.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseRequestItem(models.Model):
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name='items',
    )
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.PROTECT,
        related_name='purchase_request_items',
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['purchase_request', 'material'],
                name='unique_material_per_purchase_request',
            )
        ]

    def __str__(self):
        return f'{self.purchase_request.number} - {self.material.name}'

    def clean(self):
        if self.purchase_request_id and self.material_id:
            if self.material.company_id != self.purchase_request.company_id:
                raise ValidationError({'material': 'Selected material must belong to the same company as the PR.'})
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseOrder(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_PENDING = 'PENDING'
    STATUS_ORDERED = 'ORDERED'
    STATUS_DISPATCH_CONFIRMED = 'DISPATCH_CONFIRMED'
    STATUS_PARTIAL = 'PARTIAL'
    STATUS_RECEIVED = 'RECEIVED'
    STATUS_CANCELLED = 'CANCELLED'

    DELIVERY_WAREHOUSE = 'WAREHOUSE'
    DELIVERY_SITE = 'SITE'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_ORDERED, 'Ordered'),
        (STATUS_DISPATCH_CONFIRMED, 'Dispatch Confirmed'),
        (STATUS_PARTIAL, 'Partial'),
        (STATUS_RECEIVED, 'Received'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    DELIVERY_CHOICES = [
        (DELIVERY_WAREHOUSE, 'Warehouse'),
        (DELIVERY_SITE, 'Direct to site'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='purchase_orders')
    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    number = models.CharField(max_length=50)
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='purchase_orders',
    )
    supplier_name = models.CharField(max_length=255, blank=True)
    delivery_destination = models.CharField(
        max_length=20,
        choices=DELIVERY_CHOICES,
        default=DELIVERY_WAREHOUSE,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    expected_delivery_date = models.DateField(null=True, blank=True)
    supplier_confirmed_delivery_date = models.DateField(null=True, blank=True)
    revised_delivery_date = models.DateField(null=True, blank=True)
    delivery_revision_reason = models.TextField(blank=True)
    delivery_follow_up_owner = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='delivery_follow_up_purchase_orders',
    )
    notes = models.TextField(blank=True)
    dispatch_confirmed_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='dispatch_confirmed_purchase_orders',
    )
    dispatch_confirmed_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_purchase_orders',
    )
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('company', 'number')
        constraints = [
            models.UniqueConstraint(
                fields=['purchase_request'],
                condition=Q(purchase_request__isnull=False),
                name='unique_purchase_order_per_purchase_request',
            )
        ]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return f'/api/purchase-orders/{self.pk}/'

    def clean(self):
        if self.purchase_request_id and self.company_id and self.purchase_request.company_id != self.company_id:
            raise ValidationError({'purchase_request': 'Selected purchase request must belong to the same company.'})
        if self.purchase_request_id:
            duplicate_po_exists = PurchaseOrder.objects.filter(
                purchase_request_id=self.purchase_request_id,
            ).exclude(pk=self.pk).exists()
            if duplicate_po_exists:
                raise ValidationError({'purchase_request': 'This purchase request already has a purchase order.'})
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Selected project must belong to the same company.'})
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            raise ValidationError({'supplier': 'Selected supplier must belong to the same company.'})
        if self.received_by_id and self.company_id and self.received_by.company_id != self.company_id:
            raise ValidationError({'received_by': 'Receiving user must belong to the same company.'})
        if self.dispatch_confirmed_by_id and self.company_id:
            if self.dispatch_confirmed_by.company_id != self.company_id:
                raise ValidationError({'dispatch_confirmed_by': 'Dispatch confirmer must belong to the same company.'})
        if self.delivery_follow_up_owner_id and self.company_id:
            if self.delivery_follow_up_owner.company_id != self.company_id:
                raise ValidationError({'delivery_follow_up_owner': 'Delivery follow-up owner must belong to the same company.'})
        if self.revised_delivery_date and not self.delivery_revision_reason.strip():
            raise ValidationError({'delivery_revision_reason': 'Explain every revised delivery date.'})
        if self.purchase_request_id and self.project_id and self.purchase_request.project_id:
            if self.purchase_request.project_id != self.project_id:
                raise ValidationError({'project': 'Project must match the linked purchase request project.'})
        if self.delivery_destination == self.DELIVERY_SITE and not self.project_id:
            raise ValidationError({'project': 'Direct-to-site purchase orders must be linked to a project.'})
        if self.delivery_destination == self.DELIVERY_WAREHOUSE and self.status == self.STATUS_DISPATCH_CONFIRMED:
            raise ValidationError({'status': 'Dispatch confirmation is only used for direct-to-site purchase orders.'})

    def save(self, *args, **kwargs):
        if self.supplier_id:
            self.supplier_name = self.supplier.name
        self.full_clean()
        super().save(*args, **kwargs)


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
    )
    material = models.ForeignKey(
        'materials.Material',
        on_delete=models.PROTECT,
        related_name='purchase_order_items',
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['purchase_order', 'material'],
                name='unique_material_per_purchase_order',
            )
        ]

    def __str__(self):
        return f'{self.purchase_order.number} - {self.material.name}'

    def clean(self):
        if self.purchase_order_id and self.material_id:
            if self.material.company_id != self.purchase_order.company_id:
                raise ValidationError({'material': 'Selected material must belong to the same company as the PO.'})
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_price is not None and self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class GoodsReceivedNote(models.Model):
    STATUS_ACCEPTED = 'ACCEPTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [(STATUS_ACCEPTED, 'Accepted'), (STATUS_REVERSED, 'Reversed')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='goods_received_notes')
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='goods_received_notes')
    number = models.CharField(max_length=50)
    receipt_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACCEPTED)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='goods_received_notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    client_uuid = models.UUIDField(null=True, blank=True, default=None)

    class Meta:
        ordering = ['-receipt_date', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_grn_number'),
            models.UniqueConstraint(
                fields=['company', 'client_uuid'],
                condition=Q(client_uuid__isnull=False),
                name='unique_company_grn_client_uuid',
            ),
        ]

    def clean(self):
        if self.purchase_order_id and self.purchase_order.company_id != self.company_id:
            raise ValidationError({'purchase_order': 'Purchase order must belong to the same company.'})
        if self.received_by_id and self.received_by.company_id != self.company_id:
            raise ValidationError({'received_by': 'Receiver must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk and GoodsReceivedNote.objects.filter(pk=self.pk).exists():
            raise ValidationError('Accepted GRNs are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('GRNs cannot be deleted; use a controlled reversal.')

    def __str__(self):
        return self.number


class GoodsReceivedNoteItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='goods_received_note_items')
    goods_received_note = models.ForeignKey(GoodsReceivedNote, on_delete=models.PROTECT, related_name='items')
    purchase_order_item = models.ForeignKey(
        PurchaseOrderItem, on_delete=models.PROTECT, related_name='goods_received_note_items',
    )
    accepted_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rejected_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    damaged_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['goods_received_note', 'purchase_order_item'], name='unique_po_item_per_grn',
            ),
            models.CheckConstraint(condition=Q(accepted_quantity__gte=0), name='grn_accepted_nonnegative'),
            models.CheckConstraint(condition=Q(rejected_quantity__gte=0), name='grn_rejected_nonnegative'),
            models.CheckConstraint(condition=Q(damaged_quantity__gte=0), name='grn_damaged_nonnegative'),
            models.CheckConstraint(
                condition=Q(accepted_quantity__gt=0) | Q(rejected_quantity__gt=0) | Q(damaged_quantity__gt=0),
                name='grn_item_has_quantity',
            ),
        ]

    def clean(self):
        if self.goods_received_note_id:
            if self.goods_received_note.company_id != self.company_id:
                raise ValidationError({'goods_received_note': 'GRN must belong to the same company.'})
            if self.purchase_order_item_id and (
                self.purchase_order_item.purchase_order_id != self.goods_received_note.purchase_order_id
            ):
                raise ValidationError({'purchase_order_item': 'Item must belong to the GRN purchase order.'})

    def save(self, *args, **kwargs):
        if self.pk and GoodsReceivedNoteItem.objects.filter(pk=self.pk).exists():
            raise ValidationError('GRN items are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('GRN items cannot be deleted.')


class SupplierClaim(models.Model):
    """Commercial follow-up for material rejected or damaged during receipt."""

    STATUS_OPEN = 'OPEN'
    STATUS_AWAITING_SUPPLIER = 'AWAITING_SUPPLIER'
    STATUS_RETURN_PENDING = 'RETURN_PENDING'
    STATUS_REPLACEMENT_PENDING = 'REPLACEMENT_PENDING'
    STATUS_REPLACEMENT_RECEIVED = 'REPLACEMENT_RECEIVED'
    STATUS_CREDIT_PENDING = 'CREDIT_PENDING'
    STATUS_RESOLVED = 'RESOLVED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_AWAITING_SUPPLIER, 'Awaiting supplier'),
        (STATUS_RETURN_PENDING, 'Return pending'),
        (STATUS_REPLACEMENT_PENDING, 'Replacement pending'),
        (STATUS_REPLACEMENT_RECEIVED, 'Replacement received - confirm closure'),
        (STATUS_CREDIT_PENDING, 'Credit note pending'),
        (STATUS_RESOLVED, 'Resolved'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_claims')
    goods_received_note_item = models.OneToOneField(
        GoodsReceivedNoteItem, on_delete=models.PROTECT, related_name='supplier_claim',
    )
    # A replacement is a second physical delivery, not an amendment to the
    # original immutable GRN.  Linking it here prevents duplicate replacement
    # receipts for the same supplier exception.
    replacement_grn_item = models.OneToOneField(
        GoodsReceivedNoteItem, on_delete=models.PROTECT, null=True, blank=True,
        related_name='replacement_for_supplier_claim',
    )
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='supplier_claims')
    supplier = models.ForeignKey(
        'suppliers.Supplier', on_delete=models.PROTECT, null=True, blank=True, related_name='claims',
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplier_claims',
    )
    reported_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='reported_supplier_claims',
    )
    assigned_to = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_supplier_claims',
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_OPEN)
    due_date = models.DateField(null=True, blank=True)
    supplier_reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    resolution_notes = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, null=True, blank=True, related_name='resolved_supplier_claims',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', '-created_at']
        indexes = [
            models.Index(fields=['company', 'status'], name='supclaim_co_status_idx'),
            models.Index(fields=['company', 'due_date'], name='supplier_claim_company_due_idx'),
        ]

    def clean(self):
        if self.goods_received_note_item_id:
            grn_item = self.goods_received_note_item
            if grn_item.company_id != self.company_id:
                raise ValidationError({'goods_received_note_item': 'GRN item must belong to the same company.'})
            if self.purchase_order_id != grn_item.goods_received_note.purchase_order_id:
                raise ValidationError({'purchase_order': 'Purchase order must match the GRN item.'})
        for field in ('supplier', 'project', 'reported_by', 'assigned_to', 'resolved_by'):
            value = getattr(self, field, None)
            if value and value.company_id != self.company_id:
                raise ValidationError({field: 'Related record must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class DocumentSequence(models.Model):
    TYPE_PURCHASE_REQUEST = 'PR'
    TYPE_PURCHASE_ORDER = 'PO'
    TYPE_GOODS_RECEIVED_NOTE = 'GRN'

    TYPE_CHOICES = [
        (TYPE_PURCHASE_REQUEST, 'Purchase Request'),
        (TYPE_PURCHASE_ORDER, 'Purchase Order'),
        (TYPE_GOODS_RECEIVED_NOTE, 'Goods Received Note'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='document_sequences',
    )
    document_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'document_type'],
                name='unique_company_document_sequence',
            )
        ]

    def __str__(self):
        return f'{self.company}: {self.document_type} {self.last_value}'


from .amendments import PurchaseOrderAmendment  # noqa: E402,F401

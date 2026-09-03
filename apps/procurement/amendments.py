"""Controlled amendment primitives for approved purchase orders.

The full UI and finance-commitment reapproval workflow is intentionally kept
behind this immutable audit record; approved POs must never be edited in place.
"""
from django.conf import settings
from django.db import models


class PurchaseOrderAmendment(models.Model):
    TYPE_CONTROLLED = 'CONTROLLED'
    TYPE_PRE_APPROVAL_EDIT = 'PRE_APPROVAL_EDIT'
    TYPE_CHOICES = [
        (TYPE_CONTROLLED, 'Controlled amendment'),
        (TYPE_PRE_APPROVAL_EDIT, 'Pre-approval edit'),
    ]
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [(STATUS_SUBMITTED, 'Submitted'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected')]

    purchase_order = models.ForeignKey('procurement.PurchaseOrder', on_delete=models.PROTECT, related_name='amendments')
    company = models.ForeignKey('accounts.Company', on_delete=models.PROTECT, related_name='purchase_order_amendments')
    amendment_type = models.CharField(max_length=24, choices=TYPE_CHOICES, default=TYPE_CONTROLLED)
    version = models.PositiveIntegerField()
    reason = models.TextField()
    original_values = models.JSONField(default=dict)
    proposed_values = models.JSONField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_po_amendments')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='decided_po_amendments')
    decision_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['purchase_order', 'version'], name='unique_po_amendment_version')]
        ordering = ['-version']

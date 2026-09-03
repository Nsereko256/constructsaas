from django.db import models
from django.core.exceptions import ValidationError

from apps.accounts.models import Company


class NotificationQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)

    def unread(self):
        return self.filter(is_read=False)

    def for_recipient(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(recipient=user)


class Notification(models.Model):
    TYPE_LOW_STOCK = 'low_stock'
    TYPE_PR_SUBMITTED = 'pr_submitted'
    TYPE_PR_APPROVED = 'pr_approved'
    TYPE_PR_REJECTED = 'pr_rejected'
    TYPE_PO_CREATED = 'po_created'
    TYPE_PO_RECEIVED = 'po_received'
    TYPE_SUPPLIER_CLAIM_OPENED = 'supplier_claim_opened'
    TYPE_SYSTEM = 'system'
    TYPE_BUDGET_APPROVAL_REQUIRED = 'budget_approval_required'
    TYPE_BUDGET_THRESHOLD_REACHED = 'budget_threshold_reached'
    TYPE_PO_EXCEEDING_BUDGET = 'po_exceeding_budget'
    TYPE_INVOICE_SUBMITTED = 'invoice_submitted'
    TYPE_INVOICE_MATCH_EXCEPTION = 'invoice_match_exception'
    TYPE_INVOICE_DUE_SOON = 'invoice_due_soon'
    TYPE_INVOICE_OVERDUE = 'invoice_overdue'
    TYPE_PAYMENT_AWAITING_APPROVAL = 'payment_awaiting_approval'
    TYPE_PAYMENT_APPROVED = 'payment_approved'
    TYPE_PAYMENT_REJECTED = 'payment_rejected'
    TYPE_STAFF_ADVANCE_OVERDUE = 'staff_advance_overdue'
    TYPE_VALUATION_ADJUSTMENT = 'valuation_adjustment'
    TYPE_JOURNAL_POSTING_FAILURE = 'journal_posting_failure'

    LEVEL_INFO = 'info'
    LEVEL_SUCCESS = 'success'
    LEVEL_WARNING = 'warning'
    LEVEL_DANGER = 'danger'

    NOTIFICATION_TYPE_CHOICES = [
        (TYPE_LOW_STOCK, 'Low stock'),
        (TYPE_PR_SUBMITTED, 'PR submitted'),
        (TYPE_PR_APPROVED, 'PR approved'),
        (TYPE_PR_REJECTED, 'PR rejected'),
        (TYPE_PO_CREATED, 'PO created'),
        (TYPE_PO_RECEIVED, 'PO received'),
        (TYPE_SUPPLIER_CLAIM_OPENED, 'Supplier claim opened'),
        (TYPE_SYSTEM, 'System'),
        (TYPE_BUDGET_APPROVAL_REQUIRED, 'Budget approval required'),
        (TYPE_BUDGET_THRESHOLD_REACHED, 'Budget threshold reached'),
        (TYPE_PO_EXCEEDING_BUDGET, 'PO exceeding budget'),
        (TYPE_INVOICE_SUBMITTED, 'Invoice submitted'),
        (TYPE_INVOICE_MATCH_EXCEPTION, 'Invoice matching exception'),
        (TYPE_INVOICE_DUE_SOON, 'Invoice due soon'),
        (TYPE_INVOICE_OVERDUE, 'Invoice overdue'),
        (TYPE_PAYMENT_AWAITING_APPROVAL, 'Payment awaiting approval'),
        (TYPE_PAYMENT_APPROVED, 'Payment approved'),
        (TYPE_PAYMENT_REJECTED, 'Payment rejected'),
        (TYPE_STAFF_ADVANCE_OVERDUE, 'Staff advance overdue'),
        (TYPE_VALUATION_ADJUSTMENT, 'Valuation adjustment'),
        (TYPE_JOURNAL_POSTING_FAILURE, 'Journal posting failure'),
    ]

    LEVEL_CHOICES = [
        (LEVEL_INFO, 'Info'),
        (LEVEL_SUCCESS, 'Success'),
        (LEVEL_WARNING, 'Warning'),
        (LEVEL_DANGER, 'Danger'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='notifications')
    recipient = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    title = models.CharField(max_length=180)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company', 'recipient', 'is_read', '-created_at'], name='notificatio_company_f079c9_idx'),
            models.Index(fields=['company', 'notification_type', '-created_at'], name='notificatio_company_719c72_idx'),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f'/api/notifications/{self.pk}/'

    def clean(self):
        if self.company_id and self.recipient_id and self.recipient.company_id != self.company_id:
            raise ValidationError({'recipient': 'Recipient must belong to the notification company.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])


class WebPushSubscription(models.Model):
    """A browser/device push endpoint, deliberately scoped to one signed-in user."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='web_push_subscriptions')
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='web_push_subscriptions')
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    user_agent = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['company', 'user'], name='webpush_company_user_idx'),
        ]

    def clean(self):
        if self.company_id and self.user_id and self.user.company_id != self.company_id:
            raise ValidationError({'user': 'Subscription user must belong to the subscription company.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

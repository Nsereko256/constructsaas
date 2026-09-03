from django.db import models

from apps.accounts.models import Company


class Supplier(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    rating = models.PositiveSmallIntegerField(default=3)
    lead_time_days = models.PositiveIntegerField(default=0)
    is_preferred = models.BooleanField(default=False)
    compliance_reference = models.CharField(max_length=120, blank=True)
    compliance_expiry_date = models.DateField(null=True, blank=True)
    is_contractor = models.BooleanField(default=False)
    contractor_specialty = models.CharField(max_length=180, blank=True)
    contractor_mobilisation_days = models.PositiveIntegerField(default=0)
    contractor_rate_notes = models.TextField(blank=True)
    contractor_insurance_expiry_date = models.DateField(null=True, blank=True)
    contractor_safety_clearance_expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('company', 'name')

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f'/api/suppliers/{self.pk}/'

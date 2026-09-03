from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from uuid import uuid4


class Company(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Company.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                counter += 1
                slug = f'{base_slug}-{counter}'
            self.slug = slug
        super().save(*args, **kwargs)


class User(AbstractUser):
    ROLE_SITE_ENGINEER = 'site_engineer'
    ROLE_STOREKEEPER = 'storekeeper'
    ROLE_PROJECT_MANAGER = 'project_manager'
    ROLE_PROCUREMENT_OFFICER = 'procurement_officer'
    ROLE_FINANCE_OFFICER = 'finance_officer'
    ROLE_FINANCE_MANAGER = 'finance_manager'
    ROLE_FINANCE_VIEWER = 'finance_viewer'
    ROLE_ADMIN = 'admin'

    ROLE_CHOICES = [
        (ROLE_SITE_ENGINEER, 'Site Engineer'),
        (ROLE_STOREKEEPER, 'Storekeeper'),
        (ROLE_PROJECT_MANAGER, 'Project Manager'),
        (ROLE_PROCUREMENT_OFFICER, 'Procurement Officer'),
        (ROLE_FINANCE_OFFICER, 'Finance Officer'),
        (ROLE_FINANCE_MANAGER, 'Finance Manager'),
        (ROLE_FINANCE_VIEWER, 'Finance Viewer'),
        (ROLE_ADMIN, 'Admin'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_SITE_ENGINEER)
    phone = models.CharField(max_length=30, blank=True)
    active_session_id = models.UUIDField(default=uuid4, editable=False)
    active_session_started_at = models.DateTimeField(null=True, blank=True)

    @property
    def role_label(self):
        return self.get_role_display()

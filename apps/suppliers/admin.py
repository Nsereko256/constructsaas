from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'contact_person', 'phone', 'email', 'rating', 'is_active')
    list_filter = ('company', 'is_active', 'rating')
    search_fields = ('name', 'contact_person', 'phone', 'email')

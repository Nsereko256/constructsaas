from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Company, User


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    search_fields = ('name', 'slug')
    list_filter = ('is_active',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class ConstructionUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Construction SaaS', {'fields': ('company', 'role', 'phone')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Construction SaaS', {'fields': ('company', 'role', 'phone')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'company', 'role', 'is_staff')
    list_filter = ('role', 'company', 'is_staff', 'is_superuser', 'is_active')

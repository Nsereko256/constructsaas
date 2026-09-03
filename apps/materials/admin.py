from django.contrib import admin

from .models import Category, Material


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'created_at')
    search_fields = ('name',)
    list_filter = ('company',)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'company', 'category', 'unit', 'unit_price', 'is_active')
    search_fields = ('name', 'code')
    list_filter = ('company', 'category', 'is_active')

# Register your models here.

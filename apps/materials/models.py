from decimal import Decimal

from django.db import models
from django.db.models import Case, DecimalField, F, OuterRef, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

from apps.accounts.models import Company


class Category(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('company', 'name')
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class MaterialQuerySet(models.QuerySet):
    def for_company(self, company):
        return self.filter(company=company)

    def with_current_stock(self):
        return self.annotate(
            current_stock_value=Coalesce(
                Sum('movements__quantity_effect'),
                Value(Decimal('0.00')),
            )
        )

    def with_inventory_value(self):
        from apps.warehouse.models import StockMovement

        value_subquery = (
            StockMovement.objects.filter(material_id=OuterRef('pk'))
            .values('material_id')
            .annotate(total=Sum('value_effect'))
            .values('total')[:1]
        )
        return self.annotate(
            stock_value=Coalesce(
                Subquery(value_subquery, output_field=DecimalField(max_digits=18, decimal_places=2)),
                Value(Decimal('0.00')),
            )
        )


class Material(models.Model):
    UNIT_BAG = 'bag'
    UNIT_TON = 'ton'
    UNIT_KG = 'kg'
    UNIT_LITRE = 'litre'
    UNIT_PIECE = 'piece'
    UNIT_METRE = 'metre'
    UNIT_SQM = 'sqm'
    UNIT_CBM = 'cbm'

    UNIT_CHOICES = [
        (UNIT_BAG, 'Bag'),
        (UNIT_TON, 'Ton'),
        (UNIT_KG, 'KG'),
        (UNIT_LITRE, 'Litre'),
        (UNIT_PIECE, 'Piece'),
        (UNIT_METRE, 'Metre'),
        (UNIT_SQM, 'SQM'),
        (UNIT_CBM, 'CBM'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='materials')
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='materials',
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    min_stock_level = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MaterialQuerySet.as_manager()

    class Meta:
        ordering = ['name']
        unique_together = (
            ('company', 'name'),
            ('company', 'code'),
        )

    def __str__(self):
        return f'{self.name} ({self.code})'

    def get_absolute_url(self):
        return f'/api/materials/{self.pk}/'

    @property
    def current_stock(self):
        movement_totals = self.movements.aggregate(
            total=Coalesce(Sum('quantity_effect'), Value(Decimal('0.00'))),
        )
        return movement_totals['total']

    @property
    def is_low_stock(self):
        return self.current_stock <= self.min_stock_level

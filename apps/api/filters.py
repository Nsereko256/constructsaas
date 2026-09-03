import django_filters

from apps.warehouse.models import StockMovement


class StockMovementFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    project_site = django_filters.NumberFilter(method='filter_project_site')

    def filter_project_site(self, queryset, name, value):
        return queryset.filter(warehouse__project_site_id=value)

    class Meta:
        model = StockMovement
        fields = [
            'material', 'warehouse', 'movement_type', 'transaction_type', 'project',
            'date_from', 'date_to',
            'project_site',
        ]

from rest_framework import serializers

from apps.projects.models import Project, ProjectSite
from apps.suppliers.models import Supplier
from apps.warehouse.models import Warehouse

from .models import Account


class FinanceReportFilterSerializer(serializers.Serializer):
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    project = serializers.IntegerField(required=False, min_value=1)
    project_site = serializers.IntegerField(required=False, min_value=1)
    supplier = serializers.IntegerField(required=False, min_value=1)
    warehouse = serializers.IntegerField(required=False, min_value=1)
    account = serializers.IntegerField(required=False, min_value=1)
    status = serializers.CharField(required=False, max_length=50)
    ordering = serializers.CharField(required=False, max_length=80)

    def validate(self, attrs):
        request = self.context['request']
        company = request.user.company
        if attrs.get('date_from') and attrs.get('date_to'):
            if attrs['date_from'] > attrs['date_to']:
                raise serializers.ValidationError({'date_to': 'Must be on or after date_from.'})

        scoped_models = {
            'project': Project,
            'project_site': ProjectSite,
            'supplier': Supplier,
            'warehouse': Warehouse,
            'account': Account,
        }
        for field, model in scoped_models.items():
            object_id = attrs.get(field)
            scope = {'project__company': company} if field == 'project_site' else {'company': company}
            if object_id and not model.objects.filter(**scope, pk=object_id).exists():
                raise serializers.ValidationError({field: 'Invalid selection for your company.'})
        if attrs.get('project_site') and attrs.get('project') and not ProjectSite.objects.filter(
            pk=attrs['project_site'], project_id=attrs['project'], project__company=company,
        ).exists():
            raise serializers.ValidationError({'project_site': 'Site must belong to the selected project.'})
        return attrs

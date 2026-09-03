from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.pagination import StandardPagination

from .permissions import FinanceCompanyPermission
from .report_exports import csv_response, pdf_response, xlsx_response
from .report_serializers import FinanceReportFilterSerializer
from .report_services import build_report, finance_dashboard


REPORT_PARAMETERS = [
    OpenApiParameter('date_from', OpenApiTypes.DATE, description='Inclusive start date.'),
    OpenApiParameter('date_to', OpenApiTypes.DATE, description='Inclusive end date or report as-of date.'),
    OpenApiParameter('project', OpenApiTypes.INT, description='Project ID from the authenticated company.'),
    OpenApiParameter('project_site', OpenApiTypes.INT, description='Physical project site ID from the authenticated company.'),
    OpenApiParameter('supplier', OpenApiTypes.INT, description='Supplier ID from the authenticated company.'),
    OpenApiParameter('warehouse', OpenApiTypes.INT, description='Warehouse ID from the authenticated company.'),
    OpenApiParameter('account', OpenApiTypes.INT, description='Ledger account ID from the authenticated company.'),
    OpenApiParameter('status', OpenApiTypes.STR, description='Document status applicable to the report.'),
    OpenApiParameter('ordering', OpenApiTypes.STR, description='A returned column key, prefixed with - for descending.'),
]


class FinanceDashboardAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]

    @extend_schema(
        tags=['Finance reports'],
        summary='Finance dashboard summary',
        description='Returns authoritative company-scoped finance KPIs and project balance drill-down data.',
        parameters=REPORT_PARAMETERS,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        serializer = FinanceReportFilterSerializer(data=request.query_params, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(finance_dashboard(request.user.company, serializer.validated_data))


class FinanceReportAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]
    report_slug = None

    @extend_schema(
        tags=['Finance reports'],
        summary='Finance report',
        description=(
            'Returns authoritative report totals and paginated detail rows. IDs and API URLs are included '
            'for drill-down. The URL identifies the specific report documented in the route name.'
        ),
        parameters=REPORT_PARAMETERS,
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        serializer = FinanceReportFilterSerializer(data=request.query_params, context={'request': request})
        serializer.is_valid(raise_exception=True)
        report = build_report(self.report_slug, request.user.company, serializer.validated_data)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(report['rows'], request, view=self)
        pagination = paginator.get_paginated_response(page)
        return Response({
            'title': report['title'],
            'filters': serializer.validated_data,
            'totals': report['totals'],
            'count': pagination.data['count'],
            'next': pagination.data['next'],
            'previous': pagination.data['previous'],
            'results': pagination.data['results'],
        })


class FinanceReportDownloadAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]
    report_slug = None
    file_format = None

    @extend_schema(
        tags=['Finance reports'],
        summary='Download finance report',
        description='Downloads the complete authenticated, company-scoped report as CSV, Excel XLSX, or PDF.',
        parameters=REPORT_PARAMETERS,
        responses={200: OpenApiTypes.BINARY},
    )
    def get(self, request):
        serializer = FinanceReportFilterSerializer(data=request.query_params, context={'request': request})
        serializer.is_valid(raise_exception=True)
        report = build_report(self.report_slug, request.user.company, serializer.validated_data)
        if self.file_format == 'csv':
            return csv_response(report, self.report_slug)
        if self.file_format == 'pdf':
            return pdf_response(report, self.report_slug)
        return xlsx_response(report, self.report_slug)

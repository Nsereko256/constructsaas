import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { ProtectedRoute } from '@/auth/protected-route';
import { AppShell } from '@/components/layout/app-shell';

const DashboardPage = lazy(() => import('@/pages/dashboard').then((module) => ({ default: module.DashboardPage })));
const DeliveriesPage = lazy(() => import('@/pages/deliveries').then((module) => ({ default: module.DeliveriesPage })));
const GoodsReceivedNotesPage = lazy(() => import('@/pages/goods-received-notes').then((module) => ({ default: module.GoodsReceivedNotesPage })));
const ForgotPasswordPage = lazy(() => import('@/pages/forgot-password').then((module) => ({ default: module.ForgotPasswordPage })));
const InventoryPage = lazy(() => import('@/pages/inventory').then((module) => ({ default: module.InventoryPage })));
const InventoryMovementsPage = lazy(() => import('@/pages/inventory-movements').then((module) => ({ default: module.InventoryMovementsPage })));
const SiteCustodyPage = lazy(() => import('@/pages/site-custody').then((module) => ({ default: module.SiteCustodyPage })));
const BinLocationsPage = lazy(() => import('@/pages/bin-locations').then((module) => ({ default: module.BinLocationsPage })));
const LoginPage = lazy(() => import('@/pages/login').then((module) => ({ default: module.LoginPage })));
const RegisterCompanyPage = lazy(() => import('@/pages/register-company').then((module) => ({ default: module.RegisterCompanyPage })));
const MessagesPage = lazy(() => import('@/pages/messages').then((module) => ({ default: module.MessagesPage })));
const NotFoundPage = lazy(() => import('@/pages/not-found').then((module) => ({ default: module.NotFoundPage })));
const NotificationsPage = lazy(() => import('@/pages/notifications').then((module) => ({ default: module.NotificationsPage })));
const ProcurementRequestsPage = lazy(() => import('@/pages/procurement-requests').then((module) => ({ default: module.ProcurementRequestsPage })));
const ProcurementRfqsPage = lazy(() => import('@/pages/procurement-rfqs').then((module) => ({ default: module.ProcurementRfqsPage })));
const PurchaseOrdersPage = lazy(() => import('@/pages/purchase-orders').then((module) => ({ default: module.PurchaseOrdersPage })));
const SupplierClaimsPage = lazy(() => import('@/pages/supplier-claims').then((module) => ({ default: module.SupplierClaimsPage })));
const ProjectDetailPage = lazy(() => import('@/pages/project-detail').then((module) => ({ default: module.ProjectDetailPage })));
const ProjectsPage = lazy(() => import('@/pages/projects').then((module) => ({ default: module.ProjectsPage })));
const ProjectSitesPage = lazy(() => import('@/pages/project-sites').then((module) => ({ default: module.ProjectSitesPage })));
const ProjectProgressPage = lazy(() => import('@/pages/project-progress').then((module) => ({ default: module.ProjectProgressPage })));
const ReportsPage = lazy(() => import('@/pages/reports').then((module) => ({ default: module.ReportsPage })));
const SettingsPage = lazy(() => import('@/pages/settings').then((module) => ({ default: module.SettingsPage })));
const SuppliersPage = lazy(() => import('@/pages/suppliers').then((module) => ({ default: module.SuppliersPage })));
const TeamPage = lazy(() => import('@/pages/team').then((module) => ({ default: module.TeamPage })));
const ProjectStaffingPage = lazy(() => import('@/pages/project-staffing').then((module) => ({ default: module.ProjectStaffingPage })));
const FinanceOverviewPage = lazy(() => import('@/pages/finance/overview').then((module) => ({ default: module.FinanceOverviewPage })));
const FinanceBudgetsPage = lazy(() => import('@/pages/finance/budgets').then((module) => ({ default: module.FinanceBudgetsPage })));
const FinancePayablesPage = lazy(() => import('@/pages/finance/payables').then((module) => ({ default: module.FinancePayablesPage })));
const FinancePaymentsPage = lazy(() => import('@/pages/finance/payments').then((module) => ({ default: module.FinancePaymentsPage })));
const FinancePaymentBatchesPage = lazy(() => import('@/pages/finance/payment-batches').then((module) => ({ default: module.FinancePaymentBatchesPage })));
const FinanceReconciliationPage = lazy(() => import('@/pages/finance/reconciliation').then((module) => ({ default: module.FinanceReconciliationPage })));
const FinanceExpensesPage = lazy(() => import('@/pages/finance/expenses').then((module) => ({ default: module.FinanceExpensesPage })));
const FinanceLedgerPage = lazy(() => import('@/pages/finance/ledger').then((module) => ({ default: module.FinanceLedgerPage })));
const FinanceMonthEndPage = lazy(() => import('@/pages/finance/month-end').then((module) => ({ default: module.FinanceMonthEndPage })));
const FinanceReportsPage = lazy(() => import('@/pages/finance/reports').then((module) => ({ default: module.FinanceReportsPage })));
const FinanceSettingsPage = lazy(() => import('@/pages/finance/settings').then((module) => ({ default: module.FinanceSettingsPage })));
const WorkOrdersPage = lazy(() => import('@/pages/work-orders').then((module) => ({ default: module.WorkOrdersPage })));
const WorkOrderProgressPage = lazy(() => import('@/pages/work-order-progress').then((module) => ({ default: module.WorkOrderProgressPage })));
const WorkOrderInvoicesPage = lazy(() => import('@/pages/work-order-invoices').then((module) => ({ default: module.WorkOrderInvoicesPage })));

function RouteLoader() {
  return (
    <div className="grid min-h-[240px] place-items-center text-sm text-muted" role="status">
      Loading workspace...
    </div>
  );
}

export function App() {
  return (
    <Suspense fallback={<RouteLoader />}>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/app/*" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register-company" element={<RegisterCompanyPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ForgotPasswordPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/sites" element={<ProjectSitesPage />} />
            <Route path="/projects/:projectId/progress" element={<ProjectProgressPage />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/work-orders" element={<WorkOrdersPage />} />
            <Route path="/work-orders/progress" element={<WorkOrderProgressPage />} />
            <Route path="/work-orders/invoices" element={<WorkOrderInvoicesPage />} />
            <Route path="/work-orders/:workOrderId" element={<WorkOrdersPage />} />
            <Route path="/procurement/requests" element={<ProcurementRequestsPage />} />
            <Route path="/procurement/rfqs" element={<ProcurementRfqsPage />} />
            <Route path="/procurement/purchase-orders" element={<PurchaseOrdersPage />} />
            <Route path="/procurement/grns" element={<GoodsReceivedNotesPage />} />
            <Route path="/procurement/supplier-claims" element={<SupplierClaimsPage />} />
            <Route path="/procurement/deliveries" element={<DeliveriesPage />} />
            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/inventory/movements" element={<InventoryMovementsPage />} />
            <Route path="/inventory/site-custody" element={<SiteCustodyPage />} />
            <Route path="/inventory/bin-locations" element={<BinLocationsPage />} />
            <Route path="/suppliers" element={<SuppliersPage />} />
            <Route path="/messages" element={<MessagesPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/team" element={<TeamPage />} />
            <Route path="/team/project-staffing" element={<ProjectStaffingPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/finance" element={<FinanceOverviewPage />} />
            <Route path="/finance/budgets" element={<FinanceBudgetsPage />} />
            <Route path="/finance/payables" element={<FinancePayablesPage />} />
            <Route path="/finance/payments" element={<FinancePaymentsPage />} />
            <Route path="/finance/payment-batches" element={<FinancePaymentBatchesPage />} />
            <Route path="/finance/reconciliation" element={<FinanceReconciliationPage />} />
            <Route path="/finance/expenses" element={<FinanceExpensesPage />} />
            <Route path="/finance/ledger" element={<FinanceLedgerPage />} />
            <Route path="/finance/month-end" element={<FinanceMonthEndPage />} />
            <Route path="/finance/reports" element={<FinanceReportsPage />} />
            <Route path="/finance/settings" element={<FinanceSettingsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}

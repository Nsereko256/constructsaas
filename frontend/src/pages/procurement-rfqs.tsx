import { FileQuestion } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export function ProcurementRfqsPage() {
  return (
    <Card>
      <CardHeader><CardTitle>RFQs and quotations</CardTitle></CardHeader>
      <CardContent className="grid gap-2 text-sm text-muted">
        <FileQuestion className="h-8 w-8 text-primary" />
        <p>The backend does not yet expose RFQ or quotation models/endpoints.</p>
        <p>This page is intentionally reserved so procurement can grow into supplier quotation comparison without changing the current PR and PO workflow.</p>
      </CardContent>
    </Card>
  );
}

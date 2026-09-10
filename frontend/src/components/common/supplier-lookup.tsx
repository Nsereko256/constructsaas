import { useQuery } from '@tanstack/react-query';

import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import { SearchableSelect } from '@/components/ui/searchable-select';

type SupplierLookupProps = {
  label: string;
  supplierId: string;
  onChange: (supplierId: string, label: string) => void;
};

export function SupplierLookup({ supplierId, onChange }: SupplierLookupProps) {
  const suppliers = useQuery({
    queryKey: qk.suppliers({ lookup: 'active-picker' }),
    queryFn: () => api.suppliers({ is_active: true, page_size: 100 }),
  });
  const options = (suppliers.data?.results || []).map((supplier) => ({ value: supplier.id, label: supplier.name }));
  return <SearchableSelect required value={supplierId} options={options} placeholder={suppliers.isLoading ? 'Loading suppliers…' : 'Search active suppliers'} onChange={(value) => {
    const selected = suppliers.data?.results.find((supplier) => String(supplier.id) === value);
    onChange(value, selected?.name || '');
  }} />;
}

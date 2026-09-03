import { useDeferredValue, useEffect, useId, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import { inputClass } from '@/components/ui/field';

type SupplierLookupProps = {
  label: string;
  supplierId: string;
  onChange: (supplierId: string, label: string) => void;
};

export function SupplierLookup({ label, supplierId, onChange }: SupplierLookupProps) {
  const listId = useId();
  const deferredLabel = useDeferredValue(label);
  const suppliers = useQuery({
    queryKey: qk.suppliers({ lookup: deferredLabel }),
    queryFn: () => api.suppliers({
      search: deferredLabel,
      is_active: true,
      page_size: 20,
    }),
  });
  const options = useMemo(() => suppliers.data?.results || [], [suppliers.data?.results]);

  // A datalist can update its options after the user has already typed the
  // supplier name. Reconcile that value once the matching supplier arrives so
  // the form has the supplier ID required by the API, not only the visible name.
  useEffect(() => {
    if (supplierId || !label.trim()) return;
    const supplier = options.find(
      (item) => item.name.toLowerCase() === label.trim().toLowerCase(),
    );
    if (supplier) onChange(String(supplier.id), supplier.name);
  }, [label, onChange, options, supplierId]);

  const update = (nextLabel: string) => {
    const supplier = options.find(
      (item) => item.name.toLowerCase() === nextLabel.trim().toLowerCase(),
    );
    onChange(supplier ? String(supplier.id) : '', nextLabel);
  };

  return (
    <>
      <input
        className={inputClass}
        type="search"
        list={listId}
        value={label}
        required
        onChange={(event) => update(event.target.value)}
        placeholder="Search active suppliers"
        aria-invalid={Boolean(label && !supplierId)}
      />
      <datalist id={listId}>
        {options.map((supplier) => <option key={supplier.id} value={supplier.name} />)}
      </datalist>
      {label && !supplierId ? (
        <span className="text-xs text-muted">Choose an active supplier from the results.</span>
      ) : null}
    </>
  );
}

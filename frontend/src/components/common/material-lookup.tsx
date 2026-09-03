import { useDeferredValue, useId } from 'react';
import { useQuery } from '@tanstack/react-query';

import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import { inputClass } from '@/components/ui/field';
import { materialOption } from '@/lib/selectors';

type MaterialLookupProps = {
  label: string;
  materialId: string;
  onChange: (materialId: string, label: string) => void;
  required?: boolean;
};

export function MaterialLookup({
  label,
  materialId,
  onChange,
  required = false,
}: MaterialLookupProps) {
  const listId = useId();
  const deferredLabel = useDeferredValue(label);
  const materials = useQuery({
    queryKey: qk.materials({ lookup: deferredLabel }),
    queryFn: () => api.materials({
      search: deferredLabel,
      is_active: true,
      page_size: 20,
    }),
  });
  const options = materials.data?.results || [];

  const update = (nextLabel: string) => {
    const selected = options.find(
      (material) => materialOption(material).toLowerCase() === nextLabel.trim().toLowerCase(),
    );
    onChange(selected ? String(selected.id) : '', nextLabel);
  };

  return (
    <>
      <input
        className={inputClass}
        type="search"
        list={listId}
        value={label}
        required={required}
        onChange={(event) => update(event.target.value)}
        placeholder="Search by material name or code"
        aria-invalid={Boolean(label && !materialId)}
      />
      <datalist id={listId}>
        {options.map((material) => (
          <option key={material.id} value={materialOption(material)} />
        ))}
      </datalist>
      {label && !materialId ? (
        <span className="text-xs text-muted">Choose a material from the search results.</span>
      ) : null}
    </>
  );
}

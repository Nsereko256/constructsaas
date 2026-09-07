import { useCallback, useDeferredValue, useEffect, useId } from 'react';
import { useQuery } from '@tanstack/react-query';

import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import type { Material } from '@/api/types';
import { inputClass } from '@/components/ui/field';
import { materialOption, resolveMaterialId } from '@/lib/selectors';

const EMPTY_MATERIALS: Material[] = [];

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
    queryFn: () => api.materialsCatalog({
      search: deferredLabel,
      is_active: true,
      page_size: 20,
    }),
  });
  const options = materials.data?.results ?? EMPTY_MATERIALS;

  const findMaterial = useCallback((nextLabel: string) => {
    const normalized = nextLabel.trim().toLowerCase();
    return options.find(
      (material) => materialOption(material).toLowerCase() === normalized,
    ) || options.find(
      (material) => material.name.toLowerCase() === normalized || material.code.toLowerCase() === normalized,
    ) || (options.length === 1 && normalized ? options[0] : undefined);
  }, [options]);

  useEffect(() => {
    if (!label.trim() || materialId || materials.isLoading || materials.isError) return;
    const selected = findMaterial(label);
    if (selected) onChange(String(selected.id), label);
  }, [label, materialId, materials.isLoading, materials.isError, findMaterial, onChange]);

  const update = (nextLabel: string) => {
    const selected = findMaterial(nextLabel);
    const resolvedId = selected ? String(selected.id) : resolveMaterialId(nextLabel, options);
    onChange(resolvedId ? String(resolvedId) : '', nextLabel);
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

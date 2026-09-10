import { useQuery } from '@tanstack/react-query';

import { qk } from '@/api/queryKeys';
import { api } from '@/api/services';
import { SearchableSelect } from '@/components/ui/searchable-select';

type MaterialLookupProps = {
  label: string;
  materialId: string;
  onChange: (materialId: string, label: string) => void;
  required?: boolean;
};

export function MaterialLookup({ materialId, onChange, required = false }: MaterialLookupProps) {
  const materials = useQuery({
    queryKey: qk.materials({ lookup: 'active-picker' }),
    queryFn: () => api.materialsCatalog({ is_active: true, page_size: 100 }),
  });
  const options = (materials.data?.results || []).map((material) => ({ value: material.id, label: `${material.name} · ${material.code}` }));
  return <SearchableSelect required={required} value={materialId} options={options} placeholder={materials.isLoading ? 'Loading materials…' : 'Search material name or code'} onChange={(value) => {
    const selected = materials.data?.results.find((material) => String(material.id) === value);
    onChange(value, selected ? `${selected.name} · ${selected.code}` : '');
  }} />;
}

import type { Material } from '@/api/types';

export function materialOption(material: Material) {
  return `${material.name} (${material.code}) [${material.id}]`;
}

export function resolveMaterialId(value: string, materials: Material[]) {
  const bracket = value.match(/\[(\d+)]$/);
  if (bracket) return Number(bracket[1]);
  const normalized = value.toLowerCase().trim();
  return materials.find((material) => material.name.toLowerCase() === normalized || material.code.toLowerCase() === normalized)?.id || '';
}

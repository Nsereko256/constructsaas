import { describe, expect, it } from 'vitest';
import type { Material } from '@/api/types';
import { materialOption, resolveMaterialId } from './selectors';

const materials = [
  { id: 7, name: 'Hima Cement', code: 'CEM-HIMA' },
  { id: 8, name: 'Y16 Rebar', code: 'Y16' },
] as Material[];

describe('material selectors', () => {
  it('creates searchable material labels with stable ids', () => {
    expect(materialOption(materials[0])).toBe('Hima Cement (CEM-HIMA) [7]');
  });

  it('resolves by bracket id, name, or code', () => {
    expect(resolveMaterialId('Hima Cement (CEM-HIMA) [7]', materials)).toBe(7);
    expect(resolveMaterialId('Y16', materials)).toBe(8);
    expect(resolveMaterialId('Missing', materials)).toBe('');
  });
});

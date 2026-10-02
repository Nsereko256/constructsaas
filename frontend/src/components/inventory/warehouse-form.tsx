import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { api } from '@/api/services';
import type { Warehouse } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Field, inputClass } from '@/components/ui/field';

export function WarehouseForm({ warehouse, defaultWarehouse = false, onSaved, onCancel }: {
  warehouse?: Warehouse;
  defaultWarehouse?: boolean;
  onSaved: (warehouse: Warehouse) => void;
  onCancel: () => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState({ name: warehouse?.name || '', code: warehouse?.code || '', location: warehouse?.location || '', is_default: warehouse?.is_default ?? defaultWarehouse, is_active: warehouse?.is_active ?? true });
  const save = useMutation({
    mutationFn: () => api.saveWarehouse({ ...form, name: form.name.trim(), code: form.code.trim().toUpperCase(), location: form.location.trim() }, warehouse?.id),
    onSuccess: (data) => {
      void client.invalidateQueries({ queryKey: ['warehouses'] });
      void client.invalidateQueries({ queryKey: ['company-readiness'] });
      onSaved(data);
    },
  });
  const submit = (event: FormEvent) => { event.preventDefault(); if (!save.isPending) save.mutate(); };
  return <form onSubmit={submit} className="grid gap-3" aria-label={warehouse ? 'Edit warehouse' : 'Register warehouse'}>
    <fieldset disabled={save.isPending} className="grid min-w-0 gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Warehouse name" required><input className={inputClass} maxLength={150} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Warehouse code" required><input className={inputClass} maxLength={30} required value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} placeholder="e.g. MAIN" /></Field>
      </div>
      <p className="text-sm text-muted">Use this exact code in column E, “Warehouse code”, in your Excel workbook. Each warehouse needs a unique code within your company.</p>
      <Field label="Location / address"><input className={inputClass} maxLength={255} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_default} onChange={(e) => setForm({ ...form, is_default: e.target.checked, is_active: e.target.checked || form.is_active })} />Use as the default receiving warehouse</label>
      {form.is_default ? <p className="text-sm text-muted">This replaces the current default for future receipts. Existing stock and documents will not move.</p> : null}
      {warehouse ? <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_active} disabled={form.is_default} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />Active — available for new receipts and Excel imports</label> : null}
    </fieldset>
    {save.isError ? <p role="alert" className="rounded-md border border-critical/30 p-3 text-sm text-critical">{save.error.message}</p> : null}
    <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="secondary" disabled={save.isPending} onClick={onCancel}>Cancel</Button><Button type="submit" loading={save.isPending} disabled={!form.name.trim() || !form.code.trim()}>{warehouse ? 'Save warehouse' : 'Register warehouse'}</Button></div>
  </form>;
}

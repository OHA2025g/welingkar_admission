import { Plus, Trash2, ArrowUp, ArrowDown, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const tid = (path) => `field-${path.replace(/\./g, "-")}`;

const Leaf = ({ f, path, value, onChange, error, disabled }) => {
  const id = tid(path);
  const set = (v) => onChange(v);
  let input;
  if (f.type === "select") {
    input = (
      <Select value={value ?? ""} onValueChange={set} disabled={disabled}>
        <SelectTrigger id={id} data-testid={id} aria-invalid={!!error}><SelectValue placeholder="Select" /></SelectTrigger>
        <SelectContent>{f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
      </Select>
    );
  } else if (f.type === "switch") {
    return (
      <label className="flex items-center gap-3 text-sm sm:col-span-2">
        <Switch data-testid={id} checked={!!value} onCheckedChange={set} disabled={disabled} />{f.label}
      </label>
    );
  } else {
    const num = f.type === "number";
    input = (
      <Input id={id} data-testid={id} aria-invalid={!!error} disabled={disabled} type={num ? "number" : f.type || "text"} step="any"
        value={value ?? ""} onChange={(e) => set(num ? (e.target.value === "" ? null : Number(e.target.value)) : e.target.value)}
        className={error ? "border-destructive" : ""} />
    );
  }
  return (
    <div className={`space-y-1.5 ${f.wide ? "sm:col-span-2" : ""}`}>
      <Label htmlFor={id}>{f.label}</Label>
      {input}
      {error && <p data-testid={`${id}-error`} className="text-xs text-destructive">{error}</p>}
    </div>
  );
};

const GroupField = ({ f, path, value, set, errors, disabled }) => (
  <fieldset className="space-y-3 rounded-md border border-border p-4 sm:col-span-2">
    <legend className="px-1 text-sm font-semibold">{f.label}</legend>
    {errors[path] && <p className="text-xs text-destructive">{errors[path]}</p>}
    <FieldList fields={f.fields} value={value || {}} onChange={set} errors={errors} prefix={path} disabled={disabled} />
  </fieldset>
);

const ListItem = ({ f, path, i, it, items, set, errors, disabled }) => (
  <fieldset className="space-y-3 rounded-md border border-border p-4">
    <div className="flex items-center justify-between">
      <legend className="text-sm font-semibold">{f.itemLabel} {i + 1}</legend>
      {!disabled && items.length > (f.min || 0) && (
        <Button type="button" variant="ghost" size="sm" data-testid={`${tid(path)}-remove-${i}`} onClick={() => set(items.filter((_, j) => j !== i))}><Trash2 className="mr-1 h-3.5 w-3.5" />Remove</Button>
      )}
    </div>
    <FieldList fields={f.fields} value={it} errors={errors} prefix={`${path}.${i}`} disabled={disabled}
      onChange={(nv) => set(items.map((x, j) => (j === i ? nv : x)))} />
  </fieldset>
);

const ListField = ({ f, path, value, set, errors, disabled }) => {
  const items = value || [];
  return (
    <div className="space-y-3 sm:col-span-2">
      {errors[path] && <p data-testid={`${tid(path)}-error`} className="text-sm text-destructive">{errors[path]}</p>}
      {items.map((it, i) => <ListItem key={i} f={f} path={path} i={i} it={it} items={items} set={set} errors={errors} disabled={disabled} />)}
      {!disabled && items.length < f.max && (
        <Button type="button" variant="outline" size="sm" data-testid={`${tid(path)}-add`} onClick={() => set([...items, {}])}><Plus className="mr-1 h-4 w-4" />Add {f.itemLabel.toLowerCase()}</Button>
      )}
    </div>
  );
};

const KINDS = { group: GroupField, list: ListField };

const AnyField = ({ f, prefix, value, onChange, errors, disabled }) => {
  const path = prefix ? `${prefix}.${f.name}` : f.name;
  const set = (nv) => onChange({ ...value, [f.name]: nv });
  const K = KINDS[f.type];
  if (K) return <K f={f} path={path} value={value?.[f.name]} set={set} errors={errors} disabled={disabled} />;
  return <Leaf f={f} path={path} value={value?.[f.name]} onChange={set} error={errors[path]} disabled={disabled} />;
};

export function FieldList({ fields, value = {}, onChange, errors = {}, prefix = "", disabled }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.filter((f) => !f.showIf || f.showIf(value)).map((f) => (
        <AnyField key={f.name} f={f} prefix={prefix} value={value} onChange={onChange} errors={errors} disabled={disabled} />
      ))}
    </div>
  );
}

export const RankedPicker = ({ programs, value = [], onChange, disabled, max = 5 }) => {
  const move = (i, d) => { const a = [...value]; [a[i], a[i + d]] = [a[i + d], a[i]]; onChange(a); };
  const left = programs.filter((p) => !value.includes(p.code));
  return (
    <div className="space-y-4">
      <ol data-testid="preferences-ranked-list" className="space-y-2">
        {value.map((code, i) => (
          <li key={code} className="flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">{i + 1}</span>
            <span className="flex-1 text-sm font-medium">{programs.find((p) => p.code === code)?.name || code}</span>
            {!disabled && <>
              <Button type="button" size="icon" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="h-4 w-4" /></Button>
              <Button type="button" size="icon" variant="ghost" aria-label="Move down" disabled={i === value.length - 1} onClick={() => move(i, 1)}><ArrowDown className="h-4 w-4" /></Button>
              <Button type="button" size="icon" variant="ghost" aria-label="Remove" data-testid={`preference-remove-${code}`} onClick={() => onChange(value.filter((c) => c !== code))}><X className="h-4 w-4" /></Button>
            </>}
          </li>
        ))}
        {!value.length && <li className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">No preferences yet. Add at least one programme.</li>}
      </ol>
      {!disabled && value.length < max && (
        <Select value="" onValueChange={(c) => onChange([...value, c])}>
          <SelectTrigger data-testid="preferences-add-select" className="sm:w-96"><SelectValue placeholder="Add a programme…" /></SelectTrigger>
          <SelectContent>{left.map((p) => <SelectItem key={p.code} value={p.code}>{p.name} · {p.campus}</SelectItem>)}</SelectContent>
        </Select>
      )}
    </div>
  );
};

export const errorMap = (errors = []) => Object.fromEntries(errors.map((e) => [e.field, e.message]));

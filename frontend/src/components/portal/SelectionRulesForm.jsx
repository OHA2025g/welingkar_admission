import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const NUMS = [["exam_weight", "Exam weight (%)"], ["ga_weight", "GA weight (%)"], ["pi_weight", "PI weight (%)"],
  ["selected_cutoff", "Selection cut-off (composite)"], ["waitlist_cutoff", "Waitlist cut-off (composite)"],
  ["pi_booking_cutoff_hours", "PI booking cut-off (hours before slot)"], ["pi_reschedule_limit", "PI reschedule limit"]];

const toText = (rub) => (rub || []).map((c) => `${c.key} | ${c.label} | ${c.max}`).join("\n");
const fromText = (s) => s.split("\n").map((l) => l.split("|").map((x) => x.trim())).filter((p) => p[0])
  .map(([key, label, max]) => ({ key, label: label || key, max: Number(max) || 10 }));

const Rubric = ({ id, label, value, onChange }) => (
  <div className="space-y-1.5 sm:col-span-2">
    <Label htmlFor={id}>{label} <span className="text-xs text-muted-foreground">(one per line: key | label | max)</span></Label>
    <Textarea id={id} data-testid={`${id}-input`} rows={5} className="font-mono text-xs" defaultValue={toText(value)} onBlur={(e) => onChange(fromText(e.target.value))} />
  </div>
);

export const SelectionRulesForm = ({ c, set }) => (
  <div className="grid gap-4 sm:grid-cols-2">
    {NUMS.map(([k, l]) => (
      <div key={k} className="space-y-1.5"><Label htmlFor={`sr-${k}`}>{l}</Label>
        <Input id={`sr-${k}`} data-testid={`sr-${k}-input`} type="number" value={c[k]} onChange={(e) => set({ ...c, [k]: Number(e.target.value) })} /></div>
    ))}
    <Rubric id="sr-ga-rubric" label="GA rubric" value={c.ga_rubric} onChange={(v) => set({ ...c, ga_rubric: v })} />
    <Rubric id="sr-pi-rubric" label="PI rubric (question-level)" value={c.pi_rubric} onChange={(v) => set({ ...c, pi_rubric: v })} />
    <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="sr-notes">Notes</Label><Textarea id="sr-notes" rows={2} value={c.notes} onChange={(e) => set({ ...c, notes: e.target.value })} /></div>
  </div>
);

export const SelectionRulesSummary = ({ c }) => (
  <ul className="space-y-1 text-sm">
    <li>Weights: exam <b>{c.exam_weight}%</b> · GA <b>{c.ga_weight}%</b> · PI <b>{c.pi_weight}%</b></li>
    <li>Cut-offs: selected ≥ <b>{c.selected_cutoff}</b> · waitlist ≥ <b>{c.waitlist_cutoff}</b></li>
    <li className="text-muted-foreground">GA rubric {c.ga_rubric.length} items · PI rubric {c.pi_rubric.length} questions · booking closes {c.pi_booking_cutoff_hours}h before · max {c.pi_reschedule_limit} reschedules</li>
  </ul>
);

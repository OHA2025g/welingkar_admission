import { useCallback, useEffect, useState } from "react";
import { Plus, CheckCircle2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { http, errMsg, fmtIST, fmtINR } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { SelectionRulesForm, SelectionRulesSummary } from "@/components/portal/SelectionRulesForm";

const lines = (a) => (a || []).join("\n");
const unlines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);

const TfwForm = ({ c, set }) => (
  <div className="grid gap-4 sm:grid-cols-2">
    <label className="flex items-center gap-3 text-sm sm:col-span-2"><Switch data-testid="tfw-enabled-switch" checked={c.enabled} onCheckedChange={(v) => set({ ...c, enabled: v })} />TFW scheme enabled</label>
    <div className="space-y-1.5"><Label htmlFor="tfw-share">Seat share (%)</Label><Input id="tfw-share" data-testid="tfw-share-input" type="number" step="0.5" value={c.seat_share_percent} onChange={(e) => set({ ...c, seat_share_percent: Number(e.target.value) })} /></div>
    <div className="space-y-1.5"><Label htmlFor="tfw-income">Family income limit (INR)</Label><Input id="tfw-income" data-testid="tfw-income-input" type="number" value={c.family_income_limit_inr} onChange={(e) => set({ ...c, family_income_limit_inr: Number(e.target.value) })} /></div>
    <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="tfw-routes">Eligible routes (comma separated)</Label><Input id="tfw-routes" data-testid="tfw-routes-input" value={(c.eligible_routes || []).join(", ")} onChange={(e) => set({ ...c, eligible_routes: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} /></div>
    <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="tfw-docs">Required documents (one per line)</Label><Textarea id="tfw-docs" data-testid="tfw-docs-input" rows={3} value={lines(c.required_documents)} onChange={(e) => set({ ...c, required_documents: unlines(e.target.value) })} /></div>
    <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="tfw-notes">Notes</Label><Textarea id="tfw-notes" rows={2} value={c.notes} onChange={(e) => set({ ...c, notes: e.target.value })} /></div>
  </div>
);

const RefundForm = ({ c, set }) => {
  const tier = (i, k, v) => set({ ...c, tiers: c.tiers.map((t, j) => (j === i ? { ...t, [k]: v } : t)) });
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-3 text-sm"><Switch data-testid="refund-appfee-switch" checked={c.application_fee_refundable} onCheckedChange={(v) => set({ ...c, application_fee_refundable: v })} />Application fee refundable</label>
      <div className="space-y-1.5"><Label htmlFor="rf-proc">Processing fee deducted (INR)</Label><Input id="rf-proc" data-testid="refund-processing-fee-input" type="number" value={c.processing_fee_inr} onChange={(e) => set({ ...c, processing_fee_inr: Number(e.target.value) })} /></div>
      <div className="space-y-1.5"><Label htmlFor="rf-signoff">Super Admin sign-off at or above (INR)</Label><Input id="rf-signoff" data-testid="refund-signoff-threshold-input" type="number" min="0" value={c.super_admin_signoff_above_inr ?? 50000} onChange={(e) => set({ ...c, super_admin_signoff_above_inr: Number(e.target.value) })} /></div>
      <fieldset className="space-y-2"><legend className="text-sm font-medium">Tiers</legend>
        {c.tiers.map((t, i) => (
          <div key={i} className="grid grid-cols-[1fr_90px_90px_36px] items-center gap-2">
            <Input aria-label="Tier label" data-testid={`refund-tier-label-${i}`} value={t.label} onChange={(e) => tier(i, "label", e.target.value)} />
            <Input aria-label="Min days before start" data-testid={`refund-tier-days-${i}`} type="number" value={t.days_before_start_min} onChange={(e) => tier(i, "days_before_start_min", Number(e.target.value))} />
            <Input aria-label="Refund percent" data-testid={`refund-tier-percent-${i}`} type="number" value={t.refund_percent} onChange={(e) => tier(i, "refund_percent", Number(e.target.value))} />
            <Button type="button" variant="ghost" size="icon" aria-label="Remove tier" onClick={() => set({ ...c, tiers: c.tiers.filter((_, j) => j !== i) })}><Trash2 className="h-4 w-4" /></Button>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">Label · min days before start · refund %</p>
        <Button type="button" variant="outline" size="sm" data-testid="refund-add-tier-button" onClick={() => set({ ...c, tiers: [...c.tiers, { label: "New tier", days_before_start_min: 0, refund_percent: 0 }] })}>Add tier</Button>
      </fieldset>
      <div className="space-y-1.5"><Label htmlFor="rf-notes">Notes</Label><Textarea id="rf-notes" rows={2} value={c.notes} onChange={(e) => set({ ...c, notes: e.target.value })} /></div>
    </div>
  );
};

const Summary = ({ k, c }) => k === "selection_rules" ? <SelectionRulesSummary c={c} /> : k === "tfw_rules" ? (
  <ul className="space-y-1 text-sm">
    <li>Status: <b>{c.enabled ? "Enabled" : "Disabled"}</b> · Seat share <b>{c.seat_share_percent}%</b></li>
    <li>Income limit <b>{fmtINR(c.family_income_limit_inr)}</b> · Routes <b>{c.eligible_routes.join(", ") || "—"}</b></li>
    <li className="text-muted-foreground">{c.required_documents.length} required documents</li>
  </ul>
) : k === "refund_policy" ? (
  <ul className="space-y-1 text-sm">
    <li>Processing fee <b>{fmtINR(c.processing_fee_inr)}</b> · Application fee {c.application_fee_refundable ? "refundable" : "non-refundable"}</li>
    <li>Super Admin sign-off at or above <b>{fmtINR(c.super_admin_signoff_above_inr ?? 50000)}</b></li>
    {c.tiers.map((t) => <li key={t.label} className="text-muted-foreground">{t.label}: <b className="text-foreground">{t.refund_percent}%</b> (≥ {t.days_before_start_min} days)</li>)}
  </ul>
) : (
  <p className="text-sm text-muted-foreground">{c.notes || "Active policy"}</p>
);

const PolicyBlock = ({ p, write, reload }) => {
  const [versions, setVersions] = useState([]);
  const [draft, setDraft] = useState(null);
  const [note, setNote] = useState("");
  const [confirm, setConfirm] = useState(null);
  const load = useCallback(() => http.get(`/policies/${p.key}/versions`).then((r) => setVersions(r.data)), [p.key]);
  useEffect(() => { load(); }, [load, p]);
  const save = async () => {
    try { await http.post(`/policies/${p.key}/versions`, { content: draft, change_note: note }); toast.success("Draft saved"); setDraft(null); setNote(""); load(); reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const activate = async (v) => {
    try { await http.post(`/policies/${p.key}/versions/${v}/activate`); toast.success(`v${v} is now active`); load(); reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setConfirm(null); }
  };
  const Form = { tfw_rules: TfwForm, selection_rules: SelectionRulesForm }[p.key] || RefundForm;
  return (
    <Card testId={`policy-card-${p.key}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{p.title}</h2>
          <p className="text-sm text-muted-foreground">Active: <b data-testid={`policy-active-version-${p.key}`}>v{p.active?.version || "—"}</b> · {versions.length} versions</p>
        </div>
        {write && <Button data-testid={`new-draft-${p.key}`} size="sm" variant="outline" onClick={() => setDraft(structuredClone(p.active?.content))}><Plus className="mr-1 h-4 w-4" />New draft</Button>}
      </div>
      {p.active && <div className="mt-4 rounded-md bg-secondary p-4"><Summary k={p.key} c={p.active.content} /></div>}
      <ol className="mt-5 divide-y divide-border" data-testid={`policy-versions-${p.key}`}>
        {versions.map((v) => (
          <li key={v.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
            <span className="w-10 font-mono font-semibold">v{v.version}</span>
            <StatusPill testId={`policy-${p.key}-v${v.version}-status`} status={v.status} />
            <span className="flex-1 text-muted-foreground">{v.change_note}</span>
            <span className="text-xs text-muted-foreground">{v.created_by} · {fmtIST(v.created_at)}</span>
            {write && v.status === "draft" && <Button data-testid={`activate-${p.key}-v${v.version}`} size="sm" onClick={() => setConfirm(v.version)}><CheckCircle2 className="mr-1 h-3.5 w-3.5" />Activate</Button>}
          </li>
        ))}
      </ol>
      <Dialog open={!!draft} onOpenChange={(o) => !o && setDraft(null)}>
        <DialogContent data-testid={`policy-draft-dialog-${p.key}`} className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader><DialogTitle>New draft · {p.title}</DialogTitle></DialogHeader>
          {draft && <Form c={draft} set={setDraft} />}
          <div className="space-y-1.5"><Label htmlFor={`note-${p.key}`}>Change note (required)</Label><Input id={`note-${p.key}`} data-testid="policy-change-note-input" value={note} onChange={(e) => setNote(e.target.value)} /></div>
          <Button data-testid="policy-save-draft-button" onClick={save} disabled={note.trim().length < 3}>Save as draft v{(versions[0]?.version || 0) + 1}</Button>
        </DialogContent>
      </Dialog>
      <AlertDialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Activate v{confirm}?</AlertDialogTitle>
            <AlertDialogDescription>The current active version will be superseded. Historical versions are kept and the change is audited.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction data-testid="confirm-activate-button" onClick={() => activate(confirm)}>Activate</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
};

export default function PoliciesPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const load = useCallback(() => http.get("/policies").then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="policies-page">
      <PageHeader eyebrow="Configuration" title="Policies" description="Versioned and append-only. Drafts become effective only when activated; earlier versions remain available for audit." />
      <div className="grid gap-6 xl:grid-cols-2">{rows.map((p) => <PolicyBlock key={p.key} p={p} write={can(user, "policies.write")} reload={load} />)}</div>
    </div>
  );
}

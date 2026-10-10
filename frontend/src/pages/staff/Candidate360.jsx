import { Fragment, useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { http, errMsg, fmtINR, fmtIST } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const KV = ({ rows, testId }) => (
  <dl data-testid={testId} className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
    {rows.map(([k, v]) => <Fragment key={k}><dt className="text-muted-foreground">{k}</dt><dd className="break-all">{v ?? "—"}</dd></Fragment>)}
  </dl>
);

const EditDialog = ({ open, p, onClose, onSaved }) => {
  const [f, setF] = useState({ name: p.name, city: p.city || "", state: p.state || "", reason: "" });
  const save = async () => {
    const body = { reason: f.reason, ...Object.fromEntries(["name", "city", "state"].filter((k) => f[k] && f[k] !== p[k]).map((k) => [k, f[k]])) };
    try { const { data } = await http.patch(`/admin/candidates/${p.id}/profile`, body); toast.success("Profile corrected (audited)"); onSaved(data); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="c360-edit-dialog">
        <DialogHeader><DialogTitle>Controlled correction</DialogTitle></DialogHeader>
        {["name", "city", "state"].map((k) => <Input key={k} data-testid={`c360-edit-${k}`} placeholder={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
        <Input data-testid="c360-edit-reason" placeholder="Reason (required, audited)" value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} />
        <Button data-testid="c360-edit-save" onClick={save} disabled={f.reason.trim().length < 5}>Save correction</Button>
      </DialogContent>
    </Dialog>
  );
};

export default function Candidate360() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(false);
  const load = useCallback(() => http.get(`/admin/candidates/${id}/360`).then((r) => setD(r.data)), [id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  const p = d.profile;
  return (
    <div data-testid="candidate-360-page">
      <PageHeader eyebrow={`Candidate 360 · ${p.candidate_ref}`} title={p.name} description={d.masked ? "Read-only. Contact details are masked for your role." : "Read-only overview. Corrections are limited to name and location, with a recorded reason."}
        actions={d.can_edit && <Button variant="outline" data-testid="c360-edit-button" onClick={() => setEdit(true)}><Pencil className="mr-1.5 h-4 w-4" />Correct profile</Button>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card testId="c360-profile"><p className="mb-3 font-semibold">Profile</p><KV testId="c360-profile-kv" rows={[["Email", p.email], ["Mobile", p.mobile], ["Location", `${p.city || "—"}, ${p.state || "—"}`], ["Identity", p.status]]} /></Card>
        <Card testId="c360-application"><p className="mb-3 font-semibold">Part A</p><KV rows={[["Application", d.application.application_ref], ["Status", d.application.status], ["Submitted", fmtIST(d.application.submitted_at)], ["Interviews", d.interviews.map((b) => `${b.type} ${b.status}`).join(", ") || "—"], ["Results", d.results.map((r) => `${r.program_code} ${r.outcome}${r.rank ? ` #${r.rank}` : ""}`).join(", ") || "—"]]} /></Card>
        <Card testId="c360-partb"><p className="mb-3 font-semibold">Part B</p><KV rows={[["Eligibility", d.partb.eligibility.map((e) => `${e.program_code} ${e.outcome}`).join(", ") || "—"], ["Consent", d.partb.consent_version ? `v${d.partb.consent_version}` : "—"], ["Documents", `${d.partb.docs_initial} / ${d.partb.docs_admission}`], ["Seat", d.partb.seat ? `${d.partb.seat.program_code} (${d.partb.seat.status})` : "None"]]} /></Card>
        <Card testId="c360-payments" className="lg:col-span-2"><p className="mb-3 font-semibold">Payments</p>
          <ul className="divide-y divide-border text-sm">{d.payments.map((o) => <li key={o.order_ref} className="flex flex-wrap justify-between gap-2 py-2"><span className="font-mono text-xs">{o.order_ref}</span><span>{o.fee_code.replace("_", " ")} · {o.origin}</span><span className="tabular-nums">{fmtINR(o.amount_paise / 100)}{o.refunded_paise ? ` (refunded ${fmtINR(o.refunded_paise / 100)})` : ""}</span><StatusPill status={o.status} /></li>)}</ul></Card>
        <Card testId="c360-cancellations"><p className="mb-3 font-semibold">Cancellations</p>
          {d.cancellations.length ? d.cancellations.map((c) => <p key={c.cancellation_ref} className="text-sm">{c.cancellation_ref} · {c.program_code} · <StatusPill status={c.status} /></p>) : <p className="text-sm text-muted-foreground">None</p>}</Card>
        <Card testId="c360-audit" className="lg:col-span-3"><p className="mb-3 font-semibold">Recent activity</p>
          <ul className="divide-y divide-border text-sm">{d.audit.map((a, i) => <li key={i} className="flex justify-between gap-3 py-1.5"><span className="font-mono text-xs">{a.action}</span><span className="text-xs text-muted-foreground">{a.actor} · {fmtIST(a.at)}</span></li>)}</ul></Card>
      </div>
      {edit && <EditDialog open={edit} p={p} onClose={() => setEdit(false)} onSaved={(x) => { setD(x); setEdit(false); }} />}
    </div>
  );
}

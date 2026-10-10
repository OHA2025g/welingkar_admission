import { useCallback, useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { PolicyHelp } from "@/components/portal/PolicyHelp";

const paise = (p) => fmtINR((p || 0) / 100);

export const QuoteTable = ({ q, testId }) => (
  <dl data-testid={testId} className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
    <dt className="text-muted-foreground">Policy tier</dt><dd>{q.tier} · v{q.policy_version}</dd>
    <dt className="text-muted-foreground">Days before start</dt><dd className="tabular-nums">{q.days_before_start}</dd>
    <dt className="text-muted-foreground">Admission fee paid</dt><dd className="tabular-nums">{paise(q.paid_paise)}</dd>
    <dt className="text-muted-foreground">Deduction</dt><dd className="tabular-nums">{paise(q.deduction_paise)}</dd>
    <dt className="text-muted-foreground">Already refunded</dt><dd data-testid={`${testId}-refunded`} className="tabular-nums">{paise(q.already_refunded_paise)}</dd>
    <dt className="font-semibold">Refund due</dt><dd data-testid={`${testId}-refund`} className="font-semibold tabular-nums">{paise(q.refund_paise)}</dd>
  </dl>
);

const RequestForm = ({ onDone }) => {
  const [f, setF] = useState({ reason: "", account_holder: "", account_number: "", ifsc: "", bank_name: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { await http.post("/candidate/cancellation", f); toast.success("Cancellation request submitted"); onDone(); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} data-testid="cancellation-form" className="grid gap-3 sm:grid-cols-2">
      <div className="sm:col-span-2"><Label>Reason for cancellation</Label><Textarea data-testid="cancellation-reason" value={f.reason} onChange={set("reason")} /></div>
      <div><Label>Account holder</Label><Input data-testid="cancellation-account-holder" value={f.account_holder} onChange={set("account_holder")} /></div>
      <div><Label>Account number</Label><Input data-testid="cancellation-account-number" inputMode="numeric" value={f.account_number} onChange={set("account_number")} /></div>
      <div><Label>IFSC</Label><Input data-testid="cancellation-ifsc" value={f.ifsc} onChange={(e) => setF({ ...f, ifsc: e.target.value.toUpperCase() })} placeholder="HDFC0001234" /></div>
      <div><Label>Bank name</Label><Input data-testid="cancellation-bank-name" value={f.bank_name} onChange={set("bank_name")} /></div>
      <Button type="submit" variant="destructive" data-testid="cancellation-submit" disabled={busy || f.reason.trim().length < 10} className="sm:col-span-2">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Request seat cancellation"}</Button>
    </form>
  );
};

export default function CancellationPage() {
  const [d, setD] = useState(null);
  const load = useCallback(() => http.get("/candidate/cancellation").then((r) => setD(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const receipt = async () => { try { await downloadFile("/candidate/cancellation/receipt", "cancellation-receipt.pdf"); toast.success("Receipt downloaded"); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  const c = d.cancellation;
  return (
    <div data-testid="cancellation-page">
      <PageHeader eyebrow="Part B" title="Seat cancellation" description="Refunds follow the active refund policy and the days remaining before programme start. Your bank details are stored masked." />
      <div className="mb-6"><PolicyHelp topic="cancellation" /></div>
      {c && <Card testId="cancellation-status-card" className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div><p className="font-mono text-xs text-muted-foreground">{c.cancellation_ref}</p><p className="mt-1 font-semibold">{c.program_code}</p></div>
          <StatusPill testId="cancellation-status" status={c.status} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">Requested {fmtIST(c.created_at)} · Bank {c.bank.bank_name} {c.bank.number}</p>
        {c.review_remarks && <p className="mt-2 text-sm">Review: {c.review_remarks}</p>}
        {c.quote && <div className="mt-4"><QuoteTable q={c.quote} testId="cancellation-quote" /></div>}
        {c.timeline?.length > 0 && <ol data-testid="refund-timeline" className="mt-5 space-y-3">
          {c.timeline.map((s) => (
            <li key={s.key} data-testid={`timeline-${s.key}`} data-state={s.state} className="flex min-w-0 items-start gap-2 text-sm">
              <span className={s.state === "done" ? "text-emerald-700" : s.state === "current" ? "font-semibold text-primary" : "text-muted-foreground"}>{s.state === "done" ? "●" : s.state === "current" ? "◉" : "○"}</span>
              <span className={`min-w-0 break-words ${s.state === "upcoming" ? "text-muted-foreground" : ""}`}>{s.label}</span>
            </li>
          ))}
        </ol>}
        {["approved", "pending_signoff", "refunded", "refund_failed", "closed"].includes(c.status) && <Button className="mt-4 min-h-11 w-full sm:w-auto" data-testid="cancellation-receipt-button" onClick={receipt}><Download className="mr-1.5 h-4 w-4" />Cancellation receipt</Button>}
      </Card>}
      {d.can_request ? <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Card testId="cancellation-estimate"><p className="mb-1 font-semibold">Your seat: {d.seat.program_code}</p>
          <p className="mb-4 text-xs text-muted-foreground">Estimated refund if approved today</p><QuoteTable q={d.estimate} testId="cancellation-estimate-quote" /></Card>
        <Card><RequestForm onDone={load} /></Card>
      </div> : !c && <Card testId="cancellation-no-seat"><p className="text-sm text-muted-foreground">You don't hold a seat, so there is nothing to cancel.</p></Card>}
    </div>
  );
}

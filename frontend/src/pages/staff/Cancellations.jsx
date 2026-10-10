import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, Empty, PageHeader, StatusPill } from "@/components/portal/ui";
import { useAuth, can } from "@/context/AuthContext";
import { StepUpOtp, stepUpReady } from "@/components/finance/StepUpOtp";
import { QuoteTable } from "@/pages/candidate/Cancellation";

const ActionDialog = ({ x, onClose, onDone }) => {
  const [remarks, setRemarks] = useState("");
  const [otp, setOtp] = useState(null);
  const refund = x?.status === "approved" || x?.status === "refund_failed";
  const act = async (kind) => {
    try {
      if (kind === "refund") { const { data } = await http.post(`/accounts/cancellations/${x.id}/refund`, otp); toast.success(`Refund ${data.refund.refund_ref} ${data.refund.status} (MOCKED gateway)`); }
      else { await http.post(`/partb/cancellations/${x.id}/${kind}`, { remarks }); toast.success(kind === "approve" ? "Approved · seat released" : "Rejected"); }
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={!!x} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="cancellation-action-dialog">
        <DialogHeader><DialogTitle>{x?.cancellation_ref} · {x?.name}</DialogTitle>
          <DialogDescription>{x?.program_code} · {x?.reason}</DialogDescription></DialogHeader>
        {x?.quote && <QuoteTable q={x.quote} testId="cancellation-dialog-quote" />}
        <p className="text-xs text-muted-foreground">Bank: {x?.bank.bank_name} · {x?.bank.number} · {x?.bank.ifsc}</p>
        {refund && (x?.quote?.refund_paise || 0) > 0 ? <>
          <StepUpOtp value={otp} onChange={setOtp} />
          <Button data-testid="cancellation-refund-button" onClick={() => act("refund")} disabled={!stepUpReady(otp)}>Execute refund {fmtINR((x?.quote?.refund_paise || 0) / 100)}</Button>
        </> : refund ? <p className="text-sm text-muted-foreground">Earlier refunds already cover the amount due under the refund policy.</p> : <>
          <Input data-testid="cancellation-remarks" placeholder="Review remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          <div className="flex gap-2">
            <Button className="flex-1" data-testid="cancellation-approve-button" onClick={() => act("approve")} disabled={remarks.trim().length < 5}>Approve & release seat</Button>
            <Button className="flex-1" variant="outline" data-testid="cancellation-reject-button" onClick={() => act("reject")} disabled={remarks.trim().length < 5}>Reject</Button>
          </div>
        </>}
      </DialogContent>
    </Dialog>
  );
};

export default function CancellationsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [signoffs, setSignoffs] = useState([]);
  const [sel, setSel] = useState(null);
  const [remarks, setRemarks] = useState("");
  const load = useCallback(() => http.get("/partb/cancellations", { params: { page, page_size: 50 } })
    .then((r) => { const d = r.data; setRows(Array.isArray(d) ? d : d.rows); setTotal(Array.isArray(d) ? d.length : d.total); setError(""); })
    .catch((e) => setError(errMsg(e))), [page]);
  const loadSignoffs = useCallback(() => {
    if (!can(user, "refunds.signoff")) return Promise.resolve();
    return http.get("/refund-signoffs?status=pending").then((r) => setSignoffs(r.data));
  }, [user]);
  useEffect(() => { load(); loadSignoffs(); }, [load, loadSignoffs]);
  const actionable = (r) => (r.status === "requested" && can(user, "cancellations.review")) || (["approved", "refund_failed"].includes(r.status) && can(user, "payments.refund") && (r.quote?.refund_paise || 0) > 0);
  const exp = async () => { try { await downloadFile("/partb/cancellations/export", "cancellations.xlsx"); toast.success("Cancellation report downloaded"); } catch (e) { toast.error(errMsg(e)); } };
  const decide = async (id, kind) => {
    try {
      await http.post(`/refund-signoffs/${id}/${kind}`, { remarks });
      toast.success(kind === "approve" ? "Sign-off approved. Accounts can pay out." : "Sign-off declined. The payout will not proceed.");
      setRemarks("");
      load(); loadSignoffs();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="cancellations-page">
      <PageHeader eyebrow="Part B · Finance" title="Cancellations & refunds" description="Approval releases the seat exactly once. Refunds at or above the policy threshold wait for Super Admin sign-off. Accounts then pays out with a step-up email code."
        actions={<Button variant="outline" data-testid="cancellations-export-button" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Cancellation report</Button>} />
      {can(user, "refunds.signoff") && <Card testId="signoff-queue" className="mb-6">
        <p className="mb-3 font-semibold">Sign-off queue</p>
        {!signoffs.length ? <p className="text-sm text-muted-foreground">No refunds are waiting for your sign-off.</p> : (
          <div className="space-y-3">
            {signoffs.map((s) => (
              <div key={s.id} data-testid={`signoff-row-${s.id}`} className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3">
                <div>
                  <p className="font-mono text-xs">{s.order_ref}</p>
                  <p className="text-sm">{fmtINR(s.amount)} · {s.reason}</p>
                  <p className="text-xs text-muted-foreground">Requested by {s.requested_by}</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" data-testid={`signoff-approve-${s.id}`} onClick={() => decide(s.id, "approve")}>Approve payout</Button>
                  <Button size="sm" variant="outline" data-testid={`signoff-reject-${s.id}`} onClick={() => decide(s.id, "reject")} disabled={remarks.trim().length < 5}>Decline</Button>
                </div>
              </div>
            ))}
            <Input data-testid="signoff-remarks" placeholder="Remarks, required to decline" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          </div>
        )}
      </Card>}
      <Card className="overflow-x-auto p-0">
        <Table data-testid="cancellations-table">
          <TableHeader><TableRow>{["Ref", "Candidate", "Program", "Requested", "Refunded amount", "Refund due", "Seat", "Status", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`cancellation-row-${r.id}`}>
                <TableCell className="font-mono text-xs">{r.cancellation_ref}</TableCell>
                <TableCell>{r.name}<div className="text-xs text-muted-foreground">{r.application_ref}</div></TableCell>
                <TableCell>{r.program_code}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtIST(r.created_at)}</TableCell>
                <TableCell className="tabular-nums" data-testid={`cancellation-refunded-${r.id}`}>{fmtINR((r.quote?.already_refunded_paise || 0) / 100)}</TableCell>
                <TableCell className="tabular-nums" data-testid={`cancellation-due-${r.id}`}>{fmtINR((r.quote?.refund_paise || 0) / 100)}</TableCell>
                <TableCell className="text-xs">{r.seat_released ? "Released" : "Held"}</TableCell>
                <TableCell><StatusPill testId={`cancellation-status-${r.id}`} status={r.status} /></TableCell>
                <TableCell>{actionable(r) && <Button size="sm" data-testid={`cancellation-open-${r.id}`} onClick={() => setSel(r)}>{r.status === "requested" ? "Review" : "Refund"}</Button>}
                  {r.status === "pending_signoff" && <span className="text-xs text-muted-foreground">Waiting for Super Admin</span>}</TableCell>
              </TableRow>
            ))}
            {!rows.length && <TableRow><TableCell colSpan={9}><Empty testId="cancellations-empty" text={error || "No cancellation requests. Requests appear here after a candidate asks to give up a seat."} /></TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
      {total > 50 && (
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Previous</Button>
          <Button variant="outline" size="sm" disabled={page * 50 >= total} onClick={() => setPage((n) => n + 1)}>Next</Button>
        </div>
      )}
      <ActionDialog x={sel} onClose={() => setSel(null)} onDone={() => { setSel(null); load(); loadSignoffs(); }} />
    </div>
  );
}

import { useState } from "react";
import { Download, Eye } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, Empty, StatusPill } from "@/components/portal/ui";
import { useAuth, can } from "@/context/AuthContext";

const ReviewDialog = ({ o, onClose, onDone }) => {
  const [reason, setReason] = useState("");
  const [file, setFile] = useState(null);
  const act = async (kind) => {
    try {
      if (kind === "verify") { const fd = new FormData(); if (file) fd.append("proof", file); await http.post(`/accounts/payments/${o.id}/verify`, fd); }
      else await http.post(`/accounts/payments/${o.id}/reject`, { reason });
      toast.success(kind === "verify" ? "Marked as paid" : "Rejected"); onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={!!o} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="offline-review-dialog">
        <DialogHeader><DialogTitle>Review {o?.txn_ref}</DialogTitle></DialogHeader>
        <p className="text-sm">{o?.candidate_name} · {o?.offline_mode?.toUpperCase()} · {fmtINR(o?.amount)} · {o?.txn_date}</p>
        <p data-testid="offline-review-proof" className="text-xs text-muted-foreground">{o?.proof_file_id ? "Candidate attached proof." : "No proof attached — upload one to mark as paid."}</p>
        <Input data-testid="offline-review-proof-input" type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <Button data-testid="offline-verify-button" onClick={() => act("verify")} disabled={!o?.proof_file_id && !file}>Verify & mark paid</Button>
        <Input data-testid="offline-reject-reason" placeholder="Rejection reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button variant="destructive" data-testid="offline-reject-button" onClick={() => act("reject")} disabled={reason.trim().length < 5}>Reject</Button>
      </DialogContent>
    </Dialog>
  );
};

export const PaymentsTab = ({ data, onChange, page = 1, setPage }) => {
  const { user } = useAuth();
  const [review, setReview] = useState(null);
  const s = data.summary;
  const exp = async () => { try { await downloadFile("/accounts/payments/export", "payments.xlsx"); toast.success("Export downloaded (audited)"); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div>
      <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-5">
        {[["Orders", s.orders], ["Paid", s.paid], ["Collected", fmtINR(s.collected)], ["Refunded", fmtINR(s.refunded)], ["Awaiting verification", s.awaiting_verification]].map(([k, v], i) => (
          <Card key={k} testId={`payments-kpi-${i}`} className="p-4"><p className="text-xs uppercase tracking-wider text-muted-foreground">{k}</p><p className="mt-1 font-['Outfit'] text-2xl font-bold tabular-nums">{v}</p></Card>))}
      </div>
      <div className="mb-3 flex items-center justify-between">
        {data.masked ? <p data-testid="payments-masked-note" className="text-xs text-muted-foreground">Contact and transaction details are masked for your role.</p> : <span />}
        <Button size="sm" variant="outline" data-testid="payments-export-button" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Export Excel</Button>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="payments-table">
          <TableHeader><TableRow>{["Order", "Fee", "Candidate", "Origin", "Amount", "Refunded", "Status", "Paid", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {!data.rows.length && <TableRow><TableCell colSpan={9}><Empty testId="payments-empty" text="No payments for this view. Record an offline payment, or wait for a candidate to check out." /></TableCell></TableRow>}
            {data.rows.map((o) => (
              <TableRow key={o.id} data-testid={`payment-row-${o.id}`}>
                <TableCell className="font-mono text-xs">{o.order_ref}{o.txn_ref && <div className="text-muted-foreground">{o.txn_ref}</div>}</TableCell>
                <TableCell className="text-xs">{o.fee_code.replace("_", " ")}</TableCell>
                <TableCell className="text-sm">{o.candidate_name}<div className="text-xs text-muted-foreground">{o.candidate_email}</div></TableCell>
                <TableCell className="text-xs">{o.origin === "offline" ? `offline · ${o.offline_mode}` : o.provider}</TableCell>
                <TableCell className="tabular-nums">{fmtINR(o.amount)}</TableCell>
                <TableCell className="tabular-nums">{fmtINR(o.refunded_amount)}</TableCell>
                <TableCell><StatusPill status={o.status} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtIST(o.paid_at)}</TableCell>
                <TableCell>{o.status === "awaiting_verification" && can(user, "payments.verify") &&
                  <Button size="sm" variant="outline" data-testid={`payment-review-${o.id}`} onClick={() => setReview(o)}><Eye className="mr-1 h-3.5 w-3.5" />Review</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      {setPage && data.total > (data.page_size || 50) && (
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <Button variant="outline" size="sm" disabled={page * (data.page_size || 50) >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      )}
      <ReviewDialog o={review} onClose={() => setReview(null)} onDone={() => { setReview(null); onChange(); }} />
    </div>
  );
};

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, fmtIST } from "@/lib/api";
import { Card, Empty, StatusPill } from "@/components/portal/ui";
import { useAuth, can } from "@/context/AuthContext";

export const ExceptionsTab = () => {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/accounts/exceptions").then((r) => setD(r.data)); }, []);
  if (!d) return null;
  if (!d.orders.length && !d.failed_refunds.length) return <Empty text="No payment exceptions." />;
  return (
    <Card className="overflow-x-auto p-0">
      <Table data-testid="exceptions-table">
        <TableHeader><TableRow>{["Order", "Candidate", "Amount", "Exception", "Detail"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {d.orders.map((o) => (
            <TableRow key={o.id + o.exception} data-testid={`exception-row-${o.id}`}>
              <TableCell className="font-mono text-xs">{o.order_ref}</TableCell><TableCell>{o.candidate_name}</TableCell>
              <TableCell className="tabular-nums">{fmtINR(o.amount)}</TableCell><TableCell><StatusPill status={o.exception} /></TableCell>
              <TableCell className="text-xs text-muted-foreground">{o.failure_reason || fmtIST(o.created_at)}</TableCell>
            </TableRow>))}
          {d.failed_refunds.map((r) => (
            <TableRow key={r.id}><TableCell className="font-mono text-xs">{r.refund_ref}</TableCell><TableCell>—</TableCell>
              <TableCell className="tabular-nums">{fmtINR(r.amount_paise / 100)}</TableCell><TableCell><StatusPill status="refund_failed" /></TableCell>
              <TableCell className="text-xs">{r.error}</TableCell></TableRow>))}
        </TableBody>
      </Table>
    </Card>
  );
};

export const ReconTab = () => {
  const { user } = useAuth();
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => http.get("/accounts/reconciliation").then((r) => setRuns(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const run = async () => {
    setBusy(true);
    try { const { data } = await http.post("/accounts/reconciliation/run"); toast.success(`Checked ${data.checked} gateway orders · ${data.flags.length} flags`); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const last = runs[0];
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">Compares every Stripe test order with the gateway, checks refund totals and flags multiple payments for the same fee.</p>
        {can(user, "payments.refund") && <Button data-testid="recon-run-button" onClick={run} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><RefreshCw className="mr-1.5 h-4 w-4" />Run reconciliation</>}</Button>}
      </div>
      {!last ? <Empty text="No reconciliation run yet." /> : <Card testId="recon-last-run">
        <p className="text-sm">Last run {fmtIST(last.at)} by {last.by} · <span data-testid="recon-checked">{last.checked}</span> checked · <span data-testid="recon-flag-count">{last.flags.length}</span> mismatch flags</p>
        {last.flags.length === 0 ? <p data-testid="recon-clean" className="mt-3 text-sm font-semibold text-emerald-700">Gateway and records agree.</p> :
          <ul className="mt-3 divide-y divide-border">{last.flags.map((f, i) => (
            <li key={i} data-testid={`recon-flag-${i}`} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><span className="font-mono text-xs">{f.order_ref}</span><StatusPill status="rejected" label={f.issue.replaceAll("_", " ")} /><span className="text-xs text-muted-foreground">{f.detail}</span></li>))}</ul>}
      </Card>}
    </div>
  );
};

import { useState } from "react";
import { RefreshCw, Repeat, Undo2, FileDown, Receipt } from "lucide-react";
import { toast } from "sonner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { http, errMsg, fmtINR, fmtIST, fetchPdfBlobUrl, downloadUrl } from "@/lib/api";
import { Panel } from "./Panel";
import { StatusBadge, MockedBadge } from "./StatusBadge";
import { RefundDialog } from "./RefundDialog";

const Act = ({ testId, icon: Icon, label, onClick, disabled }) => (
  <Button data-testid={testId} size="sm" variant="ghost" onClick={onClick} disabled={disabled} title={label} className="btn-press h-8 px-2 text-xs">
    <Icon className="mr-1 h-3.5 w-3.5" />{label}
  </Button>
);

export const PaymentsTable = ({ orders, mocked, reload, delay }) => {
  const [refundFor, setRefundFor] = useState(null);

  const run = async (fn, ok) => {
    try { const r = await fn(); ok && toast.success(ok(r)); } catch (e) { toast.error(errMsg(e)); }
    reload();
  };
  const refresh = (o) => run(() => http.get(`/payments/orders/${o.id}`), (r) => `${r.data.order_ref}: ${r.data.status}`);
  const replay = (o) => run(() => http.post(`/poc/payments/${o.id}/replay-callback?times=3`),
    (r) => `3 callbacks → [${r.data.results.join(", ")}] · ${r.data.event_records} event record · ${r.data.orders_for_session} order`);
  const receipt = (o) => run(async () => downloadUrl(await fetchPdfBlobUrl(`/pdf/receipt/${o.id}`), `${o.order_ref}-receipt.pdf`), () => "Receipt downloaded");
  const refunds = orders.flatMap((o) => o.refunds.map((r) => ({ ...r, order_ref: o.order_ref })));

  return (
    <Panel testId="payments-section" eyebrow="Ledger" title="Payment records & refunds" icon={Receipt} delay={delay} className="lg:col-span-12"
      right={<Button data-testid="payments-reload-button" size="sm" variant="outline" onClick={reload} className="btn-press"><RefreshCw className="mr-1.5 h-3.5 w-3.5" />Reload</Button>}>
      <div className="overflow-x-auto">
        <Table data-testid="stripe-payment-records-table">
          <TableHeader>
            <TableRow>
              {["Order", "Candidate", "Amount", "Refunded", "Status", "Verified via", "Created", ""].map((h) => (
                <TableHead key={h} className="font-mono-x text-[11px] uppercase tracking-wider">{h}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {orders.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-10 text-center text-sm text-muted-foreground">No payment orders yet.</TableCell></TableRow>
            )}
            {orders.map((o) => (
              <TableRow key={o.id} data-testid={`payment-row-${o.id}`}>
                <TableCell className="font-mono-x text-xs">{o.order_ref}</TableCell>
                <TableCell className="text-sm">{o.candidate_name}<div className="text-xs text-muted-foreground">{o.candidate_email}</div></TableCell>
                <TableCell className="tabular-nums">{fmtINR(o.amount)}</TableCell>
                <TableCell data-testid={`payment-refunded-${o.id}`} className="tabular-nums">{fmtINR(o.refunded_amount)}<div className="text-xs text-muted-foreground">{o.refund_state}</div></TableCell>
                <TableCell><StatusBadge testId={`stripe-payment-status-badge-${o.id}`} status={o.status} /></TableCell>
                <TableCell className="font-mono-x text-xs text-muted-foreground">{o.verified_via || "—"}</TableCell>
                <TableCell className="font-mono-x text-xs text-muted-foreground">{fmtIST(o.created_at)}</TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  <Act testId={`payment-refresh-${o.id}`} icon={RefreshCw} label="Verify" onClick={() => refresh(o)} />
                  <Act testId={`payment-replay-${o.id}`} icon={Repeat} label="Replay ×3" onClick={() => replay(o)} disabled={!o.provider_session_id} />
                  <Act testId={`stripe-refund-modal-open-button-${o.id}`} icon={Undo2} label="Refund" onClick={() => setRefundFor(o)} disabled={o.status !== "paid" || o.refundable_amount <= 0} />
                  <Act testId={`payment-receipt-${o.id}`} icon={FileDown} label="Receipt" onClick={() => receipt(o)} disabled={o.status !== "paid"} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <RefundHistory refunds={refunds} reload={reload} mocked={mocked} />
      <RefundDialog order={refundFor} mocked={mocked} onClose={() => setRefundFor(null)} onDone={() => { setRefundFor(null); reload(); }} />
    </Panel>
  );
};

const RefundHistory = ({ refunds, reload }) => {
  const retry = async (r) => {
    try { const { data } = await http.post(`/payments/refunds/${r.id}/retry`); toast.success(`${data.refund.refund_ref}: ${data.refund.status}`); }
    catch (e) { toast.error(errMsg(e)); }
    reload();
  };
  if (!refunds.length) return null;
  return (
    <div className="mt-8">
      <p className="font-mono-x mb-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Refund history</p>
      <Table data-testid="stripe-refund-history-table">
        <TableHeader>
          <TableRow>
            {["Refund", "Order", "Amount", "Status", "Provider ref", "Reason", "Created", ""].map((h) => (
              <TableHead key={h} className="font-mono-x text-[11px] uppercase tracking-wider">{h}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {refunds.map((r) => (
            <TableRow key={r.id} data-testid={`refund-row-${r.id}`}>
              <TableCell className="font-mono-x text-xs">{r.refund_ref}</TableCell>
              <TableCell className="font-mono-x text-xs text-muted-foreground">{r.order_ref}</TableCell>
              <TableCell className="tabular-nums">{fmtINR(r.amount)}</TableCell>
              <TableCell className="space-x-1.5"><StatusBadge testId={`refund-status-${r.id}`} status={r.status} />{r.mocked && <MockedBadge testId={`refund-mocked-${r.id}`} />}</TableCell>
              <TableCell className="font-mono-x text-xs text-muted-foreground">{r.provider_refund_id || r.error || "—"}</TableCell>
              <TableCell className="text-xs">{r.reason}</TableCell>
              <TableCell className="font-mono-x text-xs text-muted-foreground">{fmtIST(r.created_at)}</TableCell>
              <TableCell>{r.status === "failed" && <Act testId={`refund-retry-${r.id}`} icon={RefreshCw} label="Retry" onClick={() => retry(r)} />}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};

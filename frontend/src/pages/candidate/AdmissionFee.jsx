import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CreditCard, Download, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { PolicyHelp } from "@/components/portal/PolicyHelp";
import { OfflinePaymentForm } from "@/components/finance/OfflinePaymentForm";

const OrdersTable = ({ orders }) => (
  <Table data-testid="admission-fee-orders">
    <TableHeader><TableRow>{["Reference", "Mode", "Amount", "Status", "Created"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
    <TableBody>
      {orders.map((o) => (
        <TableRow key={o.id} data-testid={`admission-order-${o.id}`}>
          <TableCell className="font-mono text-xs">{o.txn_ref || o.order_ref}</TableCell>
          <TableCell className="text-sm">{o.origin === "offline" ? o.offline_mode?.toUpperCase() : "Online (Stripe test)"}</TableCell>
          <TableCell className="tabular-nums">{fmtINR(o.amount)}</TableCell>
          <TableCell><StatusPill status={o.status} />{o.failure_reason && <p className="mt-1 text-xs text-red-700">{o.failure_reason}</p>}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{fmtIST(o.created_at)}</TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
);

export default function AdmissionFeePage({ outcome }) {
  const [params] = useSearchParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [polls, setPolls] = useState(0);
  const load = useCallback(() => http.get("/candidate/admission-fee").then((r) => setD(r.data)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (outcome !== "success" || !d || d.paid || polls > 15) return;
    const t = setTimeout(() => { setPolls((n) => n + 1); load(); }, 2000);
    return () => clearTimeout(t);
  }, [outcome, d, polls, load]);
  const pay = async () => {
    setBusy(true);
    try { const { data } = await http.post("/candidate/admission-fee/checkout", { origin_url: window.location.origin }); window.location.href = data.checkout_url; }
    catch (e) { toast.error(errMsg(e)); setBusy(false); }
  };
  const receipt = async () => { try { await downloadFile("/candidate/admission-fee/receipt", "admission-fee-receipt.pdf"); toast.success("Receipt downloaded"); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  const pendingOffline = d.orders.some((o) => o.status === "awaiting_verification");
  return (
    <div data-testid="admission-fee-page">
      <PageHeader eyebrow="Part B · Payments" title="Admission fee" description="Pay online, or submit your bank transfer reference for Accounts to verify. A redirect alone never marks the fee as paid." />
      <div className="mb-6"><PolicyHelp topic="fee" /></div>
      {outcome === "cancel" && <p data-testid="admission-fee-cancelled" className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Checkout was cancelled. You can try again.</p>}
      {params.get("order_id") && outcome === "success" && !d.paid && polls <= 15 && <p data-testid="admission-fee-verifying" className="mb-6 flex items-center gap-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"><Loader2 className="h-4 w-4 animate-spin" />Verifying your payment with the gateway…</p>}
      {!d.eligible && !d.paid ? <Card testId="admission-fee-not-eligible"><p className="text-sm text-muted-foreground">The admission fee becomes payable once you hold an allotted or provisional seat.</p></Card> : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
          <Card testId="admission-fee-status">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">{d.program_code || "Admission"}</p>
            <p data-testid="admission-fee-amount" className="mt-2 font-['Outfit'] text-4xl font-bold tabular-nums">{fmtINR(d.amount)}</p>
            {d.paid ? <>
              <p data-testid="admission-fee-paid" className="mt-4 flex items-center gap-2 text-sm font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" />Paid and verified</p>
              <Button className="mt-4" data-testid="admission-fee-receipt-button" onClick={receipt}><Download className="mr-1.5 h-4 w-4" />Payment receipt</Button>
            </> : pendingOffline ? <p data-testid="admission-fee-offline-pending" className="mt-4 text-sm text-amber-800">Your offline payment is awaiting verification by Accounts.</p>
              : <Button className="mt-6 min-h-11 w-full" data-testid="admission-fee-pay-button" onClick={pay} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><CreditCard className="mr-1.5 h-4 w-4" />Pay online (test card)</>}</Button>}
          </Card>
          {!d.paid && !pendingOffline && <Card testId="admission-fee-offline-card">
            <p className="mb-3 font-semibold">Paid by bank transfer or DD?</p>
            <OfflinePaymentForm prefix="candidate" modes={d.offline_modes} endpoint="/candidate/admission-fee/offline" onDone={load} />
          </Card>}
        </div>
      )}
      {d.orders.length > 0 && <Card className="mt-6 overflow-x-auto p-0"><OrdersTable orders={d.orders} /></Card>}
    </div>
  );
}

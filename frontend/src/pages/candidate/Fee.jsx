import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CreditCard, Download, Loader2, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { PolicyHelp } from "@/components/portal/PolicyHelp";

export default function FeePage({ outcome }) {
  const [params] = useSearchParams();
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(false);
  const [polls, setPolls] = useState(0);
  const load = useCallback(() => http.get("/candidate/application/fee").then((r) => { setD(r.data); return r.data; }), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (outcome !== "success" || !d || d.paid || polls > 15) return;
    const t = setTimeout(() => { setPolls((n) => n + 1); load(); }, 2000);
    return () => clearTimeout(t);
  }, [outcome, d, polls, load]);

  const pay = async () => {
    setBusy(true);
    try { const { data } = await http.post("/candidate/application/fee/checkout", { origin_url: window.location.origin }); window.location.href = data.checkout_url; }
    catch (e) { toast.error(errMsg(e)); setBusy(false); }
  };
  const invoice = async () => {
    try { await downloadFile("/candidate/application/fee/receipt", "weschool-application-fee-invoice.pdf"); toast.success("Invoice downloaded"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (!d) return null;
  const verifying = outcome === "success" && !d.paid && polls <= 15;
  return (
    <div data-testid="fee-page">
      <PageHeader eyebrow="Payments" title="Application fee & invoice" description="Payment status is confirmed with the gateway on the server; a redirect alone never marks a fee as paid." />
      {outcome === "cancel" && <p data-testid="fee-cancelled-notice" className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Checkout was cancelled. You can try again any time.</p>}
      {params.get("order_id") && verifying && <p data-testid="fee-verifying-notice" className="mb-6 flex items-center gap-2 rounded-md border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900"><Loader2 className="h-4 w-4 animate-spin" />Verifying your payment with the gateway…</p>}
      <div className="mb-6"><PolicyHelp topic="fee" /></div>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        <Card testId="fee-status-card">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Application fee</p>
          <p data-testid="fee-amount" className="mt-2 font-['Outfit'] text-4xl font-bold">{fmtINR(d.amount)}</p>
          <div className="mt-4">{d.paid
            ? <p data-testid="fee-paid-status" className="flex items-center gap-2 font-semibold text-emerald-700"><CheckCircle2 className="h-5 w-5" />Paid</p>
            : <StatusPill testId="fee-unpaid-status" status="draft" />}</div>
          <div className="mt-6 flex flex-wrap gap-3">
            {!d.paid && <Button data-testid="fee-pay-button" onClick={pay} disabled={busy || !d.window_open} className="min-h-11 w-full rounded-full px-6 sm:w-auto">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><CreditCard className="mr-2 h-4 w-4" />Pay {fmtINR(d.amount)}</>}</Button>}
            {d.paid && <Button data-testid="fee-invoice-button" variant="outline" onClick={invoice} className="min-h-11 w-full sm:w-auto"><Download className="mr-2 h-4 w-4" />Download invoice</Button>}
          </div>
          {!d.window_open && !d.paid && <p className="mt-3 text-sm text-destructive">The application window is closed.</p>}
          <p className="mt-6 text-xs text-muted-foreground">Stripe test mode · card 4242 4242 4242 4242 · any future expiry · any CVC.</p>
        </Card>
        <Card className="overflow-x-auto p-0">
          <Table data-testid="fee-orders-table">
            <TableHeader><TableRow>{["Order", "Amount", "Status", "Created", "Paid at"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {d.orders.length === 0 && <TableRow><TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">No payments yet.</TableCell></TableRow>}
              {d.orders.map((o) => (
                <TableRow key={o.id}><TableCell className="font-mono text-xs">{o.order_ref}</TableCell><TableCell>{fmtINR(o.amount)}</TableCell>
                  <TableCell><StatusPill status={o.status === "paid" ? "success" : o.status} /></TableCell>
                  <TableCell className="text-xs">{fmtIST(o.created_at)}</TableCell><TableCell className="text-xs">{fmtIST(o.paid_at)}</TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}

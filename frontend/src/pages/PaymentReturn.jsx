import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, ArrowLeft, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { http, errMsg, fmtINR, fmtIST, fetchPdfBlobUrl, downloadUrl } from "@/lib/api";
import { StatusBadge } from "@/components/console/StatusBadge";

const MAX_POLLS = 20;

export default function PaymentReturn({ outcome }) {
  const [params] = useSearchParams();
  const orderId = params.get("order_id");
  const [order, setOrder] = useState(null);
  const [polls, setPolls] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!orderId) return;
    let stop = false;
    const poll = async (n) => {
      try {
        const { data } = await http.get(`/payments/orders/${orderId}`);
        if (stop) return;
        setOrder(data); setPolls(n);
        if (outcome === "success" && ["created", "pending"].includes(data.status) && n < MAX_POLLS) setTimeout(() => poll(n + 1), 2000);
      } catch (e) { setError(errMsg(e)); }
    };
    poll(1);
    return () => { stop = true; };
  }, [orderId, outcome]);

  const paid = order?.status === "paid";
  const waiting = outcome === "success" && order && !paid && polls < MAX_POLLS && ["created", "pending"].includes(order.status);
  const receipt = async () => downloadUrl(await fetchPdfBlobUrl(`/pdf/receipt/${order.id}`), `${order.order_ref}-receipt.pdf`);

  return (
    <main data-testid="payment-return-page" className="dark grid-lines relative z-10 flex min-h-screen items-start bg-background px-4 py-16 text-foreground sm:px-12 lg:px-24">
      <div className="panel rise w-full max-w-xl p-8">
        <p className="font-mono-x text-[11px] uppercase tracking-[0.2em] text-primary">Payment {outcome === "success" ? "return" : "cancelled"}</p>
        <div className="mt-4 flex items-center gap-3">
          {paid ? <CheckCircle2 className="h-8 w-8 text-emerald-400" /> : waiting || !order ? <Loader2 className="h-8 w-8 animate-spin text-amber-400" /> : <XCircle className="h-8 w-8 text-red-400" />}
          <h1 data-testid="payment-return-title" className="text-3xl font-bold tracking-tight">
            {paid ? "Payment verified" : waiting || !order ? "Verifying with gateway…" : outcome === "cancel" ? "Checkout cancelled" : "Payment not confirmed"}
          </h1>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Status is confirmed server-side with Stripe. The redirect alone never marks an order as paid.
        </p>
        {error && <p data-testid="payment-return-error" className="mt-4 text-sm text-red-400">{error}</p>}
        {order && (
          <dl className="mt-6 divide-y divide-border text-sm">
            {[["Order", order.order_ref], ["Amount", fmtINR(order.amount)], ["Verified via", order.verified_via || "—"], ["Paid at", fmtIST(order.paid_at)]].map(([k, v]) => (
              <div key={k} className="flex justify-between py-2.5"><dt className="text-muted-foreground">{k}</dt><dd className="font-mono-x text-xs">{v}</dd></div>
            ))}
            <div className="flex justify-between py-2.5"><dt className="text-muted-foreground">Status</dt><dd><StatusBadge testId="payment-return-status-badge" status={order.status} /></dd></div>
          </dl>
        )}
        <div className="mt-8 flex gap-3">
          <Button asChild variant="outline" className="btn-press"><Link data-testid="payment-return-back-link" to="/"><ArrowLeft className="mr-1.5 h-4 w-4" />Back to console</Link></Button>
          {paid && <Button data-testid="payment-return-receipt-button" onClick={receipt} className="btn-press"><Download className="mr-1.5 h-4 w-4" />Receipt PDF</Button>}
        </div>
      </div>
    </main>
  );
}

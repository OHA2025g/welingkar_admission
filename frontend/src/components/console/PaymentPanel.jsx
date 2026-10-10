import { useRef, useState } from "react";
import { CreditCard, Loader2, ArrowUpRight } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { http, errMsg, fmtINR, newKey } from "@/lib/api";
import { Panel, Field } from "./Panel";
import { MockedBadge } from "./StatusBadge";

export const PaymentPanel = ({ config, application, delay }) => {
  const fee = config?.fees?.[0];
  const [name, setName] = useState("Aarav Mehta");
  const [email, setEmail] = useState("aarav.mehta@example.com");
  const [busy, setBusy] = useState(false);
  const keyRef = useRef(null);

  const pay = async () => {
    setBusy(true);
    keyRef.current = keyRef.current || newKey("order");
    try {
      const { data } = await http.post("/payments/orders", {
        fee_code: fee.code, candidate_name: name, candidate_email: email,
        application_ref: application?.application_ref, origin_url: window.location.origin,
        idempotency_key: keyRef.current,
      });
      toast.success(`Order ${data.order_ref} created. Redirecting to Stripe…`);
      window.location.href = data.checkout_url;
    } catch (e) {
      toast.error(errMsg(e));
      setBusy(false);
    }
  };

  return (
    <Panel testId="stripe-payment-panel" eyebrow="Gateway · Stripe test mode" title="Application fee checkout" icon={CreditCard} delay={delay}
      right={<span className="font-mono-x text-[11px] uppercase tracking-wider text-muted-foreground">{config?.key_type?.replaceAll("_", " ")}</span>}>
      <div className="grid gap-6 md:grid-cols-[1fr_auto]">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Candidate name">
            <Input data-testid="stripe-applicant-name-input" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Candidate email">
            <Input data-testid="stripe-applicant-email-input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Application" hint="Fee amount is fixed server-side; the client never sends amounts.">
            <Input data-testid="stripe-application-ref-input" value={application?.application_ref || ""} readOnly className="font-mono-x" />
          </Field>
          <Field label="Refund mode" hint="The shared test key has no refund API; refunds run through the adapter state machine.">
            <div className="flex h-9 items-center gap-2">
              {config?.refunds_mocked ? <MockedBadge testId="stripe-refund-mode-mocked-badge" /> : <span className="text-sm">Live provider</span>}
            </div>
          </Field>
        </div>
        <div className="flex flex-col justify-between gap-4 rounded-sm border border-border bg-background/60 p-5 md:min-w-[220px]">
          <div>
            <p className="font-mono-x text-[11px] uppercase tracking-wider text-muted-foreground">{fee?.description || "—"}</p>
            <p data-testid="stripe-fee-amount" className="mt-2 text-3xl font-semibold tabular-nums">{fmtINR(fee?.amount)}</p>
            <p className="font-mono-x mt-1 text-[11px] text-muted-foreground">INR · card 4242 4242 4242 4242</p>
          </div>
          <Button data-testid="stripe-checkout-pay-button" onClick={pay} disabled={!fee || busy || !name || !email} className="btn-press h-11 rounded-full">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Pay {fmtINR(fee?.amount)} <ArrowUpRight className="ml-1 h-4 w-4" /></>}
          </Button>
        </div>
      </div>
    </Panel>
  );
};

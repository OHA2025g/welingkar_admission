import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { http, errMsg, fmtINR, newKey } from "@/lib/api";
import { Field } from "./Panel";
import { MockedBadge } from "./StatusBadge";
import { StepUpOtp, stepUpReady } from "@/components/finance/StepUpOtp";

export const RefundDialog = ({ order, mocked, onClose, onDone }) => {
  const [type, setType] = useState("full");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("Candidate withdrew application");
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [otp, setOtp] = useState(null);

  useEffect(() => {
    if (order) { setType("full"); setAmount(""); setKey(newKey("refund")); setOtp(null); setWaiting(false); }
  }, [order]);

  const max = order?.refundable_amount || 0;
  const amt = type === "full" ? max : Number(amount);
  const invalid = !amt || amt <= 0 || amt > max || reason.trim().length < 3 || !stepUpReady(otp);

  const submit = async () => {
    setBusy(true);
    try {
      const body = { reason, idempotency_key: key, ...otp, ...(type === "partial" ? { amount: amt } : {}) };
      const { data } = await http.post(`/payments/orders/${order.id}/refunds`, body);
      const r = data.refund;
      if (r.status === "failed") toast.error(`Refund ${r.refund_ref} failed: ${r.error}`);
      else toast.success(`Refund ${r.refund_ref} ${r.status}${r.mocked ? " (MOCKED)" : ""}${data.idempotent_replay ? " · replay" : ""}`);
      onDone();
    } catch (e) {
      if (e?.response?.data?.detail?.code === "signoff_required") {
        setWaiting(true);
        toast.warning("Waiting for Super Admin sign-off before this refund can be paid out.");
      } else toast.error(errMsg(e));
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={!!order} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="stripe-refund-dialog" className="border-border bg-card">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">Refund {order?.order_ref} {mocked && <MockedBadge testId="refund-dialog-mocked-badge" />}</DialogTitle>
          <DialogDescription>
            Refundable balance <span className="font-semibold text-foreground">{fmtINR(max)}</span>. Cumulative refunds can never exceed the verified paid amount.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <Field label="Refund type">
            <Select value={type} onValueChange={setType}>
              <SelectTrigger data-testid="stripe-refund-type-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem data-testid="refund-type-full" value="full">Full remaining ({fmtINR(max)})</SelectItem>
                <SelectItem data-testid="refund-type-partial" value="partial">Partial amount</SelectItem>
              </SelectContent>
            </Select>
          </Field>
          {type === "partial" && (
            <Field label="Amount (INR)">
              <Input data-testid="stripe-refund-amount-input" type="number" min="1" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="500" />
            </Field>
          )}
          <Field label="Reason">
            <Input data-testid="stripe-refund-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <StepUpOtp value={otp} onChange={setOtp} />
          {waiting && <p data-testid="refund-signoff-waiting" className="text-sm text-amber-800">Waiting for Super Admin sign-off before this refund can be paid out.</p>}
          <p className="font-mono-x text-[11px] text-muted-foreground">Idempotency key: {key}</p>
          <Button data-testid="stripe-refund-submit-button" onClick={submit} disabled={invalid || busy} variant="destructive" className="btn-press w-full">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : `Refund ${fmtINR(amt)}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

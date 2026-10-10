import { useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { http, errMsg } from "@/lib/api";

// Step-up OTP: a real email code to the signed-in Accounts Operator; required for every refund.
export const StepUpOtp = ({ value, onChange }) => {
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);
  const send = async () => {
    setBusy(true);
    try {
      const { data } = await http.post("/accounts/step-up/send");
      setSent(data);
      onChange({ otp_challenge_id: data.id || data.challenge_id, otp_code: "" });
      toast.success(`Code emailed to ${data.masked_destination}`);
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div data-testid="step-up-otp" className="rounded-md border border-amber-200 bg-amber-50/60 p-4">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900"><ShieldCheck className="h-4 w-4" />Step-up verification</p>
      <p className="mt-1 text-xs text-amber-900/80">Refunds need a fresh one-time code sent to your staff email. Each code authorises one refund.</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" data-testid="step-up-send-button" onClick={send} disabled={busy}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : sent ? "Resend code" : "Email me a code"}
        </Button>
        {sent && <Input data-testid="step-up-code-input" inputMode="numeric" maxLength={6} placeholder="6-digit code" className="w-36 font-mono tracking-widest"
          value={value?.otp_code || ""} onChange={(e) => onChange({ ...value, otp_code: e.target.value.replace(/\D/g, "") })} />}
      </div>
      {sent && <p data-testid="step-up-sent-to" className="mt-2 text-xs text-muted-foreground">Sent to {sent.masked_destination}{sent.debug_code ? ` · test inbox code ${sent.debug_code}` : ""}</p>}
    </div>
  );
};

export const stepUpReady = (v) => !!v?.otp_challenge_id && /^\d{6}$/.test(v?.otp_code || "");

import { useState } from "react";
import { Mail, MessageCircle, Loader2, ShieldCheck, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { http, errMsg, mmss, secondsUntil, useNow } from "@/lib/api";
import { Panel, Field } from "./Panel";
import { StatusBadge, MockedBadge } from "./StatusBadge";

const CFG = {
  email: { icon: Mail, title: "Email OTP · Resend", eyebrow: "Channel 01", placeholder: "candidate@example.com", hint: "Use delivered@resend.dev to get the code echoed (test sink only)." },
  whatsapp: { icon: MessageCircle, title: "WhatsApp OTP · Twilio", eyebrow: "Channel 02", placeholder: "+919876543210", hint: "E.164 format. Recipient must have joined the Twilio sandbox." },
};

export const OtpPanel = ({ channel, health, onActivity, delay }) => {
  const c = CFG[channel];
  const now = useNow();
  const [dest, setDest] = useState("");
  const [code, setCode] = useState("");
  const [ch, setCh] = useState(null);
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState(null);
  const unconfigured = channel === "whatsapp" && health && !health.whatsapp?.configured;
  const expiresIn = secondsUntil(ch?.expires_at, now);
  const cooldown = secondsUntil(ch?.resend_available_at, now);
  const t = (s) => `${channel}-otp-${s}`;

  const send = async () => {
    setBusy("send"); setNotice(null);
    try {
      const { data } = await http.post("/otp/send", { channel, destination: dest, purpose: "registration" });
      setCh(data); setCode("");
      toast.success(`OTP sent to ${data.masked_destination}`);
    } catch (e) {
      setNotice({ tone: "error", text: errMsg(e) });
      toast.error(errMsg(e));
    } finally { setBusy(null); onActivity?.(); }
  };

  const verify = async () => {
    setBusy("verify"); setNotice(null);
    try {
      const { data } = await http.post("/otp/verify", { challenge_id: ch.id, code });
      setCh(data.challenge);
      setNotice({ tone: "success", text: "Channel verified. Code consumed and cannot be reused." });
      toast.success(`${channel} verified`);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (d?.attempts_left !== undefined) setCh((p) => ({ ...p, attempts_left: d.attempts_left }));
      if (["locked", "expired", "superseded"].includes(d?.code)) setCh((p) => ({ ...p, status: d.code, attempts_left: d.code === "locked" ? 0 : p.attempts_left }));
      setNotice({ tone: "error", text: errMsg(e) });
    } finally { setBusy(null); onActivity?.(); }
  };

  const refresh = async () => {
    const { data } = await http.get(`/otp/challenges/${ch.id}`);
    setCh(data);
  };

  return (
    <Panel testId={`${channel}-otp-panel`} eyebrow={c.eyebrow} title={c.title} icon={c.icon} delay={delay}
      right={ch && <StatusBadge testId={t("status-badge")} status={ch.status} />}>
      {channel === "whatsapp" && health?.whatsapp?.mocked && (
        <div data-testid="whatsapp-mocked-alert-banner" className="mb-4 flex items-start gap-2 rounded-sm border border-amber-400/40 bg-amber-400/10 p-3 text-sm text-amber-200">
          <MockedBadge testId="whatsapp-mode-mocked-badge" />
          <span>No approved template (TWILIO_WHATSAPP_CONTENT_SID). Codes are generated and verified for real but not sent; the code is shown here.</span>
        </div>
      )}
      {unconfigured && (
        <div data-testid="whatsapp-unconfigured-alert-banner" className="mb-4 flex gap-2 rounded-sm border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> Not configured. Missing: {health.whatsapp.missing.join(", ")}
        </div>
      )}
      <div className="space-y-4">
        <Field label="Recipient" hint={c.hint}>
          <div className="flex gap-2">
            <Input data-testid={t("recipient-input")} value={dest} onChange={(e) => setDest(e.target.value)} placeholder={c.placeholder} className="font-mono-x" />
            <Button data-testid={ch ? t("resend-button") : t("send-button")} onClick={send} disabled={!dest || busy || cooldown > 0} className="btn-press min-w-[112px]">
              {busy === "send" ? <Loader2 className="h-4 w-4 animate-spin" /> : cooldown > 0 ? <span data-testid={t("cooldown-timer")} className="font-mono-x">{mmss(cooldown)}</span> : ch ? "Resend" : "Send OTP"}
            </Button>
          </div>
        </Field>
        {ch && (
          <div className="rise space-y-4 border-t border-border pt-4">
            <div className="font-mono-x grid grid-cols-3 gap-3 text-xs">
              <Stat label="Expires in" value={ch.status === "pending" ? mmss(expiresIn) : "—"} testId={t("expiry-countdown")} />
              <Stat label="Attempts left" value={`${ch.attempts_left}/${ch.max_attempts}`} testId={t("attempts-left-badge")} />
              <Stat label="Delivery" value={ch.delivery_status} testId={t("delivery-status")} onClick={channel === "whatsapp" ? refresh : undefined} />
            </div>
            {ch.debug_code && (
              <p data-testid={t("debug-code")} className="font-mono-x flex items-center gap-2 text-xs text-[hsl(var(--gold))]">
                {ch.mocked ? <><MockedBadge testId={t("mocked-badge")} /> Not delivered. Dev code:</> : "Test-sink code:"} {ch.debug_code}
              </p>
            )}
            <div className="flex gap-2">
              <Input data-testid={t("code-input")} value={code} inputMode="numeric" maxLength={6}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="••••••"
                className="font-mono-x text-center text-lg tracking-[0.6em]" />
              <Button data-testid={t("verify-button")} onClick={verify} variant="secondary" disabled={code.length !== 6 || busy || ch.status !== "pending"} className="btn-press min-w-[112px]">
                {busy === "verify" ? <Loader2 className="h-4 w-4 animate-spin" /> : <><ShieldCheck className="mr-1.5 h-4 w-4" />Verify</>}
              </Button>
            </div>
          </div>
        )}
        {notice && (
          <p data-testid={t("result-message")} className={`text-sm ${notice.tone === "success" ? "text-emerald-400" : "text-red-400"}`}>{notice.text}</p>
        )}
      </div>
    </Panel>
  );
};

const Stat = ({ label, value, testId, onClick }) => (
  <div className="rounded-sm border border-border bg-background/50 p-2.5">
    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
    <p data-testid={testId} onClick={onClick} className={`mt-1 text-sm text-foreground ${onClick ? "cursor-pointer underline decoration-dotted" : ""}`}>{value}</p>
  </div>
);

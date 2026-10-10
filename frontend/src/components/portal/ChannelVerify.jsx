import { useState } from "react";
import { Mail, MessageCircle, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { http, errMsg, mmss, secondsUntil, useNow } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const META = {
  email: { icon: Mail, title: "Email", dest: (u) => u.email },
  whatsapp: { icon: MessageCircle, title: "WhatsApp", dest: (u) => u.mobile },
};

export const ChannelVerify = ({ channel, initial }) => {
  const { user, setUser } = useAuth();
  const m = META[channel];
  const now = useNow();
  const [ch, setCh] = useState(initial?.id ? initial : null);
  const [error, setError] = useState(initial?.error?.message || "");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(null);
  const done = !!user[channel === "email" ? "email_verified_at" : "whatsapp_verified_at"];
  const cooldown = secondsUntil(ch?.resend_available_at, now);
  const expires = secondsUntil(ch?.expires_at, now);
  const t = (s) => `verify-${channel}-${s}`;

  const send = async () => {
    setBusy("send"); setError("");
    try { const { data } = await http.post("/auth/candidate/verification/send", { channel }); setCh(data); setCode(""); toast.success(`Code sent to ${data.masked_destination}`); }
    catch (e) { setError(errMsg(e)); } finally { setBusy(null); }
  };
  const verify = async (e) => {
    e.preventDefault(); setBusy("verify"); setError("");
    try {
      const { data } = await http.post("/auth/candidate/verification/verify", { channel, challenge_id: ch.id, code });
      setUser(data.user); toast.success(`${m.title} verified`);
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d?.attempts_left !== undefined) setCh((p) => ({ ...p, attempts_left: d.attempts_left }));
      setError(errMsg(err));
    } finally { setBusy(null); }
  };

  return (
    <div data-testid={t("card")} className={`rounded-md border p-5 ${done ? "border-emerald-200 bg-emerald-50/50" : "border-border bg-card"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-secondary"><m.icon className="h-4 w-4 text-primary" /></span>
          <div>
            <p className="font-semibold">{m.title}</p>
            <p className="text-xs text-muted-foreground">{m.dest(user)}</p>
          </div>
        </div>
        {done ? <span data-testid={t("status")} className="flex items-center gap-1 text-sm font-medium text-emerald-700"><CheckCircle2 className="h-4 w-4" />Verified</span>
          : ch?.mocked ? <span data-testid={t("mocked-badge")} className="rounded-sm border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider text-amber-800">Mocked</span>
            : <span data-testid={t("status")} className="text-xs text-muted-foreground">Pending</span>}
      </div>
      {!done && (
        <form onSubmit={verify} className="mt-4 space-y-3">
          {ch && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
              <span data-testid={t("expiry")}>Expires in <b className="font-mono text-foreground">{mmss(expires)}</b></span>
              <span data-testid={t("attempts")}>Attempts left <b className="text-foreground">{ch.attempts_left}/{ch.max_attempts}</b></span>
            </div>
          )}
          {ch?.debug_code && (
            <p data-testid={t("debug-code")} className="rounded-sm bg-amber-50 px-2 py-1 font-mono text-xs text-amber-800">
              {ch.mocked ? "WhatsApp delivery is MOCKED. Dev code:" : "Test inbox code:"} {ch.debug_code}
            </p>
          )}
          <div className="flex gap-2">
            <Input data-testid={t("code-input")} aria-label={`${m.title} code`} inputMode="numeric" maxLength={6} disabled={!ch} value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} placeholder="6-digit code" className="font-mono tracking-[0.3em]" />
            <Button data-testid={t("submit-button")} type="submit" disabled={!ch || code.length !== 6 || busy}>{busy === "verify" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Verify"}</Button>
          </div>
          <Button data-testid={t("send-button")} type="button" variant="link" className="h-auto p-0 text-xs" onClick={send} disabled={cooldown > 0 || !!busy}>
            {cooldown > 0 ? `Resend in ${mmss(cooldown)}` : ch ? "Resend code" : "Send code"}
          </Button>
          {error && <p data-testid={t("error")} role="alert" className="text-sm text-destructive">{error}</p>}
        </form>
      )}
    </div>
  );
};

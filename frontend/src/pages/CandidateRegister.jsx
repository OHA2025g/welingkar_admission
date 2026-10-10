import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { http, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { INDIAN_STATES } from "@/lib/menu";
import { AuthLayout } from "@/components/portal/AuthLayout";
import { ChannelVerify } from "@/components/portal/ChannelVerify";

const F = ({ id, label, children }) => (
  <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>
);

export default function CandidateRegister() {
  const { user, signIn } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", mobile: "", state: "", city: "", password: "" });
  const [challenges, setChallenges] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const { data } = await http.post("/auth/candidate/register", f);
      signIn(data); setChallenges(data.challenges);
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  const verified = user?.identity_status === "verified";
  return (
    <AuthLayout testId="candidate-register-page" eyebrow={challenges ? "Step 2 of 2 · Verify" : "Step 1 of 2 · Register"}
      title={challenges ? "Verify your email and WhatsApp" : "Create your applicant account"}
      subtitle={challenges ? "Both channels must be verified before you can pay the application fee." : "Use details you can access. We verify both email and WhatsApp."}
      aside={<><h2 className="text-3xl font-bold leading-tight">Admissions 2026-28</h2><p className="mt-3 text-white/80">PGDM · Business Design · Research & Business Analytics · E-Business · Healthcare · Media & Entertainment · MMS</p></>}>
      {!challenges ? (
        <form onSubmit={submit} className="space-y-4">
          <F id="r-name" label="Full name (as on marksheets)"><Input id="r-name" data-testid="register-name-input" value={f.name} onChange={set("name")} required autoComplete="name" /></F>
          <div className="grid gap-4 sm:grid-cols-2">
            <F id="r-email" label="Email"><Input id="r-email" data-testid="register-email-input" type="email" value={f.email} onChange={set("email")} required autoComplete="email" /></F>
            <F id="r-mobile" label="Mobile (WhatsApp)"><Input id="r-mobile" data-testid="register-mobile-input" value={f.mobile} onChange={set("mobile")} placeholder="9876543210" required autoComplete="tel" /></F>
            <F id="r-state" label="State">
              <Select value={f.state} onValueChange={(v) => setF({ ...f, state: v })}>
                <SelectTrigger id="r-state" data-testid="register-state-select"><SelectValue placeholder="Select state" /></SelectTrigger>
                <SelectContent>{INDIAN_STATES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </F>
            <F id="r-city" label="City"><Input id="r-city" data-testid="register-city-input" value={f.city} onChange={set("city")} required /></F>
          </div>
          <F id="r-pw" label="Password"><Input id="r-pw" data-testid="register-password-input" type="password" value={f.password} onChange={set("password")} required autoComplete="new-password" />
            <p className="text-xs text-muted-foreground">At least 8 characters with letters and numbers.</p></F>
          {error && <p data-testid="register-error" role="alert" className="text-sm text-destructive">{error}</p>}
          <Button data-testid="register-submit-button" type="submit" className="h-11 w-full" disabled={busy || Object.values(f).some((v) => !v)}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create account & send codes"}
          </Button>
          <p className="text-sm text-muted-foreground">Already registered? <Link className="font-semibold text-primary hover:underline" to="/candidate/login">Sign in</Link></p>
        </form>
      ) : (
        <div className="space-y-4">
          <ChannelVerify channel="email" initial={challenges.email} />
          <ChannelVerify channel="whatsapp" initial={challenges.whatsapp} />
          <Button data-testid="register-continue-button" className="h-11 w-full" disabled={!verified} onClick={() => nav("/candidate/dashboard")}>
            {verified ? <>Continue to dashboard <ArrowRight className="ml-2 h-4 w-4" /></> : "Verify both channels to continue"}
          </Button>
        </div>
      )}
    </AuthLayout>
  );
}

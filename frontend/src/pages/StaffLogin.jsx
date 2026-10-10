import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { http, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AuthLayout } from "@/components/portal/AuthLayout";

export const SessionNotice = () => {
  const { ended } = useAuth();
  return ended ? <p data-testid="session-ended-notice" role="status" className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{ended}</p> : null;
};

export default function StaffLogin() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [step, setStep] = useState(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const finish = (data) => {
    const u = signIn(data);
    nav(loc.state?.from || u.home, { replace: true });
  };
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const { data } = await http.post("/auth/staff/login", { email, password });
      if (data.step_up_required) setStep(data);
      else finish(data);
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };
  const confirm = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const { data } = await http.post("/auth/staff/login/complete", { challenge_id: step.challenge_id, code });
      finish(data);
    } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };

  return (
    <AuthLayout testId="staff-login-page" eyebrow="Staff console" title="Sign in to WeSchool Admissions"
      subtitle="For admissions, assessment, accounts and audit staff. Candidates sign in on the candidate portal."
      aside={<><h2 className="text-3xl font-bold leading-tight">Every action, attributed.</h2><p className="mt-3 text-white/80">Access is role-scoped and every privileged change is recorded in the audit log. Sessions end after 15 minutes of inactivity.</p></>}>
      <SessionNotice />
      {step ? (
        <form onSubmit={confirm} className="space-y-5" noValidate>
          <p data-testid="staff-step-up-notice" className="text-sm text-muted-foreground">Enter the email code sent to {step.masked_destination}. Super Admin, Accounts, and Admissions sign in with this extra code.</p>
          {step.debug_code && <p data-testid="staff-step-up-debug-code" className="font-mono text-xs text-amber-700">Test inbox code: {step.debug_code}</p>}
          <div className="space-y-1.5"><Label htmlFor="sl-code">Email code</Label>
            <Input id="sl-code" data-testid="staff-step-up-code" inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required /></div>
          {error && <p data-testid="staff-login-error" role="alert" className="text-sm text-destructive">{error}</p>}
          <Button data-testid="staff-step-up-submit" type="submit" className="h-11 w-full" disabled={busy || code.length < 6}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Confirm and sign in"}
          </Button>
        </form>
      ) : (
      <form onSubmit={submit} className="space-y-5" noValidate>
        <div className="space-y-1.5"><Label htmlFor="sl-email">Work email</Label>
          <Input id="sl-email" data-testid="staff-login-email-input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
        <div className="space-y-1.5"><Label htmlFor="sl-pw">Password</Label>
          <Input id="sl-pw" data-testid="staff-login-password-input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
        {error && <p data-testid="staff-login-error" role="alert" className="text-sm text-destructive">{error}</p>}
        <Button data-testid="staff-login-submit-button" type="submit" className="h-11 w-full" disabled={busy || !email || !password}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
        </Button>
      </form>
      )}
      <p className="mt-8 text-sm text-muted-foreground">Applying to WeSchool? <Link className="font-semibold text-primary hover:underline" to="/candidate/login">Candidate portal</Link></p>
      <p className="mt-3 text-xs text-muted-foreground">Super Admin? <Link data-testid="staff-login-download-link" className="font-medium text-primary hover:underline" to="/staff/download">Download the portal to run locally</Link></p>
    </AuthLayout>
  );
}

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { http, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AuthLayout } from "@/components/portal/AuthLayout";
import { SessionNotice } from "./StaffLogin";

const PasswordForm = ({ onDone }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try { onDone((await http.post("/auth/candidate/login", { email, password })).data); }
    catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="space-y-1.5"><Label htmlFor="cl-email">Email</Label>
        <Input id="cl-email" data-testid="candidate-login-email-input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
      <div className="space-y-1.5">
        <div className="flex justify-between"><Label htmlFor="cl-pw">Password</Label>
          <Link data-testid="forgot-password-link" to="/candidate/forgot-password" className="text-xs font-medium text-primary hover:underline">Forgot password?</Link></div>
        <Input id="cl-pw" data-testid="candidate-login-password-input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></div>
      {error && <p data-testid="candidate-login-error" role="alert" className="text-sm text-destructive">{error}</p>}
      <Button data-testid="candidate-login-submit-button" type="submit" className="h-11 w-full" disabled={busy || !email || !password}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Sign in"}
      </Button>
    </form>
  );
};

export const EmailOtpForm = ({ startPath, prefix, onCode, submitLabel, extra }) => {
  const [email, setEmail] = useState("");
  const [ch, setCh] = useState(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const start = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try { const { data } = await http.post(startPath, { email }); setCh(data); toast.success(`If an account exists, a code was sent to ${data.masked_destination}`); }
    catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };
  const finish = async (e) => {
    e.preventDefault(); setBusy(true); setError("");
    try { await onCode(ch.id, code); } catch (err) { setError(errMsg(err)); } finally { setBusy(false); }
  };
  if (!ch) return (
    <form onSubmit={start} className="space-y-5">
      <div className="space-y-1.5"><Label htmlFor={`${prefix}-email`}>Registered email</Label>
        <Input id={`${prefix}-email`} data-testid={`${prefix}-email-input`} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></div>
      {error && <p role="alert" data-testid={`${prefix}-error`} className="text-sm text-destructive">{error}</p>}
      <Button data-testid={`${prefix}-send-button`} type="submit" className="h-11 w-full" disabled={busy || !email}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Email me a code"}</Button>
    </form>
  );
  return (
    <form onSubmit={finish} className="space-y-5">
      <p className="text-sm text-muted-foreground">Enter the 6-digit code sent to <span className="font-medium text-foreground">{ch.masked_destination}</span>. It expires in 10 minutes.</p>
      {ch.debug_code && <p data-testid={`${prefix}-debug-code`} className="font-mono text-xs text-amber-700">Test inbox code: {ch.debug_code}</p>}
      <Input data-testid={`${prefix}-code-input`} inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="h-12 text-center font-mono text-xl tracking-[0.5em]" aria-label="One-time code" />
      {extra}
      {error && <p role="alert" data-testid={`${prefix}-error`} className="text-sm text-destructive">{error}</p>}
      <Button data-testid={`${prefix}-submit-button`} type="submit" className="h-11 w-full" disabled={busy || code.length !== 6}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : submitLabel}</Button>
      <button type="button" className="text-xs text-muted-foreground underline" onClick={() => { setCh(null); setCode(""); }}>Use a different email</button>
    </form>
  );
};

export default function CandidateLogin() {
  const { signIn } = useAuth();
  const nav = useNavigate();
  const done = (data) => { signIn(data); nav("/candidate/dashboard", { replace: true }); };
  return (
    <AuthLayout testId="candidate-login-page" eyebrow="Candidate portal" title="Welcome back"
      subtitle="Sign in to continue your WeSchool application."
      aside={<><h2 className="text-3xl font-bold leading-tight">One account. Your entire admission journey.</h2><p className="mt-3 text-white/80">Application, payments, interviews, results and counselling, all in one place.</p></>}>
      <SessionNotice />
      <Tabs defaultValue="password">
        <TabsList className="mb-6 grid w-full grid-cols-2">
          <TabsTrigger data-testid="login-tab-password" value="password">Password</TabsTrigger>
          <TabsTrigger data-testid="login-tab-otp" value="otp">Email code</TabsTrigger>
        </TabsList>
        <TabsContent value="password"><PasswordForm onDone={done} /></TabsContent>
        <TabsContent value="otp">
          <EmailOtpForm startPath="/auth/candidate/otp-login/start" prefix="otp-login" submitLabel="Verify & sign in"
            onCode={async (id, code) => done((await http.post("/auth/candidate/otp-login/complete", { challenge_id: id, code })).data)} />
        </TabsContent>
      </Tabs>
      <p className="mt-8 text-sm text-muted-foreground">New to WeSchool? <Link data-testid="register-link" className="font-semibold text-primary hover:underline" to="/candidate/register">Create an account</Link></p>
    </AuthLayout>
  );
}

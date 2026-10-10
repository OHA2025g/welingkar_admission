import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { http } from "@/lib/api";
import { AuthLayout } from "@/components/portal/AuthLayout";
import { EmailOtpForm } from "./CandidateLogin";

export default function ForgotPassword() {
  const nav = useNavigate();
  const [pw, setPw] = useState("");
  return (
    <AuthLayout testId="forgot-password-page" eyebrow="Account recovery" title="Reset your password"
      subtitle="We will email a one-time code to your registered address. Each code works once."
      aside={<h2 className="text-3xl font-bold leading-tight">Recovery is verified, never assumed.</h2>}>
      <EmailOtpForm startPath="/auth/candidate/recovery/start" prefix="recovery" submitLabel="Reset password"
        extra={<div className="space-y-1.5"><Label htmlFor="rp-new">New password</Label>
          <Input id="rp-new" data-testid="recovery-new-password-input" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          <p className="text-xs text-muted-foreground">At least 8 characters with letters and numbers.</p></div>}
        onCode={async (id, code) => {
          await http.post("/auth/candidate/recovery/complete", { challenge_id: id, code, new_password: pw });
          toast.success("Password reset. Sign in with your new password.");
          nav("/candidate/login");
        }} />
      <p className="mt-8 text-sm"><Link className="font-semibold text-primary hover:underline" to="/candidate/login">Back to sign in</Link></p>
    </AuthLayout>
  );
}

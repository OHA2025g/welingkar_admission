import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { http, fmtDate, fmtINR, downloadFile, errMsg } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Card, StatusPill } from "@/components/portal/ui";
import { ChannelVerify } from "@/components/portal/ChannelVerify";

const ICON = { done: CheckCircle2, current: Circle, locked: Lock };
const STEP_LINK = { fee: "/candidate/payment", form: "/candidate/application", documents: "/candidate/application", submit: "/candidate/application", post: "/candidate/after-submission" };

export default function CandidateDashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/candidate/dashboard").then((r) => setD(r.data)); }, [user.identity_status]);
  const verified = user.identity_status === "verified";

  return (
    <div data-testid="candidate-dashboard">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">{d?.cycle?.name || "Admissions"}</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">Hello, {user.name.split(" ")[0]}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          <span>Candidate ID <b data-testid="candidate-ref" className="font-mono text-foreground">{user.candidate_ref}</b></span>
          <StatusPill testId="candidate-identity-status" status={user.identity_status} />
          {d?.application_ref && <span>Application <b data-testid="candidate-app-ref" className="font-mono text-foreground">{d.application_ref}</b> · <span data-testid="candidate-app-status" className="capitalize">{d.application_status}</span></span>}
        </div>
        {d?.progress && <div className="mt-5 max-w-md"><Progress value={d.progress.percent} className="h-2" /><p className="mt-1 text-xs text-muted-foreground">{d.progress.percent}% complete</p></div>}
        {d?.next_step && (
          <Card testId="next-step-card" className="mt-6">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Next step</p>
            <p className="mt-1 text-lg font-semibold">{d.next_step.title}</p>
            {d.unread > 0 && <p data-testid="home-unread" className="mt-1 text-sm text-muted-foreground">{d.unread} unread notice{d.unread === 1 ? "" : "s"}. Open the bell to read them.</p>}
            {d.next_step.path && <Button asChild className="mt-4 min-h-11 w-full sm:w-auto"><Link data-testid="next-step-button" to={d.next_step.path}>Continue</Link></Button>}
          </Card>
        )}
        {!!d?.countdowns?.length && (
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {d.countdowns.map((c) => (
              <Card key={c.key} testId={`countdown-${c.key}`} className="p-4">
                <p className="text-xs text-muted-foreground">{c.label}</p>
                <p className="mt-1 font-['Outfit'] text-2xl font-bold tabular-nums">{c.days < 0 ? `${Math.abs(c.days)}d ago` : c.days === 0 ? "Today" : `${c.days} days`}</p>
                <p className="text-xs text-muted-foreground">{fmtDate(c.date)}{c.detail ? ` · ${c.detail}` : ""}</p>
              </Card>
            ))}
          </div>
        )}

        <div className="mt-10 grid gap-8 lg:grid-cols-12">
          <div className="space-y-6 lg:col-span-7">
            {!verified && (
              <Card testId="verification-required-card">
                <h2 className="text-lg font-semibold">Finish verification</h2>
                <p className="mt-1 text-sm text-muted-foreground">Both your email and WhatsApp must be verified before you can pay the application fee.</p>
                <div className="mt-5 space-y-4">
                  <ChannelVerify channel="email" />
                  <ChannelVerify channel="whatsapp" />
                </div>
              </Card>
            )}
            <Card testId="application-journey-card">
              <h2 className="text-lg font-semibold">Your application journey</h2>
              <ol className="mt-6 space-y-1">
                {d?.steps?.map((s, i) => {
                  const I = ICON[s.status];
                  return (
                    <li key={s.key} data-testid={`journey-step-${s.key}`} className="flex items-center gap-4 rounded-md px-2 py-3">
                      <span className="w-6 text-right font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
                      <I className={`h-5 w-5 ${s.status === "done" ? "text-emerald-600" : s.status === "current" ? "text-primary" : "text-slate-300"}`} />
                      <span className={`flex-1 text-sm ${s.status === "locked" ? "text-muted-foreground" : "font-medium"}`}>{s.title}</span>
                      <span className="text-xs capitalize text-muted-foreground">{s.status}</span>
                      {s.status === "current" && STEP_LINK[s.key] && <Button asChild size="sm" variant="outline"><Link data-testid={`journey-go-${s.key}`} to={STEP_LINK[s.key]}>Open</Link></Button>}
                    </li>
                  );
                })}
              </ol>
            </Card>
          </div>
          <div className="space-y-6 lg:col-span-5">
            <Card testId="cycle-info-card">
              <h2 className="text-lg font-semibold">Cycle {d?.cycle?.code}</h2>
              <dl className="mt-4 divide-y divide-border text-sm">
                {[["Applications close", fmtDate(d?.cycle?.application_close)], ["Admission fee due", fmtDate(d?.cycle?.admission_fee_due)], ["Part B opens", fmtDate(d?.cycle?.part_b_open)],
                  ["Application fee", d?.cycle ? fmtINR(d.cycle.application_fee_inr) : "—"]].map(([k, v]) => (
                  <div key={k} className="flex justify-between py-2.5"><dt className="text-muted-foreground">{k}</dt><dd className="font-medium">{v}</dd></div>
                ))}
              </dl>
            </Card>
            {!!d?.documents?.length && (
              <Card testId="offer-pack-card">
                <h2 className="text-lg font-semibold">Your documents</h2>
                <div className="mt-4 flex flex-col gap-2">
                  {d.documents.map((doc) => (
                    <Button key={doc.path} variant="outline" className="min-h-11 justify-start" data-testid={`offer-download-${doc.path.split("/").pop()}`}
                      onClick={async () => { try { await downloadFile(doc.path, doc.filename); toast.success(`${doc.label} downloaded`); } catch (e) { toast.error(errMsg(e)); } }}>
                      {doc.label}
                    </Button>
                  ))}
                </div>
              </Card>
            )}
            <Card>
              <h2 className="text-lg font-semibold">Your details</h2>
              <dl className="mt-4 space-y-2 text-sm">
                {[["Email", user.email], ["Mobile", user.mobile], ["Location", `${user.city}, ${user.state}`]].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-4"><dt className="text-muted-foreground">{k}</dt><dd className="truncate">{v}</dd></div>
                ))}
              </dl>
            </Card>
          </div>
        </div>
    </div>
  );
}

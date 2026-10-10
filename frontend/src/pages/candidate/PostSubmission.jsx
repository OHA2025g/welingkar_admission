import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { http, errMsg, fmtIST } from "@/lib/api";
import { FieldList, RankedPicker, errorMap } from "@/components/candidate/FormEngine";
import { Card, PageHeader } from "@/components/portal/ui";

const Done = ({ at, testId, text = "Completed" }) => (
  <p data-testid={testId} className="flex items-center gap-2 text-sm font-medium text-emerald-700"><CheckCircle2 className="h-4 w-4" />{text} · {fmtIST(at)}</p>
);

const useAct = (setApp) => {
  const [busy, setBusy] = useState(null);
  const run = async (key, fn, ok) => {
    setBusy(key);
    try { setApp((await fn()).data); toast.success(ok); return true; }
    catch (e) { toast.error(errMsg(e)); return e?.response?.data?.detail; } finally { setBusy(null); }
  };
  return [busy, run];
};

const Answers = ({ kind, spec, state, run, busy, words }) => {
  const [a, setA] = useState(state?.answers || {});
  const [errs, setErrs] = useState({});
  const done = state?.submitted_at;
  const send = async (submit) => {
    const r = await run(`${kind}-${submit}`, () => http.put(`/candidate/application/post/${kind}`, { answers: a, submit }), submit ? "Submitted" : "Draft saved");
    setErrs(r && r !== true ? errorMap(r.errors) : {});
  };
  return (
    <div className="space-y-5">
      {spec.map((q) => {
        const n = (a[q.id] || "").trim().split(/\s+/).filter(Boolean).length;
        return (
          <div key={q.id} className="space-y-1.5">
            <Label htmlFor={`${kind}-${q.id}`}>{q.prompt || q.label}</Label>
            <Textarea id={`${kind}-${q.id}`} data-testid={`${kind}-${q.id}-input`} rows={words ? 6 : 3} disabled={!!done} value={a[q.id] || ""} onChange={(e) => setA({ ...a, [q.id]: e.target.value })} />
            <div className="flex justify-between text-xs"><span className="text-destructive">{errs[q.id]}</span>{words && <span className="text-muted-foreground">{n} words · {q.min_words}-{q.max_words}</span>}</div>
          </div>
        );
      })}
      {done ? <Done at={done} testId={`${kind}-submitted`} text="Submitted" /> : (
        <div className="flex gap-3">
          <Button data-testid={`${kind}-save-button`} variant="outline" disabled={!!busy} onClick={() => send(false)}>Save draft</Button>
          <Button data-testid={`${kind}-submit-button`} disabled={!!busy} onClick={() => send(true)}>{busy === `${kind}-true` ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit"}</Button>
        </div>
      )}
    </div>
  );
};

const GRAD_FIELDS = [
  { name: "graduation_status", label: "Graduation status", type: "select", options: [{ value: "completed", label: "Completed" }, { value: "final_year", label: "Final year" }] },
  { name: "expected_completion", label: "Expected completion (final year only)", type: "month" },
  { name: "meets_min_aggregate", label: "I have / expect at least 50% aggregate (45% for reserved categories)", type: "switch" },
  { name: "has_active_backlogs", label: "I have active backlogs", type: "switch" },
  { name: "accept", label: "I declare the above is true and accept that admission depends on meeting eligibility", type: "switch" },
];

export default function PostSubmission() {
  const [app, setApp] = useState(null);
  const [programs, setPrograms] = useState([]);
  const [accept, setAccept] = useState(false);
  const [prefs, setPrefs] = useState([]);
  const [grad, setGrad] = useState({ meets_min_aggregate: false, has_active_backlogs: false, accept: false });
  const [gradErr, setGradErr] = useState({});
  const [busy, run] = useAct(setApp);
  useEffect(() => {
    http.get("/candidate/application").then((r) => { setApp(r.data); setPrefs(r.data.sections.preferences?.ranked || []); });
    http.get("/candidate/admission-info").then((r) => setPrograms(r.data.programs));
  }, []);
  if (!app) return null;
  if (app.status !== "submitted") return (
    <div data-testid="post-submission-locked"><PageHeader title="After submission" description="These steps open after you submit your application." />
      <Button asChild><Link to="/candidate/application">Go to application form</Link></Button></div>
  );
  const p = app.post || {}, cfg = app.post_config;
  return (
    <div data-testid="post-submission-page">
      <PageHeader eyebrow={app.application_ref} title="After submission" description="Complete the declaration, essays, questionnaire and eligibility declaration, then confirm your data for shortlisting." />
      <div className="grid gap-6 xl:grid-cols-2">
        <Card testId="pgdm-declaration-card">
          <h2 className="font-semibold">PGDM declaration <span className="font-mono text-xs text-muted-foreground">{cfg.declaration.version}</span></h2>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{cfg.declaration.text}</p>
          <div className="mt-4">{p.declaration ? <Done at={p.declaration.accepted_at} testId="declaration-accepted" text="Accepted" /> : (
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-sm"><Checkbox data-testid="declaration-checkbox" checked={accept} onCheckedChange={setAccept} />I accept this declaration</label>
              <Button data-testid="declaration-submit-button" disabled={!accept || !!busy} onClick={() => run("decl", () => http.post("/candidate/application/post/declaration", { accept: true }), "Declaration accepted")}>Accept</Button>
            </div>)}</div>
        </Card>
        <Card testId="data-confirmation-card">
          <h2 className="font-semibold">Data confirmation for shortlisting</h2>
          <p className="mt-3 text-sm text-muted-foreground">Confirm that the submitted application (version {app.submitted_version}) is correct. If the admissions office corrects your data, you will be asked to reconfirm.</p>
          <div className="mt-4">{p.confirmation ? <Done at={p.confirmation.confirmed_at} testId="data-confirmed" text={`Confirmed v${p.confirmation.version}`} /> : (
            <Button data-testid="data-confirm-button" disabled={!!busy} onClick={() => run("conf", () => http.post("/candidate/application/post/confirm"), "Data confirmed")}>Confirm my data</Button>)}</div>
        </Card>
        <Card testId="preference-reset-card">
          <h2 className="font-semibold">Programme preference reset</h2>
          <p className="mt-1 text-sm text-muted-foreground">Allowed until Part B opens. Every change is kept in history.</p>
          <div className="mt-4"><RankedPicker programs={programs} value={prefs} onChange={setPrefs} /></div>
          <Button data-testid="preference-reset-button" className="mt-4" disabled={!!busy} onClick={() => run("pref", () => http.post("/candidate/application/post/preferences", { ranked: prefs }), "Preferences updated")}>Save new preferences</Button>
          {p.preference_history && (
            <ol data-testid="preference-history" className="mt-4 space-y-1 text-xs text-muted-foreground">
              {p.preference_history.map((h) => <li key={h.version}>v{h.version} · {fmtIST(h.at)} · {h.ranked.join(" > ")}</li>)}
            </ol>
          )}
        </Card>
        <Card testId="graduation-eligibility-card">
          <h2 className="font-semibold">Graduation eligibility declaration</h2>
          <div className="mt-4">{p.graduation ? <Done at={p.graduation.submitted_at} testId="graduation-submitted" text="Declared" /> : (<>
            <FieldList fields={GRAD_FIELDS} value={grad} onChange={setGrad} errors={gradErr} />
            <Button data-testid="graduation-submit-button" className="mt-4" disabled={!!busy} onClick={async () => {
              const r = await run("grad", () => http.post("/candidate/application/post/graduation", grad), "Eligibility declared");
              setGradErr(r && r !== true ? errorMap(r.errors) : {});
            }}>Submit declaration</Button></>)}</div>
        </Card>
        <Card testId="essays-card"><h2 className="mb-4 font-semibold">Descriptive essays</h2><Answers kind="essays" spec={cfg.essays} state={p.essays} run={run} busy={busy} words /></Card>
        <Card testId="piq-card"><h2 className="mb-1 font-semibold">Personal Interview Questionnaire (PIQ)</h2>
          <p className="mb-4 text-sm text-muted-foreground">Available now; your PI slot booking opens in Phase 3.</p>
          <Answers kind="piq" spec={cfg.piq} state={p.piq} run={run} busy={busy} /></Card>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, CircleDot, Upload, Loader2, Lock, Download, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { FORM_SCHEMA, DEFAULTS } from "@/lib/formSchema";
import { FieldList, RankedPicker, errorMap } from "@/components/candidate/FormEngine";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { PolicyHelp } from "@/components/portal/PolicyHelp";

const STATUS_ICON = { complete: CheckCircle2, in_progress: CircleDot };

const Uploads = ({ app, reload, locked }) => {
  const [busy, setBusy] = useState(null);
  const [urls, setUrls] = useState({});
  useEffect(() => {
    ["photo", "signature"].forEach(async (k) => {
      const id = app[`${k}_file_id`];
      if (!id) return;
      const r = await http.get(`/files/${id}`, { responseType: "blob" });
      setUrls((u) => ({ ...u, [k]: URL.createObjectURL(r.data) }));
    });
  }, [app]);
  const up = async (kind, file) => {
    if (!file) return;
    setBusy(kind);
    const fd = new FormData();
    fd.append("file", file);
    try { await http.post(`/candidate/application/uploads/${kind}`, fd); toast.success(`${kind === "photo" ? "Photo" : "Signature"} uploaded`); reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(null); }
  };
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {[["photo", "Passport photo", "JPG/PNG, max 200 KB, min 200×200 px, portrait"], ["signature", "Signature", "JPG/PNG, max 100 KB, min 150×50 px, landscape"]].map(([k, l, hint]) => (
        <div key={k} data-testid={`upload-${k}-card`} className="rounded-md border border-border p-4">
          <div className="flex items-center justify-between"><p className="font-medium">{l}</p><StatusPill testId={`upload-${k}-status`} status={app[`${k}_file_id`] ? "success" : "registered"} /></div>
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
          <div className={`mt-4 flex items-center justify-center rounded-md bg-secondary ${k === "photo" ? "h-44" : "h-24"}`}>
            {urls[k] ? <img src={urls[k]} alt={l} data-testid={`upload-${k}-preview`} className="max-h-full max-w-full object-contain" /> : <span className="text-xs text-muted-foreground">Not uploaded</span>}
          </div>
          {!locked && (
            <label className="mt-4 inline-flex cursor-pointer items-center gap-2 rounded-md border border-input px-3 py-2 text-sm font-medium hover:bg-secondary focus-within:ring-2 focus-within:ring-ring">
              {busy === k ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}{app[`${k}_file_id`] ? "Replace" : "Upload"}
              <input data-testid={`upload-${k}-input`} type="file" accept="image/jpeg,image/png" className="sr-only" onChange={(e) => up(k, e.target.files?.[0])} />
            </label>
          )}
        </div>
      ))}
    </div>
  );
};

const Review = ({ app, submit, busy, problems }) => {
  const p = app.progress;
  const ready = p.sections_complete === p.sections_total && p.photo && p.signature;
  return (
    <div className="space-y-5">
      <ul className="space-y-2 text-sm">
        {app.sections_meta.map((s) => <li key={s.key} className="flex justify-between"><span>{s.title}</span><StatusPill testId={`review-status-${s.key}`} label={app.section_status[s.key] === "complete" ? "Complete" : "Incomplete"} status={app.section_status[s.key] === "complete" ? "success" : "draft"} /></li>)}
        <li className="flex justify-between"><span>Photo & signature</span><StatusPill label={p.photo && p.signature ? "Uploaded" : "Missing"} status={p.photo && p.signature ? "success" : "draft"} /></li>
        <li className="flex justify-between"><span>Application fee</span><StatusPill testId="review-fee-status" label={app.fee_paid ? "Paid" : "Unpaid"} status={app.fee_paid ? "success" : "denied"} /></li>
      </ul>
      {!app.fee_paid && <p data-testid="submit-fee-required" className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="h-4 w-4" />Pay the application fee before submitting. <Link className="font-semibold underline" to="/candidate/payment">Pay now</Link></p>}
      {problems && (
        <div data-testid="submit-problems" role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {problems.map((x) => <p key={x.section}><b>{x.title}:</b> {x.errors.map((e) => e.message).join("; ")}</p>)}
        </div>
      )}
      <p className="text-xs text-muted-foreground">Once submitted, your application is locked and a versioned PDF is generated. Changes after submission need an authorised correction.</p>
      <Button data-testid="application-submit-button" className="h-11 w-full sm:w-auto" disabled={busy || !ready || !app.fee_paid} onClick={submit}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit application"}
      </Button>
    </div>
  );
};

export default function ApplicationPage() {
  const [app, setApp] = useState(null);
  const [programs, setPrograms] = useState([]);
  const [active, setActive] = useState("personal");
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [save, setSave] = useState({ state: "idle" });
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState(null);
  const timer = useRef(null);
  const resumed = useRef(false);

  const load = useCallback(async () => {
    const { data } = await http.get("/candidate/application");
    setApp(data);
    setValues((v) => (Object.keys(v).length ? v : Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, { ...DEFAULTS[k], ...(data.sections[k] || {}) }]))));
    setErrors((e) => (Object.keys(e).length ? e : Object.fromEntries(Object.entries(data.section_errors || {}).map(([k, v]) => [k, errorMap(v)]))));
  }, []);
  useEffect(() => { load(); http.get("/candidate/admission-info").then((r) => setPrograms(r.data.programs)); }, [load]);
  useEffect(() => {
    if (!app || resumed.current || app.status !== "draft") return;
    const order = [...(app.sections_meta || []).map((s) => s.key), "uploads"];
    const first = order.find((key) => (key === "uploads" ? !(app.progress?.photo && app.progress?.signature) : app.section_status?.[key] !== "complete"));
    if (first) setActive(first);
    resumed.current = true;
  }, [app]);

  const persist = useCallback(async (key, data) => {
    setSave({ state: "saving" });
    try {
      const { data: r } = await http.put(`/candidate/application/sections/${key}`, { data });
      setErrors((e) => ({ ...e, [key]: errorMap(r.errors) }));
      setApp((a) => ({ ...a, section_status: { ...a.section_status, [key]: r.status }, progress: r.progress }));
      setSave({ state: "saved", at: r.saved_at });
    } catch (e) { setSave({ state: "error", msg: errMsg(e) }); }
  }, []);

  const change = (key, data) => {
    setValues((v) => ({ ...v, [key]: data }));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => persist(key, data), 1200);
  };
  const go = (key) => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; if (FORM_SCHEMA[active] || active === "preferences") persist(active, values[active]); }
    setActive(key);
  };
  const submit = async () => {
    setBusy(true); setProblems(null);
    try { const { data } = await http.post("/candidate/application/submit"); setApp(data); toast.success("Application submitted"); }
    catch (e) { setProblems(e?.response?.data?.detail?.problems || null); toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const pdf = async () => {
    try { await downloadFile("/candidate/application/pdf", `${app.application_ref}.pdf`); toast.success("Application PDF downloaded"); }
    catch (e) { toast.error(errMsg(e)); }
  };

  if (!app) return null;
  const locked = app.status !== "draft";
  const steps = [...app.sections_meta, { key: "uploads", title: "Photo & signature" }, { key: "review", title: "Review & submit" }];
  const sectionErr = errors[active] || {};
  const general = Object.entries(sectionErr).filter(([f]) => f === "_" || !f.includes(".") && !(FORM_SCHEMA[active] || []).some((x) => x.name === f && !["list", "group"].includes(x.type)));

  return (
    <div data-testid="application-page">
      <PageHeader eyebrow={`Application ${app.application_ref}`} title={locked ? "Application submitted" : "Application form"}
        description={locked ? `Submitted ${fmtIST(app.submitted_at)} · version ${app.submitted_version}. Your application is locked.` : "Sections save automatically as drafts and are validated on the server."}
        actions={locked && <Button data-testid="application-download-pdf-button" onClick={pdf}><Download className="mr-1.5 h-4 w-4" />Download PDF</Button>} />
      <div className="mb-8 max-w-xl">
        <div className="mb-2 flex justify-between text-sm"><span className="font-medium">Overall progress</span><span data-testid="application-progress-percent" className="tabular-nums">{app.progress.percent}%</span></div>
        <Progress value={app.progress.percent} className="h-2" />
      </div>
      <div className="grid gap-8 lg:grid-cols-[260px_1fr]">
        <nav aria-label="Application sections" className="space-y-1">
          {steps.map((s, i) => {
            const st = app.section_status[s.key] || (s.key === "uploads" ? (app.progress.photo && app.progress.signature ? "complete" : "") : "");
            const I = locked ? Lock : STATUS_ICON[st] || Circle;
            return (
              <button key={s.key} data-testid={`section-tab-${s.key}`} onClick={() => go(s.key)}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm transition-colors duration-150 ${active === s.key ? "bg-accent font-semibold text-accent-foreground" : "hover:bg-secondary"}`}>
                <span className="w-5 font-mono text-xs text-muted-foreground">{i + 1}</span>
                <I className={`h-4 w-4 ${st === "complete" ? "text-emerald-600" : st === "in_progress" ? "text-amber-600" : "text-slate-400"}`} />
                <span className="flex-1">{s.title}</span>
              </button>
            );
          })}
        </nav>
        <Card testId={`section-panel-${active}`}>
          <div className="mb-6 flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">{steps.find((s) => s.key === active)?.title}</h2>
            {!locked && FORM_SCHEMA[active] !== undefined || active === "preferences" ? (
              <span data-testid="autosave-status" className="text-xs text-muted-foreground">
                {save.state === "saving" ? "Saving…" : save.state === "saved" ? `Saved at ${fmtIST(save.at)}` : save.state === "error" ? <span className="text-destructive">{save.msg}</span> : app.updated_at ? `Saved at ${fmtIST(app.updated_at)}` : ""}
              </span>
            ) : null}
          </div>
          {general.length > 0 && (FORM_SCHEMA[active] || active === "preferences") && (
            <div data-testid="section-errors" role="alert" className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {general.map(([f, m]) => <p key={f}>{m}</p>)}
            </div>
          )}
          {FORM_SCHEMA[active] && <FieldList fields={FORM_SCHEMA[active]} value={values[active]} errors={sectionErr} disabled={locked} onChange={(d) => change(active, d)} />}
          {active === "preferences" && <RankedPicker programs={programs} disabled={locked} value={values.preferences?.ranked || []} onChange={(r) => change("preferences", { ranked: r })} />}
          {active === "uploads" && <div className="mb-6"><PolicyHelp topic="documents" /></div>}
          {active === "uploads" && <Uploads app={app} reload={load} locked={locked} />}
          {active === "review" && (locked ? <p data-testid="application-locked-message" className="text-sm">Your application is submitted and locked. <Link className="font-semibold text-primary underline" to="/candidate/after-submission">Continue with declarations and essays</Link>.</p> : <Review app={app} submit={submit} busy={busy} problems={problems} />)}
          {!locked && active !== "review" && (
            <div className="sticky bottom-4 mt-8 flex justify-end">
              <Button data-testid="section-next-button" variant="outline" className="min-h-11" onClick={() => go(steps[steps.findIndex((s) => s.key === active) + 1].key)}>Save & continue</Button>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

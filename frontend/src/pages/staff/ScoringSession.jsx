import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Lock, Save, Send } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { http, errMsg } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { AuthImage } from "@/components/portal/AuthImage";

const Summary = ({ s }) => (
  <dl className="grid gap-1 text-xs text-muted-foreground sm:grid-cols-2">
    <div><dt className="inline font-semibold text-foreground">Graduation </dt><dd className="inline">{s.graduation}</dd></div>
    <div><dt className="inline font-semibold text-foreground">Exams </dt><dd className="inline">{s.exams.join("; ")}</dd></div>
    <div><dt className="inline font-semibold text-foreground">Work </dt><dd className="inline">{s.work.join("; ") || "Fresher"}</dd></div>
    <div><dt className="inline font-semibold text-foreground">Preferences </dt><dd className="inline">{s.preferences.join(" > ")}</dd></div>
  </dl>
);

const CandidateCard = ({ c, rubric, type, value, onChange, canScore }) => {
  const locked = c.assessment?.status === "submitted";
  const absent = c.attendance === "absent";
  const total = rubric.reduce((n, r) => n + (Number(value[r.key]) || 0), 0);
  return (
    <Card testId={`score-card-${c.candidate_ref}`} className={locked ? "bg-secondary/40" : ""}>
      <div className="flex gap-4">
        {type === "PI" && <AuthImage fileId={c.photo_file_id} alt={`Photo of ${c.name}`} className="h-24 w-20 shrink-0 rounded-sm" testId={`score-photo-${c.candidate_ref}`} />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold">{c.name}</p><span className="font-mono text-xs text-muted-foreground">{c.application_ref}</span>
            {locked && <StatusPill testId={`score-locked-${c.candidate_ref}`} status="active" label="submitted · locked" />}
            {!locked && c.assessment && <StatusPill status="draft" label="draft saved" />}
            {absent && <StatusPill status="denied" label="absent" />}
          </div>
          <div className="mt-2"><Summary s={c.summary} /></div>
          {type === "PI" && c.summary.piq && <details className="mt-2 text-xs"><summary className="cursor-pointer font-semibold">PIQ answers</summary>
            <ul className="mt-1 space-y-1 text-muted-foreground">{Object.entries(c.summary.piq).map(([k, v]) => <li key={k}><b className="text-foreground">{k}:</b> {v}</li>)}</ul></details>}
        </div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {rubric.map((r) => (
          <label key={r.key} className="space-y-1 text-xs font-medium">{r.label}
            <select data-testid={`score-${c.candidate_ref}-${r.key}`} disabled={locked || absent || !canScore} value={value[r.key] ?? ""}
              onChange={(e) => onChange({ ...value, [r.key]: e.target.value === "" ? undefined : Number(e.target.value) })}
              className="block h-9 w-full rounded-md border border-input bg-background px-2 text-sm disabled:opacity-60">
              <option value="">—</option>{Array.from({ length: r.max + 1 }, (_, i) => <option key={i} value={i}>{i}</option>)}
            </select>
          </label>
        ))}
      </div>
      <p data-testid={`score-total-${c.candidate_ref}`} className="mt-3 text-sm tabular-nums">Total <b>{total}</b> / {rubric.reduce((n, r) => n + r.max, 0)}</p>
    </Card>
  );
};

export default function ScoringSession() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [scores, setScores] = useState({});
  const [error, setError] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const apply = (data) => { setD(data); setScores(Object.fromEntries(data.candidates.map((c) => [c.application_id, c.assessment?.scores || {}]))); };
  const load = useCallback(() => http.get(`/panel/sessions/${id}`).then((r) => apply(r.data)).catch((e) => setError(errMsg(e))), [id]);
  useEffect(() => { load(); }, [load]);
  const open = d ? d.candidates.filter((c) => c.assessment?.status !== "submitted" && c.attendance !== "absent") : [];
  const send = async (submit) => {
    const entries = open.map((c) => ({ application_id: c.application_id, scores: Object.fromEntries(Object.entries(scores[c.application_id] || {}).filter(([, v]) => v !== undefined)) }))
      .filter((e) => submit || Object.keys(e.scores).length);
    if (!entries.length) return toast.error("Enter at least one score");
    try { const { data } = await http.put(`/panel/sessions/${id}/scores`, { entries, submit }); apply(data); toast.success(submit ? "Scores submitted and locked" : "Draft saved"); }
    catch (e) { toast.error(errMsg(e)); } finally { setConfirm(false); }
  };
  if (error) return <Card testId="scoring-error"><p className="text-sm text-destructive">{error}</p></Card>;
  if (!d) return null;
  const s = d.session;
  return (
    <div data-testid="scoring-session-page" onContextMenu={(e) => e.preventDefault()}>
      <Link to="/staff/scoring" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />My sessions</Link>
      <PageHeader eyebrow={`${s.type_label} · rubric v${d.rubric_version}`} title={`${s.date} · ${s.start}–${s.end} IST`} description={`${s.location} · ${s.room}. ${s.type === "GA" ? "Score the whole group, then submit collectively." : "Question-level scores for each candidate. No download or print in this view."}`}
        actions={d.can_score && open.length > 0 && <>
          <Button data-testid="scores-save-draft-button" variant="outline" onClick={() => send(false)}><Save className="mr-1.5 h-4 w-4" />Save draft</Button>
          <Button data-testid="scores-submit-button" onClick={() => setConfirm(true)}><Send className="mr-1.5 h-4 w-4" />Submit {open.length} {open.length === 1 ? "candidate" : "candidates"}</Button></>} />
      {!d.can_score && <p data-testid="scoring-not-started" className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">Scoring opens on the session date.</p>}
      {d.can_score && open.length === 0 && d.candidates.length > 0 && <p data-testid="scoring-all-locked" className="mb-6 flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"><Lock className="h-4 w-4" />All scores for this session are submitted and locked.</p>}
      <div className="space-y-4">
        {d.candidates.map((c) => <CandidateCard key={c.application_id} c={c} rubric={d.rubric} type={s.type} canScore={d.can_score}
          value={scores[c.application_id] || {}} onChange={(v) => setScores({ ...scores, [c.application_id]: v })} />)}
      </div>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Submit and lock scores?</AlertDialogTitle>
            <AlertDialogDescription>Every rubric item must be scored. After submission you cannot edit these scores; an administrator correction is audited.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction data-testid="scores-submit-confirm" onClick={() => send(true)}>Submit</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

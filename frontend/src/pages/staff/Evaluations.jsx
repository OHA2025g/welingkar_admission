import { useCallback, useEffect, useState } from "react";
import { Download, FileText, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, downloadFile } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { SlotReportTab } from "@/components/interviews/SlotReportTab";

const sel = "h-9 rounded-md border border-input bg-background px-3 text-sm";

const CorrectDialog = ({ row, rubric, onClose, onDone }) => {
  const [scores, setScores] = useState(row.scores);
  const [reason, setReason] = useState("");
  const save = async () => {
    try { await http.post(`/admin/assessments/${row.id}/correct`, { scores, reason }); toast.success("Score corrected (audited)"); onDone(); onClose(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="score-correct-dialog">
        <DialogHeader><DialogTitle>Correct {row.candidate_name} · {row.panelist_name}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">
          {rubric.map((r) => <label key={r.key} className="space-y-1 text-xs font-medium">{r.label} (0–{r.max})
            <Input data-testid={`correct-${r.key}-input`} type="number" min={0} max={r.max} value={scores[r.key] ?? ""} onChange={(e) => setScores({ ...scores, [r.key]: Number(e.target.value) })} /></label>)}
        </div>
        <Input aria-label="Reason" data-testid="correct-reason-input" placeholder="Reason (required, audited)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button data-testid="correct-save-button" onClick={save} disabled={reason.trim().length < 5}>Save correction</Button>
      </DialogContent>
    </Dialog>
  );
};

export default function EvaluationsPage() {
  const { user } = useAuth();
  const [type, setType] = useState("GA");
  const [f, setF] = useState({ panelist_id: "", date: "" });
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(null);
  const params = Object.fromEntries(Object.entries({ type, ...f }).filter(([, v]) => v));
  const load = useCallback(() => { if (type !== "slots") http.get("/reports/evaluation", { params }).then((r) => setD(r.data)); }, [JSON.stringify(params)]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  const exp = async () => { try { const n = await downloadFile("/reports/evaluation/export", `${type}-scores.xlsx`, params); toast.success(`${n} downloaded`); } catch (e) { toast.error(errMsg(e)); } };
  const batch = async (sid) => { try { await downloadFile(`/reports/evaluation/ga-batch/${sid}/pdf`, "ga-batch.pdf"); } catch (e) { toast.error(errMsg(e)); } };
  const sessions = d ? [...new Map(d.rows.map((r) => [r.session_id, r])).values()] : [];
  return (
    <div data-testid="evaluations-page">
      <PageHeader eyebrow="Reports" title="GA / PI evaluation reports" description="Live score data with score versions. Panelist-specific Excel files are produced by filtering on a panelist before export." />
      <Tabs value={type} onValueChange={(v) => { setType(v); setD(null); }} className="mb-4"><TabsList>
        <TabsTrigger data-testid="eval-tab-ga" value="GA">GA scores</TabsTrigger><TabsTrigger data-testid="eval-tab-pi" value="PI">PI scores</TabsTrigger>
        <TabsTrigger data-testid="eval-tab-slots" value="slots">Slot report</TabsTrigger></TabsList></Tabs>
      {type === "slots" ? <SlotReportTab /> : d && (<>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <select aria-label="Panelist" data-testid="eval-panelist-filter" className={sel} value={f.panelist_id} onChange={(e) => setF({ ...f, panelist_id: e.target.value })}>
            <option value="">All panelists</option>{d.panelists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <Input aria-label="Date" data-testid="eval-date-filter" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} className="w-44" />
          <Button data-testid="eval-export-button" variant="outline" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Export {f.panelist_id ? "panelist file" : "Excel"}</Button>
          {type === "GA" && sessions.map((s) => <Button key={s.session_id} size="sm" variant="ghost" data-testid={`ga-batch-pdf-${s.session_id}`} onClick={() => batch(s.session_id)}><FileText className="mr-1 h-4 w-4" />Batch PDF {s.date} {s.slot}</Button>)}
        </div>
        <Card className="overflow-x-auto p-0">
          <Table data-testid="eval-table">
            <TableHeader><TableRow>{["Date / slot", "Venue", "Candidate", "Panelist", ...d.rubric.map((r) => r.label), "Total", "Status", "Ver.", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {d.rows.length === 0 && <TableRow><TableCell colSpan={8 + d.rubric.length} className="py-8 text-center text-sm text-muted-foreground">No scores for these filters.</TableCell></TableRow>}
              {d.rows.map((r) => (
                <TableRow key={r.id} data-testid={`eval-row-${r.candidate_ref}-${r.panelist_id}`}>
                  <TableCell className="text-xs">{r.date}<p className="text-muted-foreground">{r.slot}</p></TableCell>
                  <TableCell className="text-xs">{r.location}<p className="text-muted-foreground">{r.room}</p></TableCell>
                  <TableCell className="text-sm">{r.candidate_name}<p className="font-mono text-xs text-muted-foreground">{r.candidate_ref}</p></TableCell>
                  <TableCell className="text-sm">{r.panelist_name}</TableCell>
                  {d.rubric.map((c) => <TableCell key={c.key} className="tabular-nums">{r.scores[c.key] ?? "—"}</TableCell>)}
                  <TableCell className="tabular-nums">{r.total}/{r.max_total}</TableCell>
                  <TableCell><StatusPill status={r.status === "submitted" ? "active" : "draft"} label={r.status} /></TableCell>
                  <TableCell className="text-xs">v{r.version}{r.corrections ? ` (${r.corrections} corr.)` : ""}</TableCell>
                  <TableCell>{can(user, "assessments.correct") && r.status === "submitted" && <Button size="sm" variant="ghost" data-testid={`eval-correct-${r.id}`} onClick={() => setEdit(r)}><PencilLine className="h-4 w-4" /></Button>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </>)}
      {edit && <CorrectDialog row={edit} rubric={d.rubric} onClose={() => setEdit(null)} onDone={load} />}
    </div>
  );
}

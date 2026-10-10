import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Download, Megaphone } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const LABEL = { selected: "Selected", waitlisted: "Waitlisted", not_selected: "Not selected", incomplete: "Incomplete", manual_selection: "Institute selection" };

export default function ResultVersion() {
  const { version } = useParams();
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [program, setProgram] = useState("");
  const [list, setList] = useState("general");
  const [action, setAction] = useState(null);
  const load = useCallback(() => http.get(`/results/versions/${version}`).then((r) => setD(r.data)), [version]);
  useEffect(() => { load(); }, [load]);
  const act = async () => {
    try { await http.post(`/results/versions/${version}/${action}`, { note: "" }); toast.success(action === "approve" ? "Version approved" : "Version published to candidates"); load(); }
    catch (e) { toast.error(errMsg(e)); } finally { setAction(null); }
  };
  const exp = async () => { try { await downloadFile(`/results/versions/${version}/export`, `results-v${version}.xlsx`); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  const approver = can(user, "results.publish");
  const tfw = list === "tfw";
  const rows = d.rows.filter((r) => (!program || r.program_code === program) && (!tfw || r.tfw_rank));
  const r = d.ruleset.selection_rules;
  return (
    <div data-testid="result-version-page">
      <Link to="/staff/results" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />All versions</Link>
      <PageHeader eyebrow={`Result version · ${d.status}`} title={`Version ${d.version}`} description={d.note || "No note"}
        actions={<>
          <Button variant="outline" data-testid="result-export-button" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Export Excel</Button>
          {approver && d.status === "generated" && <Button data-testid="result-approve-button" onClick={() => setAction("approve")}><CheckCircle2 className="mr-1.5 h-4 w-4" />Approve</Button>}
          {approver && d.status === "approved" && <Button data-testid="result-publish-button" onClick={() => setAction("publish")}><Megaphone className="mr-1.5 h-4 w-4" />Publish to candidates</Button>}
        </>} />
      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <Card><p className="text-xs uppercase tracking-wider text-muted-foreground">Status</p><div className="mt-2"><StatusPill testId="result-version-status" status={d.status} /></div>
          <p className="mt-2 text-xs text-muted-foreground">Generated {fmtIST(d.created_at)} by {d.created_by}</p>
          {d.approved_by && <p className="text-xs text-muted-foreground">Approved {fmtIST(d.approved_at)} by {d.approved_by}</p>}
          {d.published_by && <p className="text-xs text-muted-foreground">Published {fmtIST(d.published_at)} by {d.published_by}</p>}</Card>
        <Card><p className="text-xs uppercase tracking-wider text-muted-foreground">Ruleset · selection v{d.ruleset.selection_rules_version}</p>
          <p className="mt-2 text-sm">Exam {r.exam_weight}% · GA {r.ga_weight}% · PI {r.pi_weight}%</p>
          <p className="text-sm">Selected ≥ {r.selected_cutoff} · waitlist ≥ {r.waitlist_cutoff}</p>
          <p className="text-xs text-muted-foreground">TFW v{d.ruleset.tfw_policy_version}: income ≤ ₹{d.ruleset.tfw_policy.family_income_limit_inr.toLocaleString("en-IN")}</p></Card>
        <Card><p className="text-xs uppercase tracking-wider text-muted-foreground">Summary</p>
          <p data-testid="result-summary" className="mt-2 text-sm">{d.summary.candidates} candidates · {d.summary.selected} selected · {d.summary.waitlisted} waitlisted · {d.summary.incomplete} incomplete · {d.summary.manual_selection} institute selection</p>
          <p className="text-sm">TFW: {d.summary.tfw_selected} selected · {d.summary.tfw_waitlisted} waitlisted</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">inputs {d.inputs.checksum.slice(0, 16)}</p></Card>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={list} onValueChange={setList}><TabsList>
          <TabsTrigger data-testid="result-list-general" value="general">General merit</TabsTrigger>
          <TabsTrigger data-testid="result-list-tfw" value="tfw">TFW merit (separate)</TabsTrigger>
        </TabsList></Tabs>
        <select aria-label="Programme" data-testid="result-program-filter" className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={program} onChange={(e) => setProgram(e.target.value)}>
          <option value="">All programmes</option>{d.programs.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
        </select>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="result-rows-table">
          <TableHeader><TableRow>{["Programme", "Candidate", "Choice", "Exam %ile", "GA %", "PI %", "Composite", tfw ? "TFW rank" : "Rank", "Outcome"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((x) => (
              <TableRow key={`${x.program_code}-${x.candidate_id}`} data-testid={`result-row-${x.program_code}-${x.candidate_ref}`}>
                <TableCell className="text-sm">{x.program_name}</TableCell>
                <TableCell className="text-sm">{x.name}<p className="font-mono text-xs text-muted-foreground">{x.application_ref}{x.tfw_eligible ? " · TFW" : ""}</p></TableCell>
                <TableCell>{x.choice}</TableCell>
                {[x.exam_percentile, x.ga, x.pi, x.composite].map((n, i) => <TableCell key={i} className="tabular-nums">{n ?? "—"}</TableCell>)}
                <TableCell className="tabular-nums">{(tfw ? x.tfw_rank : x.rank) ?? "—"}</TableCell>
                <TableCell><StatusPill status={tfw ? x.tfw_outcome : x.outcome} label={LABEL[tfw ? x.tfw_outcome : x.outcome]} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <AlertDialog open={!!action} onOpenChange={(o) => !o && setAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>{action === "approve" ? `Approve version ${d.version}?` : `Publish version ${d.version}?`}</AlertDialogTitle>
            <AlertDialogDescription>{action === "approve" ? "Approval records your review. Candidates still see nothing until you publish." : "Candidates will see these outcomes immediately. Any previously published version is superseded."}</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction data-testid="result-action-confirm" onClick={act}>Confirm</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PlayCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

export default function ResultsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const load = useCallback(() => http.get("/results/versions").then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const generate = async () => {
    try { const { data } = await http.post("/results/versions", { note }); toast.success(`Version ${data.version} generated`); setOpen(false); setNote(""); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const published = rows.find((r) => r.status === "published");
  return (
    <div data-testid="results-page">
      <PageHeader eyebrow="Results" title="Result versions" description="Generated versions are drafts and never change what candidates see. Only the Result Approver can approve and publish one version."
        actions={can(user, "results.generate") && <Button data-testid="results-generate-button" onClick={() => setOpen(true)}><PlayCircle className="mr-1.5 h-4 w-4" />Generate new version</Button>} />
      <p data-testid="results-published-banner" className="mb-6 text-sm">{published ? <>Published to candidates: <b>v{published.version}</b> on {fmtIST(published.published_at)} by {published.published_by}</> : "No version is published yet."}</p>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="results-versions-table">
          <TableHeader><TableRow>{["Version", "Status", "Generated", "Rules", "Inputs", "Selected", "Waitlisted", "TFW selected", "Note", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((v) => (
              <TableRow key={v.id} data-testid={`result-version-row-${v.version}`}>
                <TableCell className="font-mono font-semibold">v{v.version}</TableCell>
                <TableCell><StatusPill testId={`result-version-status-${v.version}`} status={v.status} /></TableCell>
                <TableCell className="text-xs">{fmtIST(v.created_at)}<p className="text-muted-foreground">{v.created_by}</p></TableCell>
                <TableCell className="text-xs">selection v{v.ruleset.selection_rules_version} · TFW v{v.ruleset.tfw_policy_version}</TableCell>
                <TableCell className="text-xs">{v.inputs.applications} apps · {v.inputs.assessments} scores<p className="font-mono text-muted-foreground">{v.inputs.checksum.slice(0, 10)}</p></TableCell>
                <TableCell className="tabular-nums">{v.summary.selected}</TableCell>
                <TableCell className="tabular-nums">{v.summary.waitlisted}</TableCell>
                <TableCell className="tabular-nums">{v.summary.tfw_selected}</TableCell>
                <TableCell className="max-w-48 text-xs text-muted-foreground">{v.note}</TableCell>
                <TableCell><Button asChild size="sm" variant="outline"><Link data-testid={`result-version-open-${v.version}`} to={`/staff/results/${v.version}`}>Review</Link></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="results-generate-dialog">
          <DialogHeader><DialogTitle>Generate result version</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Uses the active selection rules, TFW policy and all submitted GA/PI scores. You can run this as often as needed.</p>
          <Input aria-label="Note" data-testid="results-generate-note-input" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <Button data-testid="results-generate-confirm" onClick={generate}>Generate</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

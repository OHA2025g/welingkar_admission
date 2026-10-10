import { useCallback, useEffect, useState } from "react";
import { Download, RotateCcw, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const sel = "h-9 rounded-md border border-input bg-background px-3 text-sm";
const TONE = { inserted: "active", validated: "draft", rolled_back: "archived", committing: "draft" };

const Report = ({ b, onClose, onCommit }) => (
  <Dialog open onOpenChange={(o) => !o && onClose()}>
    <DialogContent data-testid="import-report-dialog" className="max-w-2xl">
      <DialogHeader><DialogTitle>{b.filename} · {b.rows_valid}/{b.rows_total} valid</DialogTitle></DialogHeader>
      <div className="max-h-80 overflow-y-auto">
        {b.errors.length === 0 ? <p className="text-sm text-emerald-700">No row errors.</p> : (
          <Table data-testid="import-errors-table"><TableHeader><TableRow><TableHead>Row</TableHead><TableHead>Field</TableHead><TableHead>Error</TableHead></TableRow></TableHeader>
            <TableBody>{b.errors.map((e, i) => <TableRow key={i}><TableCell>{e.row}</TableCell><TableCell className="font-mono text-xs">{e.field}</TableCell><TableCell className="text-sm">{e.message}</TableCell></TableRow>)}</TableBody></Table>)}
      </div>
      <div className="flex flex-wrap gap-2">
        {b.errors.length > 0 && <Button variant="outline" data-testid="import-error-report-button" onClick={() => downloadFile(`/partb/imports/${b.id}/error-report`, "errors.xlsx").catch((e) => toast.error(errMsg(e)))}><Download className="mr-1.5 h-4 w-4" />Error report</Button>}
        {b.status === "validated" && <Button data-testid="import-commit-button" onClick={onCommit} disabled={!b.rows_valid}>Insert {b.rows_valid} valid rows</Button>}
      </div>
    </DialogContent>
  </Dialog>
);

export default function PartBImports() {
  const [rows, setRows] = useState([]);
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("validate");
  const [ver, setVer] = useState("");
  const [open, setOpen] = useState(null);
  const [rb, setRb] = useState(null);
  const [reason, setReason] = useState("");
  const load = useCallback(() => http.get("/partb/imports").then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const show = async (id) => setOpen((await http.get(`/partb/imports/${id}`)).data);
  const done = (b) => { toast.success(`${b.status}: ${b.rows_valid}/${b.rows_total} valid rows`); load(); show(b.id); };
  const upload = async () => {
    const fd = new FormData(); fd.append("file", file); fd.append("mode", mode);
    try { done((await http.post("/partb/imports", fd)).data); } catch (e) { toast.error(errMsg(e)); }
  };
  const fromResult = async () => { try { done((await http.post("/partb/imports/from-result", { version: Number(ver), mode })).data); } catch (e) { toast.error(errMsg(e)); } };
  const commit = async () => { try { await http.post(`/partb/imports/${open.id}/commit`); toast.success("Rows inserted"); load(); show(open.id); } catch (e) { toast.error(errMsg(e)); } };
  const rollback = async () => { try { await http.post(`/partb/imports/${rb.id}/rollback`, { reason }); toast.success("Batch rolled back"); setRb(null); setReason(""); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div data-testid="partb-imports-page">
      <PageHeader eyebrow="Part B transition" title="Merit & waitlist imports" description="Columns: cycle_code, program_code, application_reference, outcome (selected/waitlisted/rejected), merit_rank, waitlist_rank, choice_position, list_version. Validate first, or insert directly (invalid rows are quarantined)." />
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card><p className="mb-3 font-semibold">Upload Excel / CSV</p>
          <div className="flex flex-wrap gap-2">
            <Input type="file" accept=".csv,.xlsx" data-testid="import-file-input" onChange={(e) => setFile(e.target.files[0])} className="max-w-xs" />
            <select aria-label="Mode" data-testid="import-mode-select" className={sel} value={mode} onChange={(e) => setMode(e.target.value)}><option value="validate">Validate (two-step)</option><option value="insert">Insert directly</option></select>
            <Button data-testid="import-upload-button" onClick={upload} disabled={!file}><Upload className="mr-1.5 h-4 w-4" />Upload</Button>
          </div></Card>
        <Card><p className="mb-3 font-semibold">From the published result version</p>
          <div className="flex flex-wrap gap-2">
            <Input aria-label="Result version" data-testid="import-result-version-input" type="number" min={1} placeholder="Version" value={ver} onChange={(e) => setVer(e.target.value)} className="w-28" />
            <Button variant="outline" data-testid="import-from-result-button" onClick={fromResult} disabled={!ver}>Build list ({mode})</Button>
          </div></Card>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="imports-table">
          <TableHeader><TableRow>{["When", "Source", "Mode", "Status", "Rows", "Valid", "Inserted", "Errors", "By", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{rows.map((b) => (
            <TableRow key={b.id} data-testid={`import-row-${b.id}`}>
              <TableCell className="text-xs">{fmtIST(b.created_at)}</TableCell><TableCell className="text-sm">{b.filename}</TableCell><TableCell className="text-xs">{b.mode}</TableCell>
              <TableCell><StatusPill testId={`import-status-${b.id}`} status={TONE[b.status] || b.status} label={b.status.replace("_", " ")} /></TableCell>
              {[b.rows_total, b.rows_valid, b.inserted, b.error_count].map((n, i) => <TableCell key={i} className="tabular-nums">{n}</TableCell>)}
              <TableCell className="text-xs">{b.created_by}</TableCell>
              <TableCell className="flex gap-1"><Button size="sm" variant="outline" data-testid={`import-open-${b.id}`} onClick={() => show(b.id)}>Report</Button>
                {b.status === "inserted" && <Button size="sm" variant="ghost" data-testid={`import-rollback-${b.id}`} onClick={() => setRb(b)}><RotateCcw className="h-4 w-4" /></Button>}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </Card>
      {open && <Report b={open} onClose={() => setOpen(null)} onCommit={commit} />}
      <Dialog open={!!rb} onOpenChange={(o) => !o && setRb(null)}>
        <DialogContent data-testid="rollback-dialog"><DialogHeader><DialogTitle>Roll back {rb?.filename}?</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Removes this batch's eligibility rows. Blocked if any candidate from it already has an allotment.</p>
          <Input aria-label="Reason" data-testid="rollback-reason-input" placeholder="Reason (audited)" value={reason} onChange={(e) => setReason(e.target.value)} />
          <Button variant="destructive" data-testid="rollback-confirm-button" disabled={reason.trim().length < 5} onClick={rollback}>Roll back</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

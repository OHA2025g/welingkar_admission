import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtDate, fmtINR } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const BLANK = { code: "", name: "", status: "draft", application_open: "", application_close: "", part_b_open: "", part_b_close: "", admission_fee_due: "", application_fee_inr: 1500, admission_fee_inr: 0 };
const DATES = [["application_open", "Applications open"], ["application_close", "Applications close"], ["part_b_open", "Part B opens"], ["part_b_close", "Part B closes"], ["admission_fee_due", "Admission fee due"]];

const CycleDialog = ({ open, editing, onClose, onSaved }) => {
  const [f, setF] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setF(editing ? { ...BLANK, ...editing, part_b_open: editing.part_b_open || "", part_b_close: editing.part_b_close || "", admission_fee_due: editing.admission_fee_due || "" } : BLANK); }, [open, editing]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { code: f.code, name: f.name, status: f.status, application_open: f.application_open, application_close: f.application_close,
      part_b_open: f.part_b_open || null, part_b_close: f.part_b_close || null, admission_fee_due: f.admission_fee_due || null,
      application_fee_inr: Number(f.application_fee_inr), admission_fee_inr: Number(f.admission_fee_inr) };
    try {
      if (editing) await http.patch(`/cycles/${editing.id}`, { ...body, version: editing.version });
      else await http.post("/cycles", body);
      toast.success(editing ? "Cycle updated" : "Cycle created"); onSaved(); onClose();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="cycle-dialog" className="max-w-xl">
        <DialogHeader><DialogTitle>{editing ? `Edit cycle ${editing.code}` : "New admission cycle"}</DialogTitle></DialogHeader>
        <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="c-code">Code</Label><Input id="c-code" data-testid="cycle-code-input" value={f.code} onChange={set("code")} placeholder="2027-29" required /></div>
          <div className="space-y-1.5"><Label>Status</Label>
            <Select value={f.status} onValueChange={(v) => setF({ ...f, status: v })}>
              <SelectTrigger data-testid="cycle-status-select"><SelectValue /></SelectTrigger>
              <SelectContent>{["draft", "active", "closed", "archived"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="c-name">Name</Label><Input id="c-name" data-testid="cycle-name-input" value={f.name} onChange={set("name")} required /></div>
          {DATES.map(([k, l]) => (
            <div key={k} className="space-y-1.5"><Label htmlFor={`c-${k}`}>{l}</Label><Input id={`c-${k}`} data-testid={`cycle-${k}-input`} type="date" value={f[k]} onChange={set(k)} required={k.startsWith("application_")} /></div>
          ))}
          <div className="space-y-1.5"><Label htmlFor="c-fee">Application fee (INR)</Label><Input id="c-fee" data-testid="cycle-fee-input" type="number" min="0" value={f.application_fee_inr} onChange={set("application_fee_inr")} /></div>
          <div className="space-y-1.5"><Label htmlFor="c-afee">Admission fee (INR)</Label><Input id="c-afee" data-testid="cycle-admission-fee-input" type="number" min="0" value={f.admission_fee_inr} onChange={set("admission_fee_inr")} /></div>
          <Button data-testid="cycle-save-button" type="submit" className="sm:col-span-2" disabled={busy}>{editing ? "Save changes" : "Create cycle"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default function CyclesPage() {
  const { user } = useAuth();
  const write = can(user, "cycles.write");
  const [rows, setRows] = useState([]);
  const [dialog, setDialog] = useState(null);
  const load = useCallback(() => http.get("/cycles").then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="cycles-page">
      <PageHeader eyebrow="Configuration" title="Admission cycles" description="Only one cycle can be active. Edits use version checks and are recorded in the audit log."
        actions={write && <Button data-testid="add-cycle-button" onClick={() => setDialog({})}><Plus className="mr-1.5 h-4 w-4" />New cycle</Button>} />
      <Card className="overflow-x-auto p-0">
        <Table data-testid="cycles-table">
          <TableHeader><TableRow>{["Code", "Name", "Status", "Applications", "Part B", "Fee due", "Application fee", "Ver.", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.id} data-testid={`cycle-row-${c.code}`}>
                <TableCell className="font-mono text-sm font-semibold">{c.code}</TableCell>
                <TableCell>{c.name}</TableCell>
                <TableCell><StatusPill testId={`cycle-status-${c.code}`} status={c.status} /></TableCell>
                <TableCell className="text-sm">{fmtDate(c.application_open)} – {fmtDate(c.application_close)}</TableCell>
                <TableCell className="text-sm">{c.part_b_open ? `${fmtDate(c.part_b_open)} – ${fmtDate(c.part_b_close)}` : "—"}</TableCell>
                <TableCell className="text-sm">{c.admission_fee_due ? fmtDate(c.admission_fee_due) : "—"}</TableCell>
                <TableCell className="tabular-nums">{fmtINR(c.application_fee_inr)}</TableCell>
                <TableCell className="text-xs text-muted-foreground">v{c.version}</TableCell>
                <TableCell>{write && <Button data-testid={`edit-cycle-${c.code}`} variant="ghost" size="sm" onClick={() => setDialog({ editing: c })}><Pencil className="mr-1 h-3.5 w-3.5" />Edit</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <CycleDialog open={!!dialog} editing={dialog?.editing} onClose={() => setDialog(null)} onSaved={load} />
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const STAGES = ["application", "essay", "ga", "pi", "part_b"];
const BLANK = { code: "", name: "", route: "PGDM", campus: "Mumbai", duration_months: 24, seat_capacity: 60, tfw_seats: 0, stages: ["application"], status: "active" };

const ProgramDialog = ({ open, editing, cycleId, onClose, onSaved }) => {
  const [f, setF] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setF(editing ? { ...editing } : BLANK); }, [open, editing]);
  const set = (k, num) => (e) => setF({ ...f, [k]: num ? Number(e.target.value) : e.target.value });
  const toggle = (s) => setF({ ...f, stages: f.stages.includes(s) ? f.stages.filter((x) => x !== s) : [...f.stages, s] });
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    const body = { cycle_id: cycleId, code: f.code.toUpperCase(), name: f.name, route: f.route, campus: f.campus, duration_months: f.duration_months,
      seat_capacity: f.seat_capacity, tfw_seats: f.tfw_seats, stages: f.stages, status: f.status };
    try {
      if (editing) await http.patch(`/programs/${editing.id}`, { ...body, version: editing.version });
      else await http.post("/programs", body);
      toast.success(editing ? "Program updated" : "Program created"); onSaved(); onClose();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="program-dialog" className="max-w-xl">
        <DialogHeader><DialogTitle>{editing ? `Edit ${editing.code}` : "New program / route"}</DialogTitle></DialogHeader>
        <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="p-code">Code</Label><Input id="p-code" data-testid="program-code-input" value={f.code} onChange={set("code")} placeholder="PGDM-XYZ" required /></div>
          <div className="space-y-1.5"><Label htmlFor="p-route">Route</Label><Input id="p-route" data-testid="program-route-input" value={f.route} onChange={set("route")} required /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="p-name">Name</Label><Input id="p-name" data-testid="program-name-input" value={f.name} onChange={set("name")} required /></div>
          <div className="space-y-1.5"><Label htmlFor="p-campus">Campus</Label><Input id="p-campus" data-testid="program-campus-input" value={f.campus} onChange={set("campus")} required /></div>
          <div className="space-y-1.5"><Label htmlFor="p-dur">Duration (months)</Label><Input id="p-dur" type="number" min="1" value={f.duration_months} onChange={set("duration_months", true)} /></div>
          <div className="space-y-1.5"><Label htmlFor="p-seats">Seat capacity</Label><Input id="p-seats" data-testid="program-seats-input" type="number" min="0" value={f.seat_capacity} onChange={set("seat_capacity", true)} /></div>
          <div className="space-y-1.5"><Label htmlFor="p-tfw">TFW seats</Label><Input id="p-tfw" data-testid="program-tfw-input" type="number" min="0" value={f.tfw_seats} onChange={set("tfw_seats", true)} /></div>
          <fieldset className="space-y-2 sm:col-span-2"><legend className="text-sm font-medium">Applicable stages</legend>
            <div className="flex flex-wrap gap-4">{STAGES.map((s) => (
              <label key={s} className="flex items-center gap-2 text-sm"><Checkbox data-testid={`program-stage-${s}`} checked={f.stages.includes(s)} onCheckedChange={() => toggle(s)} />{s.replace("_", " ").toUpperCase()}</label>
            ))}</div></fieldset>
          <div className="space-y-1.5"><Label>Status</Label>
            <Select value={f.status} onValueChange={(v) => setF({ ...f, status: v })}>
              <SelectTrigger data-testid="program-status-select"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="inactive">Inactive</SelectItem></SelectContent>
            </Select></div>
          <Button data-testid="program-save-button" type="submit" className="self-end" disabled={busy}>{editing ? "Save changes" : "Create program"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default function ProgramsPage() {
  const { user } = useAuth();
  const write = can(user, "programs.write");
  const [cycles, setCycles] = useState([]);
  const [cycleId, setCycleId] = useState("");
  const [rows, setRows] = useState([]);
  const [dialog, setDialog] = useState(null);
  useEffect(() => { http.get("/cycles").then((r) => { setCycles(r.data); setCycleId((r.data.find((c) => c.status === "active") || r.data[0])?.id || ""); }); }, []);
  const load = useCallback(() => { if (cycleId) http.get("/programs", { params: { cycle_id: cycleId } }).then((r) => setRows(r.data)); }, [cycleId]);
  useEffect(() => { load(); }, [load]);
  const active = rows.filter((p) => p.status === "active");
  const seats = active.reduce((a, p) => a + p.seat_capacity, 0);
  const tfw = active.reduce((a, p) => a + p.tfw_seats, 0);

  return (
    <div data-testid="programs-page">
      <PageHeader eyebrow="Configuration" title="Programs, routes & seats" description="Seat capacity is the basis for allotment in Part B. TFW seats cannot exceed capacity."
        actions={write && cycleId && <Button data-testid="add-program-button" onClick={() => setDialog({})}><Plus className="mr-1.5 h-4 w-4" />New program</Button>} />
      <div className="mb-6 flex flex-wrap items-center gap-6">
        <Select value={cycleId} onValueChange={setCycleId}>
          <SelectTrigger data-testid="programs-cycle-select" className="w-64"><SelectValue placeholder="Cycle" /></SelectTrigger>
          <SelectContent>{cycles.map((c) => <SelectItem key={c.id} value={c.id}>{c.code} · {c.status}</SelectItem>)}</SelectContent>
        </Select>
        <p className="text-sm text-muted-foreground"><b data-testid="programs-total-seats" className="text-foreground">{seats}</b> seats · <b className="text-foreground">{tfw}</b> TFW · {active.length} active programs</p>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="programs-table">
          <TableHeader><TableRow>{["Code", "Program", "Route", "Campus", "Seats", "TFW", "Stages", "Status", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((p) => (
              <TableRow key={p.id} data-testid={`program-row-${p.code}`}>
                <TableCell className="font-mono text-xs font-semibold">{p.code}</TableCell>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell className="text-sm">{p.route}</TableCell>
                <TableCell className="text-sm">{p.campus}</TableCell>
                <TableCell data-testid={`program-seats-${p.code}`} className="tabular-nums">{p.seat_capacity}</TableCell>
                <TableCell className="tabular-nums">{p.tfw_seats}</TableCell>
                <TableCell className="text-xs text-muted-foreground">{p.stages.join(" · ")}</TableCell>
                <TableCell><StatusPill status={p.status} /></TableCell>
                <TableCell>{write && <Button data-testid={`edit-program-${p.code}`} variant="ghost" size="sm" onClick={() => setDialog({ editing: p })}><Pencil className="mr-1 h-3.5 w-3.5" />Edit</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <ProgramDialog open={!!dialog} editing={dialog?.editing} cycleId={cycleId} onClose={() => setDialog(null)} onSaved={load} />
    </div>
  );
}

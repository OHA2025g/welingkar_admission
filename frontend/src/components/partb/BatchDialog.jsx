import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { http, errMsg } from "@/lib/api";

const sel = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";

export const BatchDialog = ({ batch, onClose, onSaved }) => {
  const editing = !!batch.id;
  const [f, setF] = useState({ kind: batch.kind || "merit", name: batch.name || "", program_code: batch.program_code || "", start_date: batch.start_date || "", end_date: batch.end_date || "" });
  const [progs, setProgs] = useState([]);
  useEffect(() => { http.get("/programs").then((r) => setProgs(r.data)).catch(() => setProgs([])); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try {
      if (editing) await http.put(`/partb/batches/${batch.id}`, { name: f.name, start_date: f.start_date, end_date: f.end_date });
      else await http.post("/partb/batches", f);
      toast.success(editing ? "Batch updated" : "Batch created"); onSaved(); onClose();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="batch-dialog">
        <DialogHeader><DialogTitle>{editing ? "Edit batch" : "New merit / waitlist batch"}</DialogTitle></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="b-kind">Kind</Label><select id="b-kind" data-testid="batch-kind-select" className={sel} disabled={editing} value={f.kind} onChange={set("kind")}><option value="merit">Merit</option><option value="waitlist">Waiting list</option></select></div>
          <div className="space-y-1.5"><Label htmlFor="b-prog">Programme</Label><select id="b-prog" data-testid="batch-program-select" className={sel} disabled={editing} value={f.program_code} onChange={set("program_code")}>
            <option value="">Choose</option>{(Array.isArray(progs) ? progs : progs.items || []).map((p) => <option key={p.code} value={p.code}>{p.code} · {p.name}</option>)}</select></div>
          <div className="space-y-1.5 sm:col-span-2"><Label htmlFor="b-name">Name</Label><Input id="b-name" data-testid="batch-name-input" value={f.name} onChange={set("name")} /></div>
          <div className="space-y-1.5"><Label htmlFor="b-start">Start date</Label><Input id="b-start" type="date" data-testid="batch-start-input" value={f.start_date} onChange={set("start_date")} /></div>
          <div className="space-y-1.5"><Label htmlFor="b-end">End date</Label><Input id="b-end" type="date" data-testid="batch-end-input" value={f.end_date} onChange={set("end_date")} /></div>
        </div>
        <Button data-testid="batch-save-button" onClick={save} disabled={!f.name || !f.program_code || !f.start_date || !f.end_date}>Save</Button>
      </DialogContent>
    </Dialog>
  );
};

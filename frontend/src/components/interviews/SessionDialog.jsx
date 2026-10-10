import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { http, errMsg } from "@/lib/api";

const sel = "h-9 w-full rounded-md border border-input bg-background px-3 text-sm";
const EMPTY = { type: "PI", room_id: "", date: "", start: "10:00", end: "12:00", capacity: 4, panelist_ids: [] };

export const PanelistPicker = ({ panelists, value, onChange }) => (
  <div className="grid gap-2 sm:grid-cols-2">
    {panelists.map((p) => (
      <label key={p.id} className="flex items-center gap-2 text-sm">
        <Checkbox data-testid={`panelist-check-${p.id}`} checked={value.includes(p.id)}
          onCheckedChange={(v) => onChange(v ? [...value, p.id] : value.filter((x) => x !== p.id))} />{p.name}
      </label>
    ))}
  </div>
);

export const SessionDialog = ({ open, onOpenChange, locations, panelists, onCreated }) => {
  const [f, setF] = useState(EMPTY);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    try { await http.post("/interviews/sessions", { ...f, capacity: Number(f.capacity) }); toast.success("Session created"); setF(EMPTY); onCreated(); onOpenChange(false); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="session-dialog" className="max-w-xl">
        <DialogHeader><DialogTitle>New interview session</DialogTitle></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5"><Label htmlFor="s-type">Type</Label>
            <select id="s-type" data-testid="session-type-select" className={sel} value={f.type} onChange={set("type")}><option value="GA">GA / GD</option><option value="PI">PI</option></select></div>
          <div className="space-y-1.5"><Label htmlFor="s-room">Room</Label>
            <select id="s-room" data-testid="session-room-select" className={sel} value={f.room_id} onChange={set("room_id")}>
              <option value="">Choose a room</option>
              {locations.map((l) => <optgroup key={l.id} label={l.name}>{l.rooms.map((r) => <option key={r.id} value={r.id}>{r.name} (cap {r.capacity})</option>)}</optgroup>)}
            </select></div>
          <div className="space-y-1.5"><Label htmlFor="s-date">Date</Label><Input id="s-date" data-testid="session-date-input" type="date" value={f.date} onChange={set("date")} /></div>
          <div className="space-y-1.5"><Label htmlFor="s-cap">Capacity</Label><Input id="s-cap" data-testid="session-capacity-input" type="number" min={1} value={f.capacity} onChange={set("capacity")} /></div>
          <div className="space-y-1.5"><Label htmlFor="s-start">Start (IST)</Label><Input id="s-start" data-testid="session-start-input" type="time" value={f.start} onChange={set("start")} /></div>
          <div className="space-y-1.5"><Label htmlFor="s-end">End (IST)</Label><Input id="s-end" data-testid="session-end-input" type="time" value={f.end} onChange={set("end")} /></div>
        </div>
        <div className="space-y-2"><Label>Panelists</Label><PanelistPicker panelists={panelists} value={f.panelist_ids} onChange={(v) => setF({ ...f, panelist_ids: v })} /></div>
        <Button data-testid="session-save-button" onClick={save} disabled={!f.room_id || !f.date}>Create session</Button>
      </DialogContent>
    </Dialog>
  );
};

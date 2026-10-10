import { useState } from "react";
import { Loader2, Shuffle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { http, errMsg } from "@/lib/api";
import { Card } from "@/components/portal/ui";

const sel = "h-9 rounded-md border border-input bg-background px-3 text-sm";

export const AllocationTab = ({ locations, reload }) => {
  const [f, setF] = useState({ type: "GA", location_id: "" });
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { const { data } = await http.post("/interviews/allocate", { type: f.type, location_id: f.location_id || null }); setRes(data); toast.success(`${data.allocated.length} candidates allocated`); reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-6">
      <Card>
        <p className="font-semibold">Automatic allocation</p>
        <p className="mt-1 text-sm text-muted-foreground">Places submitted candidates whose preferences need this stage into upcoming sessions with free capacity, preferring their home city. Already-booked candidates are skipped.</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <select aria-label="Session type" data-testid="allocate-type-select" className={sel} value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}><option value="GA">GA</option><option value="PI">PI</option></select>
          <select aria-label="Location" data-testid="allocate-location-select" className={sel} value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}>
            <option value="">All locations</option>{locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
          <Button data-testid="allocate-run-button" onClick={run} disabled={busy}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Shuffle className="mr-1.5 h-4 w-4" />Run allocation</>}</Button>
        </div>
      </Card>
      {res && (
        <div data-testid="allocation-result" className="grid gap-4 lg:grid-cols-2">
          <Card><p className="font-semibold">Allocated ({res.allocated.length})</p>
            <ul className="mt-2 space-y-1 text-sm">{res.allocated.map((a) => <li key={a.application_ref}>{a.name} <span className="font-mono text-xs text-muted-foreground">{a.application_ref}</span> → {a.session}</li>)}</ul></Card>
          <Card><p className="font-semibold">Not placed ({res.unallocated.length})</p>
            <ul className="mt-2 space-y-1 text-sm">{res.unallocated.map((a) => <li key={a.application_ref}>{a.name} <span className="font-mono text-xs text-muted-foreground">{a.application_ref}</span></li>)}</ul>
            {res.unallocated.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Add sessions or capacity, then run again.</p>}</Card>
        </div>
      )}
    </div>
  );
};

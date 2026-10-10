import { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { http, errMsg } from "@/lib/api";
import { Card } from "@/components/portal/ui";

const RoomForm = ({ loc, reload }) => {
  const [r, setR] = useState({ name: "", capacity: 6 });
  const add = async () => {
    try { await http.post(`/interviews/locations/${loc.id}/rooms`, { ...r, capacity: Number(r.capacity) }); toast.success("Room added"); setR({ name: "", capacity: 6 }); reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      <Input aria-label="Room name" data-testid={`room-name-input-${loc.id}`} placeholder="Room name" value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} className="w-44" />
      <Input aria-label="Room capacity" data-testid={`room-capacity-input-${loc.id}`} type="number" min={1} value={r.capacity} onChange={(e) => setR({ ...r, capacity: e.target.value })} className="w-24" />
      <Button size="sm" variant="outline" data-testid={`room-add-button-${loc.id}`} onClick={add} disabled={r.name.trim().length < 2}><Plus className="mr-1 h-4 w-4" />Add room</Button>
    </div>
  );
};

export const LocationsTab = ({ locations, reload }) => {
  const [f, setF] = useState({ name: "", city: "", address: "" });
  const create = async () => {
    try { await http.post("/interviews/locations", f); toast.success("Location created"); setF({ name: "", city: "", address: "" }); reload(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="space-y-6">
      <Card>
        <p className="mb-3 font-semibold">New location</p>
        <div className="flex flex-col gap-2 md:flex-row">
          <Input aria-label="Location name" data-testid="location-name-input" placeholder="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <Input aria-label="City" data-testid="location-city-input" placeholder="City" value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} className="md:w-48" />
          <Input aria-label="Address" data-testid="location-address-input" placeholder="Address" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} />
          <Button data-testid="location-create-button" onClick={create} disabled={f.name.trim().length < 3 || f.city.trim().length < 2}>Create</Button>
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        {locations.map((l) => (
          <Card key={l.id} testId={`location-card-${l.id}`}>
            <p className="font-semibold">{l.name}</p>
            <p className="text-sm text-muted-foreground">{l.city} · {l.address}</p>
            <ul className="mt-3 divide-y divide-border text-sm">
              {l.rooms.map((r) => <li key={r.id} className="flex justify-between py-2"><span>{r.name}</span><span className="tabular-nums text-muted-foreground">capacity {r.capacity}</span></li>)}
              {l.rooms.length === 0 && <li className="py-2 text-muted-foreground">No rooms yet.</li>}
            </ul>
            <RoomForm loc={l} reload={reload} />
          </Card>
        ))}
      </div>
    </div>
  );
};

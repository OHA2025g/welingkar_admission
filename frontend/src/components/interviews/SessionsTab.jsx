import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, Pill } from "@/components/portal/ui";
import { SessionDialog } from "@/components/interviews/SessionDialog";

export const TypePill = ({ type }) => <Pill tone={type === "GA" ? "bg-sky-50 text-sky-800 border-sky-200" : "bg-amber-50 text-amber-800 border-amber-200"}>{type}</Pill>;

export const SessionsTab = ({ sessions, locations, panelists, reload }) => {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState("all");
  const rows = sessions.filter((s) => type === "all" || s.type === type);
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <select aria-label="Filter by type" data-testid="sessions-type-filter" className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="all">All types</option><option value="GA">GA</option><option value="PI">PI</option>
        </select>
        <Button data-testid="session-new-button" onClick={() => setOpen(true)}><Plus className="mr-1.5 h-4 w-4" />New session</Button>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="sessions-table">
          <TableHeader><TableRow>{["Date", "Time (IST)", "Type", "Venue", "Booked", "Panelists", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.id} data-testid={`session-row-${s.id}`}>
                <TableCell className="font-mono text-xs">{s.date}</TableCell>
                <TableCell className="tabular-nums text-sm">{s.start}–{s.end}</TableCell>
                <TableCell><TypePill type={s.type} /></TableCell>
                <TableCell className="text-sm">{s.location}<p className="text-xs text-muted-foreground">{s.room}</p></TableCell>
                <TableCell data-testid={`session-booked-${s.id}`} className="tabular-nums text-sm">{s.booked}/{s.capacity}</TableCell>
                <TableCell className="text-sm">{s.panelists.map((p) => p.name).join(", ") || <span className="text-destructive">None</span>}</TableCell>
                <TableCell><Button asChild size="sm" variant="outline"><Link data-testid={`session-open-${s.id}`} to={`/staff/interviews/sessions/${s.id}`}>Open</Link></Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <SessionDialog open={open} onOpenChange={setOpen} locations={locations} panelists={panelists} onCreated={reload} />
    </div>
  );
};

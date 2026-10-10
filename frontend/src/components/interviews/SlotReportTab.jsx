import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, downloadFile } from "@/lib/api";
import { Card, StatusPill } from "@/components/portal/ui";

const Grid = ({ head, rows, testId }) => (
  <Card className="overflow-x-auto p-0">
    <Table data-testid={testId}>
      <TableHeader><TableRow>{head.map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
      <TableBody>{rows}</TableBody>
    </Table>
  </Card>
);

export const SlotReportTab = () => {
  const [type, setType] = useState("");
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/interviews/reports/slots", { params: type ? { type } : {} }).then((r) => setD(r.data)); }, [type]);
  const exp = async () => { try { await downloadFile("/interviews/reports/slots/export", "slot-report.xlsx", type ? { type } : {}); toast.success("Slot report downloaded"); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  return (
    <div className="space-y-6" data-testid="slot-report">
      <div className="flex flex-wrap justify-between gap-3">
        <select aria-label="Type" data-testid="slot-report-type-filter" className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">GA & PI</option><option value="GA">GA</option><option value="PI">PI</option>
        </select>
        <Button data-testid="slot-report-export-button" variant="outline" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Export Excel</Button>
      </div>
      <Grid testId="slot-report-sessions" head={["Date", "Time", "Type", "Venue", "Capacity", "Booked", "Available", "Present", "Absent"]}
        rows={d.sessions.map((s) => <TableRow key={s.id}><TableCell className="font-mono text-xs">{s.date}</TableCell><TableCell className="text-sm">{s.start}–{s.end}</TableCell><TableCell>{s.type}</TableCell>
          <TableCell className="text-sm">{s.location} · {s.room}</TableCell>{[s.capacity, s.booked, s.available, s.present, s.absent].map((n, i) => <TableCell key={i} className="tabular-nums">{n}</TableCell>)}</TableRow>)} />
      <p className="font-semibold">Bookings & reschedule history</p>
      <Grid testId="slot-report-bookings" head={["Candidate", "Type", "Current slot", "Venue", "Version", "Reschedules", "History"]}
        rows={d.bookings.map((b, i) => <TableRow key={i}><TableCell className="text-sm">{b.name}<p className="font-mono text-xs text-muted-foreground">{b.candidate_ref}</p></TableCell><TableCell>{b.type}</TableCell>
          <TableCell className="text-sm">{b.slot}</TableCell><TableCell className="text-sm">{b.location} · {b.room}</TableCell><TableCell>v{b.version}</TableCell><TableCell>{b.reschedules}</TableCell>
          <TableCell className="text-xs text-muted-foreground">{b.history.join(" | ")}</TableCell></TableRow>)} />
      <p className="font-semibold">Panelist attendance</p>
      <Grid testId="slot-report-panelists" head={["Date", "Slot", "Type", "Venue", "Panelist", "Attendance"]}
        rows={d.panelists.map((p, i) => <TableRow key={i}><TableCell className="font-mono text-xs">{p.date}</TableCell><TableCell>{p.slot}</TableCell><TableCell>{p.type}</TableCell>
          <TableCell className="text-sm">{p.location} · {p.room}</TableCell><TableCell className="text-sm">{p.panelist}</TableCell><TableCell><StatusPill status={p.attendance} /></TableCell></TableRow>)} />
    </div>
  );
};

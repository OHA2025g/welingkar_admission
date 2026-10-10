import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http } from "@/lib/api";
import { Card, Empty, PageHeader, StatusPill } from "@/components/portal/ui";
import { TypePill } from "@/components/interviews/SessionsTab";

export default function ScoringPage() {
  const [rows, setRows] = useState(null);
  useEffect(() => { http.get("/panel/sessions").then((r) => setRows(r.data)); }, []);
  if (!rows) return null;
  return (
    <div data-testid="scoring-page">
      <PageHeader eyebrow="Panelist" title="My assigned sessions" description="You only see sessions you are assigned to. Submitted scores are locked; corrections go through an administrator." />
      {rows.length === 0 ? <Empty text="No sessions assigned to you yet." /> : (
        <Card className="overflow-x-auto p-0">
          <Table data-testid="panel-sessions-table">
            <TableHeader><TableRow>{["Date", "Time (IST)", "Type", "Venue", "Candidates", "My submitted", "", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {rows.map((s) => (
                <TableRow key={s.id} data-testid={`panel-session-row-${s.id}`}>
                  <TableCell className="font-mono text-xs">{s.date}</TableCell>
                  <TableCell className="text-sm">{s.start}–{s.end}</TableCell>
                  <TableCell><TypePill type={s.type} /></TableCell>
                  <TableCell className="text-sm">{s.location}<p className="text-xs text-muted-foreground">{s.room}</p></TableCell>
                  <TableCell className="tabular-nums">{s.booked}</TableCell>
                  <TableCell className="tabular-nums">{s.submitted}</TableCell>
                  <TableCell><StatusPill status={s.phase === "past" ? "closed" : s.phase === "today" ? "active" : "draft"} label={s.phase} /></TableCell>
                  <TableCell><Button asChild size="sm" variant="outline"><Link data-testid={`panel-session-open-${s.id}`} to={`/staff/scoring/${s.id}`}>Open</Link></Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http } from "@/lib/api";
import { Card, PageHeader } from "@/components/portal/ui";

const LABELS = [["registered", "Registered"], ["verified", "Verified"], ["paid", "Fee paid"], ["draft", "Drafts"], ["submitted", "Submitted"],
  ["declarations", "Declarations"], ["essays", "Essays submitted"], ["confirmed", "Data confirmed"]];

export default function PartADashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/admin/part-a/dashboard").then((r) => setD(r.data)); }, []);
  if (!d) return (
    <div data-testid="part-a-dashboard">
      <PageHeader eyebrow="Part A" title="Operational dashboard" description="Loading live counts…" />
    </div>
  );
  const max = Math.max(1, ...d.first_preferences.map((x) => x.count));
  return (
    <div data-testid="part-a-dashboard">
      <PageHeader eyebrow="Part A" title="Operational dashboard" description="Live counts across registration, payment, submission and post-submission steps." />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {LABELS.map(([k, l]) => (
          <Card key={k} testId={`part-a-count-${k}`} className="p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{l}</p>
            <p className="mt-2 font-['Outfit'] text-3xl font-bold tabular-nums">{d.counts[k]}</p>
          </Card>
        ))}
      </div>
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card className="overflow-x-auto p-0">
          <p className="px-6 pt-5 font-semibold">State-wise paid / unpaid</p>
          <Table data-testid="part-a-state-table">
            <TableHeader><TableRow>{["State", "Registered", "Paid", "Unpaid", "Submitted"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>{d.by_state.map((s) => <TableRow key={s.state}><TableCell>{s.state}</TableCell><TableCell>{s.registered}</TableCell><TableCell>{s.paid}</TableCell><TableCell>{s.unpaid}</TableCell><TableCell>{s.submitted}</TableCell></TableRow>)}</TableBody>
          </Table>
        </Card>
        <Card testId="part-a-preferences">
          <p className="mb-4 font-semibold">First-preference demand</p>
          <ul className="space-y-3">
            {d.first_preferences.map((p) => (
              <li key={p.program} className="text-sm">
                <div className="flex justify-between"><span>{p.program}</span><span className="tabular-nums">{p.count}</span></div>
                <div className="mt-1 h-2 rounded-full bg-secondary"><div className="h-2 rounded-full bg-primary" style={{ width: `${(100 * p.count) / max}%` }} /></div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { ConsentCard } from "@/components/partb/ConsentCard";
import { DocumentsPanel } from "@/components/partb/DocumentsPanel";
import { AllotmentCard, BettermentCard, NotificationsCard } from "@/components/partb/AllotmentCard";

const OUT = { selected: "active", waitlisted: "draft", rejected: "denied" };

export default function PartBPage() {
  const [d, setD] = useState(null);
  const [notes, setNotes] = useState([]);
  const load = useCallback(() => {
    http.get("/candidate/partb").then((r) => setD(r.data));
    http.get("/candidate/notifications").then((r) => setNotes(r.data.items));
  }, []);
  useEffect(() => { load(); }, [load]);
  const readAll = () => http.post("/candidate/notifications/read-all").then((r) => setNotes(r.data.items));
  if (!d) return null;
  if (!d.eligible) return (
    <div data-testid="partb-page"><PageHeader eyebrow="Part B" title="Counselling & allotment" />
      <Card testId="partb-ineligible"><p className="text-sm">{d.reason}</p></Card>
      <div className="mt-6"><NotificationsCard items={notes} onRead={readAll} /></div></div>
  );
  return (
    <div data-testid="partb-page">
      <PageHeader eyebrow="Part B" title="Counselling, documents & allotment" description={`${d.profile.name} · ${d.profile.candidate_ref} · ${d.profile.application_ref} · ${d.profile.category || ""}`} />
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Card className="overflow-x-auto p-0">
            <Table data-testid="partb-courses-table">
              <TableHeader><TableRow>{["Choice", "Programme", "Outcome", "Merit no.", "Waitlist no."].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
              <TableBody>{d.courses.map((c) => (
                <TableRow key={c.program_code} data-testid={`partb-course-${c.program_code}`}>
                  <TableCell>{c.choice_position ?? "—"}</TableCell><TableCell className="font-medium">{c.program_name}</TableCell>
                  <TableCell><StatusPill status={OUT[c.outcome]} label={c.outcome} /></TableCell>
                  <TableCell className="tabular-nums">{c.merit_rank ?? "—"}</TableCell><TableCell className="tabular-nums">{c.waitlist_rank ?? "—"}</TableCell>
                </TableRow>))}</TableBody>
            </Table>
          </Card>
          <ConsentCard data={d} onSaved={load} />
          <DocumentsPanel key={`i-${d.consent?.version}`} stage="initial" />
          <DocumentsPanel key={`a-${d.allotment?.id}-${d.allotment?.status}`} stage="admission" />
        </div>
        <div className="space-y-6">
          <AllotmentCard a={d.allotment} />
          <BettermentCard offers={d.betterment_offers} onDone={load} />
          <NotificationsCard items={notes} onRead={readAll} />
        </div>
      </div>
    </div>
  );
}

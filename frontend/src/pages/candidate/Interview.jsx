import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, Download, MapPin } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, downloadFile } from "@/lib/api";
import { Card, Empty, PageHeader, StatusPill } from "@/components/portal/ui";

const BookingCard = ({ b }) => (
  <Card testId={`booking-card-${b.type}`}>
    <p className="text-xs font-semibold uppercase tracking-wider text-primary">{b.session.type_label}</p>
    <p data-testid={`booking-slot-${b.type}`} className="mt-2 flex items-center gap-2 text-lg font-semibold"><CalendarClock className="h-5 w-5" />{b.session.date} · {b.session.start}–{b.session.end} IST</p>
    <p data-testid={`booking-venue-${b.type}`} className="mt-1 flex items-start gap-2 text-sm text-muted-foreground"><MapPin className="mt-0.5 h-4 w-4" />{b.session.location}, {b.session.room}<br />{b.session.address}</p>
    <div className="mt-3 flex flex-wrap gap-2 text-xs"><StatusPill status="active" label={`booking v${b.version}`} />{b.reschedules > 0 && <StatusPill status="draft" label={`rescheduled ${b.reschedules}x`} />}{b.attendance && <StatusPill status={b.attendance} />}</div>
  </Card>
);

export default function InterviewPage() {
  const [d, setD] = useState(null);
  const [busy, setBusy] = useState(null);
  const load = useCallback(() => http.get("/candidate/interviews").then((r) => setD(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const pi = d?.bookings.find((b) => b.type === "PI");
  const choose = async (sid) => {
    setBusy(sid);
    try { const { data } = await http.post(`/candidate/interviews/pi/${pi ? "reschedule" : "book"}`, { session_id: sid }); setD(data); toast.success(pi ? "PI slot rescheduled. Download your new hall ticket." : "PI slot booked"); }
    catch (e) { toast.error(errMsg(e)); load(); } finally { setBusy(null); }
  };
  const ticket = async () => { try { const n = await downloadFile("/candidate/interviews/hall-ticket", "hall-ticket.pdf"); toast.success(`${n} downloaded`); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  const left = d.rules.reschedule_limit - (pi?.reschedules || 0);
  return (
    <div data-testid="candidate-interview-page">
      <PageHeader eyebrow="GA / PI" title="Interviews & hall ticket" description={`PI booking and rescheduling close ${d.rules.cutoff_hours} hours before a slot. You can reschedule up to ${d.rules.reschedule_limit} times.`}
        actions={pi && <Button data-testid="hall-ticket-download-button" onClick={ticket}><Download className="mr-1.5 h-4 w-4" />Hall ticket (v{pi.version})</Button>} />
      {d.reasons.length > 0 && <Card testId="interview-ineligible" className="mb-6 border-amber-200 bg-amber-50">
        <ul className="space-y-1 text-sm text-amber-900">{d.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        <Button asChild size="sm" variant="outline" className="mt-3"><Link to="/candidate/after-submission">Go to after-submission steps</Link></Button></Card>}
      <h2 className="mb-3 text-lg font-semibold">Your assigned interviews</h2>
      {d.bookings.length === 0 ? <Empty text="No GA or PI session assigned yet." /> : <div className="grid gap-4 md:grid-cols-2">{d.bookings.map((b) => <BookingCard key={b.id} b={b} />)}</div>}
      {d.eligible && <>
        <h2 className="mb-3 mt-10 text-lg font-semibold">{pi ? `Reschedule your PI (${left} left)` : "Book a PI slot"}</h2>
        <Card className="overflow-x-hidden p-0">
          <Table data-testid="pi-slots-table" className="table-fixed">
            <TableHeader><TableRow>{["Date", "Time (IST)", "Venue", "Seats left", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {d.pi_slots.length === 0 && <TableRow><TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">No PI slots published yet.</TableCell></TableRow>}
              {d.pi_slots.map((s) => {
                const mine = pi?.session_id === s.id;
                return (
                  <TableRow key={s.id} data-testid={`pi-slot-row-${s.id}`}>
                    <TableCell className="font-mono text-xs">{s.date}</TableCell><TableCell className="text-sm">{s.start}–{s.end}</TableCell>
                    <TableCell className="text-sm">{s.location}<p className="text-xs text-muted-foreground">{s.room}</p></TableCell>
                    <TableCell data-testid={`pi-slot-available-${s.id}`} className="tabular-nums">{s.available}</TableCell>
                    <TableCell>{mine ? <StatusPill status="active" label="your slot" /> :
                      <Button size="sm" className="min-h-11 w-full" data-testid={`pi-slot-${pi ? "reschedule" : "book"}-${s.id}`} disabled={!s.bookable || busy === s.id || (pi && left <= 0)} onClick={() => choose(s.id)}>
                        {!s.bookable ? (s.available ? "Closed" : "Full") : pi ? "Move here" : "Book"}</Button>}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      </>}
    </div>
  );
}

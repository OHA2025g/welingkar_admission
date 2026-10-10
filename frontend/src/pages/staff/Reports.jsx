import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, fmtIST, downloadFile } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/portal/ui";

const inr = (paise) => fmtINR((paise || 0) / 100);
const label = (value) => String(value || "—").replace(/_/g, " ");

const Grid = ({ testId, head, rows, render }) => (
  <Card className="overflow-x-auto p-0">
    <Table data-testid={testId}>
      <TableHeader><TableRow>{head.map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
      <TableBody>
        {rows.map(render)}
        {!rows.length && <TableRow><TableCell colSpan={head.length}><Empty text="Nothing in this table yet. Counts appear after candidates register, pay, or cancel." /></TableCell></TableRow>}
      </TableBody>
    </Table>
  </Card>
);

export default function ReportsPage() {
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [people, setPeople] = useState(null);
  useEffect(() => {
    http.get("/reports/detailed").then((r) => setReport(r.data)).catch((e) => setError(errMsg(e)));
  }, []);
  const openPeople = (slice, key) => {
    setPeople({ slice, key, rows: [], masked: false, loading: true });
    http.get("/reports/people", { params: { slice, key } })
      .then((r) => setPeople({ ...r.data, loading: false }))
      .catch((e) => setPeople({ slice, key, rows: [], masked: false, loading: false, error: errMsg(e) }));
  };
  const exp = async () => {
    try { await downloadFile("/reports/detailed/export", "weschool-reports.xlsx"); toast.success("Report downloaded"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (error) return <Empty testId="reports-error" text={`Reports could not be loaded. ${error} Refresh the page. If the message mentions the gateway, confirm Stripe is reachable and try again.`} />;
  if (!report) return (
    <div data-testid="reports-page">
      <PageHeader eyebrow="Reports" title="Detailed reports" description="Loading the latest counts…" />
    </div>
  );
  const fin = report.finance;
  const t = fin.totals;
  return (
    <div data-testid="reports-page" className="space-y-8">
      <PageHeader eyebrow={`Reports · ${report.cycle_code || "No active cycle"}`} title="Detailed reports"
        description={`Counts for admissions, seats, collections, cancellations, and interviews. Generated ${fmtIST(report.generated_at)}.`}
        actions={<Button variant="outline" data-testid="reports-download" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Download Excel</Button>} />

      <section>
        <h2 className="mb-3 text-lg font-semibold">Admissions funnel</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          {report.admissions.funnel.map((step) => (
            <Card key={step.key} testId={`reports-funnel-${step.key}`} className="p-4">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{step.label}</p>
              <p className="mt-1 font-['Outfit'] text-2xl font-bold tabular-nums">{step.count}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">Candidates by state</h2>
          <Grid testId="reports-state-table" head={["State", "Registered", "Verified", "Fee paid", "Submitted"]} rows={report.admissions.by_state}
            render={(row) => <TableRow key={row.state}><TableCell><button type="button" className="font-medium text-primary underline" data-testid={`reports-state-${row.state}`} onClick={() => openPeople("state", row.state)}>{row.state}</button></TableCell><TableCell className="tabular-nums">{row.registered}</TableCell><TableCell className="tabular-nums">{row.verified}</TableCell><TableCell className="tabular-nums">{row.fee_paid}</TableCell><TableCell className="tabular-nums">{row.submitted}</TableCell></TableRow>} />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">First-preference demand</h2>
          <Grid testId="reports-preference-table" head={["Programme", "Name", "Count"]} rows={report.admissions.first_preferences}
            render={(row) => <TableRow key={row.program_code}><TableCell><button type="button" className="font-mono text-xs text-primary underline" data-testid={`reports-programme-${row.program_code}`} onClick={() => openPeople("programme", row.program_code)}>{row.program_code}</button></TableCell><TableCell>{row.program_name}</TableCell><TableCell className="tabular-nums">{row.count}</TableCell></TableRow>} />
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Seats</h2>
        <Grid testId="reports-seats-table" head={["Programme", "Capacity", "Filled", "Vacant", "Allotted", "Provisional", "On hold", "Cancelled", "Reconciled"]} rows={report.seats}
          render={(row) => (
            <TableRow key={row.program_code} data-testid={`reports-seat-${row.program_code}`}>
              <TableCell><span className="font-mono text-xs">{row.program_code}</span><div className="text-xs text-muted-foreground">{row.program_name}</div></TableCell>
              <TableCell className="tabular-nums">{row.capacity}</TableCell>
              <TableCell className="tabular-nums">{row.filled}</TableCell>
              <TableCell className="tabular-nums">{row.vacant}</TableCell>
              <TableCell className="tabular-nums">{row.allotted}</TableCell>
              <TableCell className="tabular-nums">{row.provisional}</TableCell>
              <TableCell className="tabular-nums">{row.on_hold}</TableCell>
              <TableCell className="tabular-nums">{row.cancelled}</TableCell>
              <TableCell>{row.reconciled ? "Yes" : "No"}</TableCell>
            </TableRow>
          )} />
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Collections and refunds</h2>
        <Grid testId="reports-finance-table" head={["Programme", "Collections", "Collected", "Refunds", "Refunded"]} rows={fin.by_programme}
          render={(row) => (
            <TableRow key={row.program_code}>
              <TableCell><span className="font-mono text-xs">{row.program_code}</span><div className="text-xs text-muted-foreground">{row.program_name}</div></TableCell>
              <TableCell className="tabular-nums">{row.collected_count}</TableCell>
              <TableCell className="tabular-nums">{inr(row.collected_paise)}</TableCell>
              <TableCell className="tabular-nums">{row.refunded_count}</TableCell>
              <TableCell className="tabular-nums">{inr(row.refunded_paise)}</TableCell>
            </TableRow>
          )} />
        <p data-testid="reports-finance-total" className="mt-3 text-sm font-semibold">
          Total {t.collected_count} collections · {inr(t.collected_paise)} · {t.refunded_count} refunds · {inr(t.refunded_paise)}
        </p>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">Payments by status</h2>
          <Grid testId="reports-payment-status" head={["Status", "Count", "Amount"]} rows={fin.payments_by_status}
            render={(row) => <TableRow key={row.status}><TableCell className="capitalize">{label(row.status)}</TableCell><TableCell className="tabular-nums">{row.count}</TableCell><TableCell className="tabular-nums">{inr(row.amount_paise)}</TableCell></TableRow>} />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">Cancellations</h2>
          <Grid testId="reports-cancellations" head={["Status", "Count", "Quoted refund"]} rows={fin.cancellations}
            render={(row) => <TableRow key={row.status}><TableCell><button type="button" className="capitalize text-primary underline" data-testid={`reports-cancellation-${row.status}`} onClick={() => openPeople("cancellation", row.status)}>{label(row.status)}</button></TableCell><TableCell className="tabular-nums">{row.count}</TableCell><TableCell className="tabular-nums">{inr(row.refund_paise)}</TableCell></TableRow>} />
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div>
          <h2 className="mb-3 text-lg font-semibold">Cancellations by programme</h2>
          <Grid testId="reports-cancellations-programme" head={["Programme", "Count", "Quoted refund"]} rows={fin.cancellations_by_programme}
            render={(row) => <TableRow key={row.program_code}><TableCell>{row.program_code}</TableCell><TableCell className="tabular-nums">{row.count}</TableCell><TableCell className="tabular-nums">{inr(row.refund_paise)}</TableCell></TableRow>} />
        </div>
        <div>
          <h2 className="mb-3 text-lg font-semibold">Interviews and results</h2>
          <Card testId="reports-interviews" className="space-y-4 text-sm">
            <p><span className="font-semibold">Sessions. </span>{report.interviews.sessions.map((r) => `${r.type} ${r.count}`).join(" · ") || "None"}</p>
            <p><span className="font-semibold">Bookings. </span>{report.interviews.bookings.map((r) => `${label(r.status)} ${r.count}`).join(" · ") || "None"}</p>
            <p><span className="font-semibold">Scores. </span>{report.interviews.scores.map((r) => `${label(r.status)} ${r.count}`).join(" · ") || "None"}</p>
            <p><span className="font-semibold">Result versions. </span>{report.interviews.results.map((r) => `v${r.version} ${label(r.status)}`).join(" · ") || "None"}</p>
          </Card>
        </div>
      </section>
      {people && (
        <section>
          <h2 className="mb-3 text-lg font-semibold">Candidates · {label(people.key)}</h2>
          {people.masked && <p className="mb-2 text-xs text-muted-foreground">Email addresses are masked for the Auditor.</p>}
          {people.error ? <Empty testId="reports-people-error" text={people.error} /> : people.loading ? <p className="text-sm text-muted-foreground">Loading candidates…</p> : (
            <Card className="overflow-x-auto p-0">
              <Table data-testid="reports-people">
                <TableHeader><TableRow>{["Name", "Email", "Candidate", "Application", "State"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
                <TableBody>
                  {people.rows.map((row) => (
                    <TableRow key={row.candidate_ref || row.email}><TableCell>{row.name}</TableCell><TableCell>{row.email}</TableCell><TableCell className="font-mono text-xs">{row.candidate_ref}</TableCell><TableCell className="font-mono text-xs">{row.application_ref || "—"}</TableCell><TableCell>{row.state}</TableCell></TableRow>
                  ))}
                  {!people.rows.length && <TableRow><TableCell colSpan={5}><Empty text="No candidates in this group." /></TableCell></TableRow>}
                </TableBody>
              </Table>
            </Card>
          )}
        </section>
      )}
    </div>
  );
}

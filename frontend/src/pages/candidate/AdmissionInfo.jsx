import { useEffect, useState } from "react";
import { ExternalLink, Newspaper, Award } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, fmtDate, fmtINR } from "@/lib/api";
import { Card, PageHeader } from "@/components/portal/ui";
import { ProgrammeCompare } from "@/components/portal/ProgrammeCompare";

export default function AdmissionInfo() {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/candidate/admission-info").then((r) => setD(r.data)); }, []);
  if (!d) return null;
  const c = d.cycle;
  return (
    <div data-testid="admission-info-page">
      <PageHeader eyebrow={`Cycle ${c.code}`} title="Admission information" description={c.name} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card testId="admission-dates-card">
          <h2 className="font-semibold">Important dates</h2>
          <dl className="mt-4 space-y-2 text-sm">
            {[["Applications open", c.application_open], ["Applications close", c.application_close], ["Part B opens", c.part_b_open], ["Part B closes", c.part_b_close]].map(([k, v]) => (
              <div key={k} className="flex justify-between"><dt className="text-muted-foreground">{k}</dt><dd className="font-medium">{fmtDate(v)}</dd></div>
            ))}
          </dl>
          <p className={`mt-4 text-xs font-semibold ${d.window_open ? "text-emerald-700" : "text-red-700"}`}>{d.window_open ? "Application window is open" : "Application window is closed"}</p>
        </Card>
        <Card testId="admission-fees-card">
          <h2 className="font-semibold">Fees</h2>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">Application fee</dt><dd data-testid="admission-app-fee" className="font-medium">{fmtINR(c.application_fee_inr)}</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Admission fee (Part B)</dt><dd className="font-medium">{fmtINR(c.admission_fee_inr)}</dd></div>
          </dl>
          <h3 className="mt-6 flex items-center gap-2 text-sm font-semibold"><Award className="h-4 w-4 text-[hsl(var(--gold))]" />Scholarships</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{d.scholarships.map((s) => <li key={s}>{s}</li>)}</ul>
        </Card>
        <Card testId="admission-news-card">
          <h2 className="flex items-center gap-2 font-semibold"><Newspaper className="h-4 w-4 text-primary" />News & resources</h2>
          <ul className="mt-4 space-y-2 text-sm">{d.news.map((n) => <li key={n}>{n}</li>)}</ul>
          <ul className="mt-4 space-y-2 text-sm">
            {d.resources.map((r) => <li key={r.title}><a className="inline-flex items-center gap-1 font-medium text-primary hover:underline" href={r.url} target="_blank" rel="noreferrer">{r.title}<ExternalLink className="h-3.5 w-3.5" /></a></li>)}
          </ul>
        </Card>
      </div>
      {d.tfw && (
        <Card testId="admission-tfw-card" className="mt-6">
          <h2 className="font-semibold">Tuition Fee Waiver (TFW)</h2>
          <p className="mt-2 text-sm text-muted-foreground">{d.tfw.enabled ? `Up to ${d.tfw.seat_share_percent}% of seats for eligible routes (${d.tfw.eligible_routes.join(", ")}). Family income limit ${fmtINR(d.tfw.family_income_limit_inr)}.` : "TFW is not offered this cycle."}</p>
          {d.tfw.enabled && <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">{d.tfw.required_documents.map((x) => <li key={x}>{x}</li>)}</ul>}
        </Card>
      )}
      <Card className="mt-6">
        <h2 className="font-semibold">Compare programmes</h2>
        <ProgrammeCompare programs={d.programs} applicationFee={c.application_fee_inr} admissionFee={c.admission_fee_inr} />
      </Card>
      <Card className="mt-6 overflow-x-auto p-0">
        <Table data-testid="admission-programs-table">
          <TableHeader><TableRow>{["Programme", "Route", "Campus", "Duration", "Seats", "TFW"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{d.programs.map((p) => (
            <TableRow key={p.code}><TableCell className="font-medium">{p.name}</TableCell><TableCell>{p.route}</TableCell><TableCell>{p.campus}</TableCell>
              <TableCell>{p.duration_months} months</TableCell><TableCell className="tabular-nums">{p.seat_capacity}</TableCell><TableCell className="tabular-nums">{p.tfw_seats}</TableCell></TableRow>
          ))}</TableBody>
        </Table>
      </Card>
    </div>
  );
}

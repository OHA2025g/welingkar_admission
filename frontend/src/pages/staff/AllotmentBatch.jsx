import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const TONE = { awaiting: "draft", allotted: "active", provisional: "approved", on_hold: "waitlisted", rejected: "denied", cancelled: "archived", superseded: "archived" };

export default function AllotmentBatch() {
  const { id } = useParams();
  const { user } = useAuth();
  const manage = can(user, "partb.manage");
  const [d, setD] = useState(null);
  const [filter, setFilter] = useState("");
  const load = useCallback(() => http.get(`/partb/batches/${id}/dashboard`).then((r) => setD(r.data)), [id]);
  useEffect(() => { load(); }, [load]);
  const act = async (r, status) => {
    try {
      if (status === "rejected") {
        const remarks = window.prompt("Reason for rejection") || "";
        if (remarks.length < 5) return;
        await http.post(`/partb/batches/${id}/reject`, { candidate_id: r.candidate_id, remarks });
      } else await http.post(`/partb/batches/${id}/allot`, { candidate_id: r.candidate_id, status });
      toast.success(`${r.name}: ${status.replace("_", " ")}`);
    } catch (e) { toast.error(errMsg(e)); }
    load();
  };
  if (!d) return null;
  const b = d.batch;
  const rows = d.rows.filter((r) => !filter || r.status === filter);
  return (
    <div data-testid="allotment-batch-page">
      <Link to="/staff/allotment" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />All batches</Link>
      <PageHeader eyebrow={`${b.kind} batch · ${b.open ? "open" : "closed"}`} title={b.name} description={`${b.program_code} · ${b.start_date} → ${b.end_date}`} />
      <div className="mb-6 flex flex-wrap gap-3">
        <Card testId="batch-vacancy" className="min-w-48"><p className="text-xs uppercase tracking-wider text-muted-foreground">Vacant seats</p>
          <p data-testid="batch-vacancy-count" className="mt-1 text-2xl font-semibold tabular-nums">{d.vacancy?.vacant} <span className="text-sm font-normal text-muted-foreground">/ {d.vacancy?.capacity}</span></p></Card>
        {Object.entries(d.counts).map(([k, n]) => (
          <button key={k} type="button" data-testid={`batch-count-${k}`} onClick={() => setFilter(filter === k ? "" : k)}
            className={`rounded-md border px-4 py-2 text-left transition-colors ${filter === k ? "border-primary bg-primary/5" : "border-border bg-card"}`}>
            <p className="text-xs capitalize text-muted-foreground">{k.replace("_", " ")}</p><p className="text-xl font-semibold tabular-nums">{n}</p></button>
        ))}
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="batch-dashboard-table">
          <TableHeader><TableRow>{["Rank", "Candidate", "Consent", "Documents", "Status", "Actions"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{rows.map((r) => {
            const awaiting = ["awaiting", "rejected", "cancelled", "superseded"].includes(r.status);
            return (
              <TableRow key={r.candidate_id} data-testid={`batch-row-${r.candidate_ref}`}>
                <TableCell className="tabular-nums">{r.rank}</TableCell>
                <TableCell className="text-sm">{r.name}<p className="font-mono text-xs text-muted-foreground">{r.application_ref}{r.holds_seat_in ? ` · holds ${r.holds_seat_in}` : ""}</p></TableCell>
                <TableCell className="text-xs"><StatusPill status={r.consent === "accept" ? "active" : r.consent === "decline" ? "denied" : "draft"} label={r.consent} />
                  {r.holds_seat_in && <p className="mt-1">betterment: {r.betterment_consent || "pending"}</p>}</TableCell>
                <TableCell><StatusPill testId={`batch-docs-${r.candidate_ref}`} status={r.docs === "verified" ? "active" : r.docs} label={r.docs.replace("_", " ")} /></TableCell>
                <TableCell><StatusPill testId={`batch-status-${r.candidate_ref}`} status={TONE[r.status]} label={r.status.replace("_", " ")} /></TableCell>
                <TableCell className="flex flex-wrap gap-1">{manage && b.open && awaiting && <>
                  <Button size="sm" data-testid={`allot-${r.candidate_ref}`} onClick={() => act(r, "allotted")}>Allot</Button>
                  <Button size="sm" variant="outline" data-testid={`provisional-${r.candidate_ref}`} onClick={() => act(r, "provisional")}>Provisional</Button>
                  <Button size="sm" variant="outline" data-testid={`hold-${r.candidate_ref}`} onClick={() => act(r, "on_hold")}>Hold</Button>
                  {r.status === "awaiting" && <Button size="sm" variant="ghost" data-testid={`reject-${r.candidate_ref}`} onClick={() => act(r, "rejected")}>Reject</Button>}</>}</TableCell>
              </TableRow>);
          })}</TableBody>
        </Table>
      </Card>
    </div>
  );
}

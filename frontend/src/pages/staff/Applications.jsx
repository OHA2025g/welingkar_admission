import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { INDIAN_STATES } from "@/lib/menu";
import { Card, Empty, PageHeader, StatusPill } from "@/components/portal/ui";

const F = ({ value, onChange, all, options, testId }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger data-testid={testId} className="sm:w-48"><SelectValue /></SelectTrigger>
    <SelectContent><SelectItem value="all">{all}</SelectItem>{options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
  </Select>
);

export default function ApplicationsPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [f, setF] = useState({ q: "", status: "all", fee: "all", state: "all" });
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v && v !== "all"));
  useEffect(() => {
    let live = true;
    setReady(false);
    http.get("/admin/applications", { params: { ...params, page, page_size: 50 } })
      .then((r) => {
        if (!live) return;
        const d = r.data;
        setRows(Array.isArray(d) ? d : d.rows);
        setTotal(Array.isArray(d) ? d.length : d.total);
        setError("");
      })
      .catch((e) => { if (live) setError(errMsg(e)); })
      .finally(() => { if (live) setReady(true); });
    return () => { live = false; };
  }, [JSON.stringify(params), page]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (v) => { setPage(1); setF({ ...f, [k]: v?.target ? v.target.value : v }); };
  const exportXlsx = async () => {
    try { await downloadFile("/admin/applications/export", "weschool-part-a.xlsx", params); toast.success("Export downloaded"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="applications-page">
      <PageHeader eyebrow="Part A" title="Candidates & applications" description="Read-only application view. Corrections to submitted forms are versioned and audited."
        actions={can(user, "applications.export") && <Button data-testid="applications-export-button" onClick={exportXlsx}><Download className="mr-1.5 h-4 w-4" />Export Excel</Button>} />
      <div className="mb-4 flex flex-col flex-wrap gap-3 sm:flex-row">
        <Input data-testid="applications-search-input" placeholder="Search name, email, ID or application ref" value={f.q} onChange={set("q")} className="sm:w-80" />
        <F testId="applications-status-filter" value={f.status} onChange={set("status")} all="All statuses" options={[["not_started", "Not started"], ["draft", "Draft"], ["submitted", "Submitted"]]} />
        <F testId="applications-fee-filter" value={f.fee} onChange={set("fee")} all="Paid & unpaid" options={[["paid", "Fee paid"], ["unpaid", "Fee unpaid"]]} />
        <F testId="applications-state-filter" value={f.state} onChange={set("state")} all="All states" options={INDIAN_STATES.map((s) => [s, s])} />
      </div>
      <p data-testid="applications-count" className="mb-2 text-sm text-muted-foreground">{total} candidates</p>
      {error && <Empty testId="applications-error" text={`Could not load candidates. ${error} Refresh the page and try again.`} />}
      <Card className="overflow-x-auto p-0">
        <Table data-testid="applications-table">
          <TableHeader><TableRow>{["Candidate", "Application", "State", "Identity", "Fee", "Status", "Sections", "1st preference", "Submitted"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.candidate_id} data-testid={`application-row-${r.candidate_ref}`}>
                <TableCell><p className="font-medium">{r.name}</p><p className="text-xs text-muted-foreground">{r.email} · {r.candidate_ref}</p></TableCell>
                <TableCell className="font-mono text-xs">{r.application_id ? <Link className="text-primary hover:underline" data-testid={`application-link-${r.candidate_ref}`} to={`/staff/applications/${r.application_id}`}>{r.application_ref}</Link> : "—"}</TableCell>
                <TableCell className="text-sm">{r.state}</TableCell>
                <TableCell><StatusPill status={r.identity_status} /></TableCell>
                <TableCell><StatusPill status={r.fee_paid ? "success" : "draft"} testId={`fee-${r.candidate_ref}`} /></TableCell>
                <TableCell><StatusPill status={r.application_status === "submitted" ? "active" : r.application_status === "draft" ? "draft" : "registered"} /></TableCell>
                <TableCell className="tabular-nums text-sm">{r.sections_complete}/7</TableCell>
                <TableCell className="text-sm">{r.first_preference || "—"}</TableCell>
                <TableCell className="text-xs">{fmtIST(r.submitted_at)}</TableCell>
              </TableRow>
            ))}
            {!ready && !error && <TableRow><TableCell colSpan={9}><Empty testId="applications-loading" text="Loading candidates…" /></TableCell></TableRow>}
            {ready && !rows.length && !error && <TableRow><TableCell colSpan={9}><Empty testId="applications-empty" text="No candidates match these filters. Clear a filter, or wait for a new registration." /></TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
      {total > 50 && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span>Page {page}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page * 50 >= total} onClick={() => setPage((n) => n + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, fmtIST } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

export default function CandidatesPage() {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  useEffect(() => {
    http.get("/admin/candidates", { params: { ...(status !== "all" ? { status } : {}), ...(q ? { q } : {}) } }).then((r) => setRows(r.data));
  }, [status, q]);
  return (
    <div data-testid="candidates-page">
      <PageHeader eyebrow="Candidates" title="Registered candidates" description="Read-only. Contact details are masked for roles without contact access." />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <Input data-testid="candidates-search-input" placeholder="Search name, email or ID" value={q} onChange={(e) => setQ(e.target.value)} className="sm:max-w-xs" />
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger data-testid="candidates-status-filter" className="sm:w-56"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {["verified", "partially_verified", "registered"].map((s) => <SelectItem key={s} value={s}>{s.replace("_", " ")}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="candidates-table">
          <TableHeader><TableRow>{["Candidate ID", "Name", "Email", "Mobile", "Location", "Identity", "Registered"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.id} data-testid={`candidate-row-${c.id}`}>
                <TableCell className="font-mono text-xs">{c.candidate_ref}</TableCell>
                <TableCell className="font-medium"><Link data-testid={`candidate-360-link-${c.id}`} to={`/staff/candidates/${c.id}`} className="text-primary hover:underline">{c.name}</Link></TableCell>
                <TableCell data-testid={`candidate-email-${c.id}`} className="text-sm">{c.email}</TableCell>
                <TableCell className="font-mono text-xs">{c.mobile}</TableCell>
                <TableCell className="text-sm">{c.city}, {c.state}</TableCell>
                <TableCell><StatusPill status={c.identity_status} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtIST(c.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

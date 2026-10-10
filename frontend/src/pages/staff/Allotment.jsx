import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Download, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, downloadFile, fmtIST } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { BatchDialog } from "@/components/partb/BatchDialog";

const TONE = { green: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-600" };

export const VacancyGrid = ({ rows }) => (
  <div data-testid="vacancy-grid" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    {rows.map((v) => (
      <Card key={v.program_code} testId={`vacancy-${v.program_code}`}>
        <div className="flex items-center justify-between"><p className="text-sm font-semibold">{v.program_code}</p><span className={`h-3 w-3 rounded-full ${TONE[v.tone]}`} /></div>
        <p className="text-xs text-muted-foreground">{v.program_name}</p>
        <p className="mt-3 text-2xl font-semibold tabular-nums" data-testid={`vacancy-count-${v.program_code}`}>{v.vacant}<span className="text-sm font-normal text-muted-foreground"> / {v.capacity} vacant</span></p>
        {!v.reconciled && <p className="text-xs text-destructive">Counter differs from seat-holding allotments</p>}
      </Card>
    ))}
  </div>
);

const BatchesTab = ({ batches, reload, manage }) => {
  const [dlg, setDlg] = useState(null);
  const del = async (b) => { if (!window.confirm(`Delete ${b.name}?`)) return; try { await http.delete(`/partb/batches/${b.id}`); toast.success("Batch deleted"); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <>
      {manage && <Button className="mb-4" data-testid="batch-new-button" onClick={() => setDlg({})}><Plus className="mr-1.5 h-4 w-4" />New batch</Button>}
      <Card className="overflow-x-auto p-0">
        <Table data-testid="batches-table">
          <TableHeader><TableRow>{["Batch", "Kind", "Programme", "Dates", "Open", "Active allotments", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{batches.map((b) => (
            <TableRow key={b.id} data-testid={`batch-row-${b.id}`}>
              <TableCell className="text-sm font-medium">{b.name}</TableCell><TableCell><StatusPill status={b.kind === "merit" ? "active" : "draft"} label={b.kind} /></TableCell>
              <TableCell className="text-sm">{b.program_name}</TableCell><TableCell className="font-mono text-xs">{b.start_date} → {b.end_date}</TableCell>
              <TableCell>{b.open ? "Yes" : "No"}</TableCell><TableCell className="tabular-nums">{b.active_allotments}</TableCell>
              <TableCell className="flex gap-1"><Button asChild size="sm" variant="outline"><Link data-testid={`batch-open-${b.id}`} to={`/staff/allotment/${b.id}`}>Dashboard</Link></Button>
                {manage && <><Button size="sm" variant="ghost" data-testid={`batch-edit-${b.id}`} onClick={() => setDlg(b)}>Edit</Button>
                  <Button size="sm" variant="ghost" data-testid={`batch-delete-${b.id}`} onClick={() => del(b)}><Trash2 className="h-4 w-4" /></Button></>}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </Card>
      {dlg && <BatchDialog batch={dlg} onClose={() => setDlg(null)} onSaved={reload} />}
    </>
  );
};

const HoldTab = ({ manage }) => {
  const [rows, setRows] = useState([]);
  const [ref, setRef] = useState({ application_ref: "", reason: "" });
  const load = useCallback(() => http.get("/partb/allotments", { params: { status: "on_hold" } }).then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  const dispose = async (a, to) => { const remarks = window.prompt(`Remarks for ${to}`) || ""; if (remarks.length < 3) return;
    try { await http.post(`/partb/allotments/${a.id}/disposition`, { to, remarks }); toast.success(`Now ${to}`); load(); } catch (e) { toast.error(errMsg(e)); } };
  const cancel = async () => { try { await http.post("/partb/allotments/cancel", ref); toast.success("Allotment cancelled; seat released"); setRef({ application_ref: "", reason: "" }); load(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-6">
      <Card className="overflow-x-auto p-0">
        <Table data-testid="onhold-table">
          <TableHeader><TableRow>{["Candidate", "Programme", "Since", "Disposition"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {rows.length === 0 && <TableRow><TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">No on-hold allotments.</TableCell></TableRow>}
            {rows.map((a) => (
              <TableRow key={a.id} data-testid={`onhold-row-${a.candidate_ref}`}>
                <TableCell className="text-sm">{a.name}<p className="font-mono text-xs text-muted-foreground">{a.application_ref}</p></TableCell>
                <TableCell>{a.program_code}</TableCell><TableCell className="text-xs">{fmtIST(a.updated_at)}</TableCell>
                <TableCell className="flex gap-1">{manage && ["allotted", "provisional", "cancelled"].map((to) =>
                  <Button key={to} size="sm" variant={to === "cancelled" ? "outline" : "default"} data-testid={`onhold-${to}-${a.candidate_ref}`} onClick={() => dispose(a, to)}>{to}</Button>)}</TableCell>
              </TableRow>))}
          </TableBody>
        </Table>
      </Card>
      {manage && <Card><p className="mb-3 font-semibold">Cancel by application reference (roll number)</p>
        <div className="flex flex-wrap gap-2">
          <Input aria-label="Application reference" data-testid="cancel-ref-input" placeholder="WS26-…" value={ref.application_ref} onChange={(e) => setRef({ ...ref, application_ref: e.target.value })} className="w-56" />
          <Input aria-label="Reason" data-testid="cancel-reason-input" placeholder="Reason" value={ref.reason} onChange={(e) => setRef({ ...ref, reason: e.target.value })} className="w-72" />
          <Button variant="destructive" data-testid="cancel-submit-button" disabled={!ref.application_ref || ref.reason.length < 5} onClick={cancel}>Cancel allotment</Button>
        </div></Card>}
    </div>
  );
};

const ReportsTab = () => {
  const [rows, setRows] = useState([]);
  useEffect(() => { http.get("/partb/reports/overview").then((r) => setRows(r.data)); }, []);
  const exp = () => downloadFile("/partb/reports/export", "partb.xlsx").then((n) => toast.success(`${n} downloaded`)).catch((e) => toast.error(errMsg(e)));
  const cols = ["capacity", "filled", "vacant", "eligible", "consented", "docs_verified", "allotted", "provisional", "on_hold", "cancelled", "superseded"];
  return (
    <div>
      <Button className="mb-4" variant="outline" data-testid="partb-export-button" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Export Excel</Button>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="partb-overview-table">
          <TableHeader><TableRow><TableHead>Programme</TableHead>{cols.map((c) => <TableHead key={c}>{c.replace("_", " ")}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{rows.map((r) => <TableRow key={r.program_code}><TableCell className="text-sm font-medium">{r.program_code}</TableCell>{cols.map((c) => <TableCell key={c} className="tabular-nums">{r[c]}</TableCell>)}</TableRow>)}</TableBody>
        </Table>
      </Card>
    </div>
  );
};

export default function AllotmentPage() {
  const { user } = useAuth();
  const manage = can(user, "partb.manage");
  const [batches, setBatches] = useState([]);
  const [vac, setVac] = useState([]);
  const load = useCallback(() => { http.get("/partb/batches").then((r) => setBatches(r.data)); http.get("/partb/vacancy").then((r) => setVac(r.data)); }, []);
  useEffect(() => { load(); const t = setInterval(() => http.get("/partb/vacancy").then((r) => setVac(r.data)), 15000); return () => clearInterval(t); }, [load]);
  return (
    <div data-testid="allotment-page">
      <PageHeader eyebrow="Part B" title="Seat management & allotment" description="Seat counters are guarded atomically: an allotment that would exceed capacity is refused. Vacancy refreshes every 15 seconds." />
      <Tabs defaultValue="batches">
        <TabsList className="mb-6">
          <TabsTrigger data-testid="allot-tab-batches" value="batches">Merit & waitlist batches</TabsTrigger>
          <TabsTrigger data-testid="allot-tab-vacancy" value="vacancy">Live vacancy</TabsTrigger>
          <TabsTrigger data-testid="allot-tab-hold" value="hold">On hold & cancellation</TabsTrigger>
          <TabsTrigger data-testid="allot-tab-reports" value="reports">Reports</TabsTrigger>
        </TabsList>
        <TabsContent value="batches"><BatchesTab batches={batches} reload={load} manage={manage} /></TabsContent>
        <TabsContent value="vacancy"><VacancyGrid rows={vac} /></TabsContent>
        <TabsContent value="hold"><HoldTab manage={manage} /></TabsContent>
        <TabsContent value="reports"><ReportsTab /></TabsContent>
      </Tabs>
    </div>
  );
}

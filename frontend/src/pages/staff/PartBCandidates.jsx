import { useCallback, useEffect, useState } from "react";
import { PencilLine } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const Correct = ({ c, onClose, onDone }) => {
  const codes = c.courses.filter((x) => x.outcome !== "rejected").map((x) => x.program_code);
  const [courses, setCourses] = useState(Object.fromEntries(codes.map((k) => [k, c.consent?.courses?.[k] || "accept"])));
  const [overall, setOverall] = useState(true);
  const [reason, setReason] = useState("");
  const save = async () => {
    try { await http.post(`/partb/consents/${c.candidate_id}/correct`, { courses, overall, reason }); toast.success("Consent corrected (new version)"); onDone(); onClose(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="consent-correct-dialog"><DialogHeader><DialogTitle>Correct consent · {c.name}</DialogTitle></DialogHeader>
        {codes.map((k) => <label key={k} className="flex items-center justify-between text-sm">{k}
          <select data-testid={`correct-consent-${k}`} className="h-9 rounded-md border border-input bg-background px-3 text-sm" value={courses[k]} onChange={(e) => setCourses({ ...courses, [k]: e.target.value })}>
            <option value="accept">Accept</option><option value="decline">Decline</option></select></label>)}
        <label className="flex items-center gap-2 text-sm"><Checkbox data-testid="correct-consent-overall" checked={overall} onCheckedChange={(v) => setOverall(!!v)} />Overall admission consent</label>
        <Input aria-label="Reason" data-testid="correct-consent-reason" placeholder="Reason (audited)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button data-testid="correct-consent-save" disabled={reason.trim().length < 5} onClick={save}>Save new version</Button>
      </DialogContent>
    </Dialog>
  );
};

export default function PartBCandidates() {
  const { user } = useAuth();
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => http.get("/partb/candidates").then((r) => setRows(r.data)), []);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="partb-candidates-page">
      <PageHeader eyebrow="Part B" title="Part B candidates" description="Eligibility, consent version, document stages and current seat for every candidate in the active merit/waitlist lists." />
      <Card className="overflow-x-auto p-0">
        <Table data-testid="partb-candidates-table">
          <TableHeader><TableRow>{["Candidate", "Courses", "Consent", "Counselling docs", "Admission docs", "Seat", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>{rows.map((c) => (
            <TableRow key={c.candidate_id} data-testid={`partb-candidate-${c.candidate_ref}`}>
              <TableCell className="text-sm">{c.name}<p className="font-mono text-xs text-muted-foreground">{c.candidate_ref} · {c.application_ref}</p></TableCell>
              <TableCell className="text-xs">{c.courses.map((x) => `${x.program_code} ${x.outcome}${x.merit_rank ? ` #${x.merit_rank}` : ""}${x.waitlist_rank ? ` WL#${x.waitlist_rank}` : ""}`).join(" · ")}</TableCell>
              <TableCell className="text-xs">{c.consent ? `v${c.consent.version} · ${Object.entries(c.consent.courses).map(([k, v]) => `${k}:${v}`).join(", ")}` : <StatusPill status="draft" label="pending" />}</TableCell>
              <TableCell><StatusPill status={c.docs_initial === "verified" ? "active" : c.docs_initial} label={c.docs_initial.replace("_", " ")} /></TableCell>
              <TableCell><StatusPill status={c.docs_admission === "verified" ? "active" : c.docs_admission} label={c.docs_admission.replace("_", " ")} /></TableCell>
              <TableCell className="text-xs">{c.allotment ? `${c.allotment.program_code} · ${c.allotment.status}` : "—"}</TableCell>
              <TableCell>{can(user, "consent.correct") && <Button size="sm" variant="ghost" data-testid={`consent-correct-${c.candidate_ref}`} onClick={() => setEdit(c)}><PencilLine className="h-4 w-4" /></Button>}</TableCell>
            </TableRow>))}</TableBody>
        </Table>
      </Card>
      {edit && <Correct c={edit} onClose={() => setEdit(null)} onDone={load} />}
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";
import { PanelistPicker } from "@/components/interviews/SessionDialog";

const sel = "h-8 rounded-md border border-input bg-background px-2 text-sm";
const Att = ({ value, onChange, testId }) => (
  <select aria-label="Attendance" data-testid={testId} className={sel} value={value || ""} onChange={(e) => onChange(e.target.value)}>
    <option value="">Not recorded</option><option value="present">Present</option><option value="absent">Absent</option>
  </select>
);

export default function InterviewSession() {
  const { id } = useParams();
  const [s, setS] = useState(null);
  const [panelists, setPanelists] = useState([]);
  const [pids, setPids] = useState([]);
  const [att, setAtt] = useState({ candidates: {}, panelists: {} });
  const load = useCallback(() => http.get(`/interviews/sessions/${id}`).then((r) => { setS(r.data); setPids(r.data.panelists.map((p) => p.id)); setAtt({ candidates: {}, panelists: {} }); }), [id]);
  useEffect(() => { load(); http.get("/interviews/panelists").then((r) => setPanelists(r.data)); }, [load]);
  const savePanelists = async () => { try { await http.put(`/interviews/sessions/${id}/panelists`, { panelist_ids: pids }); toast.success("Panelists updated"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const saveAtt = async () => { try { await http.post(`/interviews/sessions/${id}/attendance`, att); toast.success("Attendance saved"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const mark = (k, key) => (v) => v && setAtt({ ...att, [k]: { ...att[k], [key]: v } });
  if (!s) return null;
  const dirty = Object.keys(att.candidates).length + Object.keys(att.panelists).length > 0;
  return (
    <div data-testid="interview-session-page">
      <Link to="/staff/interviews" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />All sessions</Link>
      <PageHeader eyebrow={s.type_label} title={`${s.date} · ${s.start}–${s.end} IST`} description={`${s.location} · ${s.room} · ${s.booked}/${s.capacity} booked`}
        actions={<Button data-testid="attendance-save-button" onClick={saveAtt} disabled={!dirty}><Save className="mr-1.5 h-4 w-4" />Save attendance</Button>} />
      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <Card className="overflow-x-auto p-0">
          <Table data-testid="session-candidates-table">
            <TableHeader><TableRow>{["Candidate", "Application", "Source", "Attendance"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {s.candidates.length === 0 && <TableRow><TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">No candidates booked yet.</TableCell></TableRow>}
              {s.candidates.map((c) => (
                <TableRow key={c.booking_id} data-testid={`session-candidate-${c.candidate_ref}`}>
                  <TableCell className="text-sm">{c.name}<p className="font-mono text-xs text-muted-foreground">{c.candidate_ref} · {c.city}</p></TableCell>
                  <TableCell className="font-mono text-xs">{c.application_ref} · v{c.version}</TableCell>
                  <TableCell><StatusPill status={c.source} /></TableCell>
                  <TableCell><Att testId={`attendance-candidate-${c.candidate_ref}`} value={att.candidates[c.booking_id] ?? c.attendance} onChange={mark("candidates", c.booking_id)} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
        <div className="space-y-6">
          <Card testId="session-panelists-card">
            <p className="font-semibold">Panelist attendance</p>
            <ul className="mt-3 space-y-2">
              {s.panelists.map((p) => <li key={p.id} className="flex items-center justify-between gap-3 text-sm">{p.name}<Att testId={`attendance-panelist-${p.id}`} value={att.panelists[p.id] ?? p.attendance} onChange={mark("panelists", p.id)} /></li>)}
              {s.panelists.length === 0 && <li className="text-sm text-muted-foreground">No panelists assigned.</li>}
            </ul>
          </Card>
          <Card>
            <p className="mb-3 font-semibold">Assign panelists</p>
            <PanelistPicker panelists={panelists} value={pids} onChange={setPids} />
            <p className="mt-2 text-xs text-muted-foreground">Overlapping assignments on the same date are rejected.</p>
            <Button className="mt-4" size="sm" data-testid="panelists-save-button" onClick={savePanelists}>Save panelists</Button>
          </Card>
        </div>
      </div>
    </div>
  );
}

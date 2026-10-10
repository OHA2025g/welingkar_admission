import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { FORM_SCHEMA } from "@/lib/formSchema";
import { FieldList, errorMap } from "@/components/candidate/FormEngine";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const Img = ({ id, alt, className }) => {
  const [url, setUrl] = useState(null);
  useEffect(() => { if (id) http.get(`/files/${id}`, { responseType: "blob" }).then((r) => setUrl(URL.createObjectURL(r.data))); }, [id]);
  return url ? <img src={url} alt={alt} className={className} /> : <div className={`${className} flex items-center justify-center bg-secondary text-xs text-muted-foreground`}>None</div>;
};

const Flat = ({ data }) => (
  <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
    {Object.entries(data || {}).map(([k, v]) => (
      <div key={k} className="min-w-0"><dt className="text-xs uppercase tracking-wider text-muted-foreground">{k.replace(/_/g, " ")}</dt>
        <dd className="break-words">{typeof v === "object" ? (Array.isArray(v) ? (v.length ? v.map((x) => (typeof x === "object" ? Object.values(x).filter(Boolean).join(" · ") : x)).join(" | ") : "—") : Object.entries(v || {}).map(([a, b]) => `${a}: ${b}`).join(", ")) : String(v ?? "—")}</dd></div>
    ))}
  </dl>
);

export default function ApplicationDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [a, setA] = useState(null);
  const [edit, setEdit] = useState(null);
  const [reason, setReason] = useState("");
  const [errs, setErrs] = useState({});
  const load = useCallback(() => http.get(`/admin/applications/${id}`).then((r) => setA(r.data)), [id]);
  useEffect(() => { load(); }, [load]);
  const save = async () => {
    try {
      const { data } = await http.post(`/admin/applications/${id}/correction`, { section: edit.key, data: edit.data, reason });
      toast.success(`Saved as version ${data.version}`); setEdit(null); setReason(""); setErrs({}); load();
    } catch (e) { setErrs(errorMap(e?.response?.data?.detail?.errors)); toast.error(errMsg(e)); }
  };
  const pdf = async () => { try { await downloadFile(`/admin/applications/${id}/pdf`, `${a.application_ref}.pdf`); } catch (e) { toast.error(errMsg(e)); } };
  if (!a) return null;
  const canFix = can(user, "applications.correct") && a.status === "submitted";
  return (
    <div data-testid="application-detail-page">
      <PageHeader eyebrow={a.candidate.candidate_ref} title={`${a.candidate.name} · ${a.application_ref}`}
        description={`${a.candidate.email} · ${a.candidate.mobile} · ${a.candidate.city}, ${a.candidate.state}`}
        actions={a.status === "submitted" && <Button data-testid="staff-application-pdf-button" variant="outline" onClick={pdf}><Download className="mr-1.5 h-4 w-4" />PDF (v{a.submitted_version})</Button>} />
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          {a.sections_meta.map((s) => (
            <Card key={s.key} testId={`staff-section-${s.key}`}>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-semibold">{s.title}</h2>
                <div className="flex items-center gap-2">
                  <StatusPill status={a.section_status[s.key] === "complete" ? "success" : "draft"} />
                  {canFix && FORM_SCHEMA[s.key] && <Button data-testid={`correct-${s.key}-button`} size="sm" variant="ghost" onClick={() => setEdit({ key: s.key, title: s.title, data: structuredClone(a.sections[s.key] || {}) })}><PencilLine className="mr-1 h-3.5 w-3.5" />Correct</Button>}
                </div>
              </div>
              <Flat data={a.sections[s.key]} />
            </Card>
          ))}
        </div>
        <div className="space-y-4">
          <Card>
            <p className="text-sm font-semibold">Status</p>
            <div className="mt-2 flex flex-wrap gap-2"><StatusPill testId="staff-app-status" status={a.status === "submitted" ? "active" : "draft"} /><StatusPill status={a.fee_paid ? "success" : "draft"} /></div>
            <p className="mt-2 text-xs text-muted-foreground">{a.status === "submitted" ? `Submitted ${fmtIST(a.submitted_at)}` : "Draft"} · Fee {a.fee_paid ? a.fee_order_ref : "unpaid"}</p>
          </Card>
          <Card><p className="mb-3 text-sm font-semibold">Photo & signature</p><Img id={a.photo_file_id} alt="Candidate photo" className="h-40 w-32 rounded-sm object-cover" /><Img id={a.signature_file_id} alt="Signature" className="mt-3 h-14 w-48 object-contain" /></Card>
          <Card testId="staff-post-status"><p className="mb-2 text-sm font-semibold">Post-submission</p>
            {["declaration", "essays", "piq", "graduation", "confirmation"].map((k) => <p key={k} className="flex justify-between text-sm capitalize"><span>{k}</span><span className="text-muted-foreground">{a.post?.[k] ? "done" : "pending"}</span></p>)}</Card>
          <Card testId="staff-versions"><p className="mb-2 text-sm font-semibold">Versions</p>
            {a.versions.map((v) => <p key={v.version} className="text-xs"><b>v{v.version}</b> · {v.reason} · {v.created_by} · {fmtIST(v.created_at)}</p>)}
            {!a.versions.length && <p className="text-xs text-muted-foreground">Not submitted</p>}</Card>
        </div>
      </div>
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent data-testid="correction-dialog" className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader><DialogTitle>Correct {edit?.title}</DialogTitle>
            <DialogDescription>Creates version {a.submitted_version + 1}, records before/after in the audit log and asks the candidate to reconfirm their data.</DialogDescription></DialogHeader>
          {edit && <FieldList fields={FORM_SCHEMA[edit.key]} value={edit.data} errors={errs} onChange={(d) => setEdit({ ...edit, data: d })} />}
          <div className="space-y-1.5"><Label htmlFor="corr-reason">Reason (required)</Label><Input id="corr-reason" data-testid="correction-reason-input" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
          <Button data-testid="correction-save-button" disabled={reason.trim().length < 5} onClick={save}>Save correction</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

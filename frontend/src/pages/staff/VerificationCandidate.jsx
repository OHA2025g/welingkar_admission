import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Eye } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { http, errMsg, fmtIST } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

const view = async (fid) => {
  const w = window.open("", "_blank");
  try { const r = await http.get(`/files/${fid}`, { responseType: "blob" }); w.location = URL.createObjectURL(r.data); }
  catch (e) { w?.close(); toast.error(errMsg(e)); }
};

const DocReview = ({ it, onDone }) => {
  const [remarks, setRemarks] = useState("");
  const d = it.doc;
  const review = async (status) => {
    try { const { data } = await http.post(`/verify/documents/${d.id}`, { status, remarks, version: d.version }); toast.success(`${it.label}: ${status}`); setRemarks(""); onDone(data); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <li data-testid={`review-doc-${it.key}`} className="py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="text-sm font-medium">{it.label}</p>
          <p className="text-xs text-muted-foreground">{d ? `v${d.version} · uploaded ${fmtIST(d.uploaded_at)}${d.superseded.length ? ` · ${d.superseded.length} superseded` : ""}` : "Not uploaded"}</p>
          {d?.remarks && <p className="text-xs text-destructive">Remark: {d.remarks}</p>}</div>
        <div className="flex items-center gap-2">
          <StatusPill testId={`review-status-${it.key}`} status={d ? (d.status === "verified" ? "active" : d.status) : "draft"} label={d ? d.status : "missing"} />
          {d && <Button size="sm" variant="ghost" data-testid={`review-view-${it.key}`} onClick={() => view(d.file_id)}><Eye className="h-4 w-4" /></Button>}
        </div>
      </div>
      {d && d.status !== "verified" && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Input aria-label="Remarks" data-testid={`review-remarks-${it.key}`} placeholder="Discrepancy remarks for the candidate" value={remarks} onChange={(e) => setRemarks(e.target.value)} className="max-w-md" />
          <Button size="sm" data-testid={`review-verify-${it.key}`} onClick={() => review("verified")}>Verify</Button>
          <Button size="sm" variant="outline" data-testid={`review-discrepancy-${it.key}`} disabled={remarks.trim().length < 5} onClick={() => review("discrepancy")}>Flag discrepancy</Button>
        </div>
      )}
      {it.history.length > 0 && <p className="mt-2 text-xs text-muted-foreground">History: {it.history.map((h) => `${h.action} v${h.version} (${h.by})`).join(" → ")}</p>}
    </li>
  );
};

export default function VerificationCandidate() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const stage = sp.get("stage") || "initial";
  const [d, setD] = useState(null);
  const load = useCallback(() => http.get(`/verify/candidates/${id}`, { params: { stage } }).then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e))), [id, stage]);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  return (
    <div data-testid="verification-candidate-page">
      <Link to="/staff/verification" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Worklists</Link>
      <PageHeader eyebrow={d.title} title={d.candidate.name} description={`${d.candidate.candidate_ref} · ${d.candidate.application_ref} · ${d.candidate.category || ""}`}
        actions={<StatusPill testId="review-stage-status" status={d.summary.status === "verified" ? "active" : d.summary.status} label={d.summary.status.replace("_", " ")} />} />
      <Card><ul className="divide-y divide-border">{d.items.map((it) => <DocReview key={it.key} it={it} onDone={setD} />)}</ul></Card>
    </div>
  );
}

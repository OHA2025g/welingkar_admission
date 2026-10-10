import { useCallback, useEffect, useRef, useState } from "react";
import { Printer, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { http, errMsg, fmtIST } from "@/lib/api";
import { Card, StatusPill } from "@/components/portal/ui";
import { PolicyHelp } from "@/components/portal/PolicyHelp";

const DocRow = ({ stage, it, reload }) => {
  const ref = useRef();
  const [busy, setBusy] = useState(false);
  const d = it.doc;
  const up = async (f) => {
    if (!f) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", f);
    try { await http.post(`/candidate/partb/documents/${stage}/${it.key}`, fd); toast.success(`${it.label} uploaded`); reload(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); ref.current.value = ""; }
  };
  return (
    <li data-testid={`doc-row-${stage}-${it.key}`} className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium">{it.label}</p>
        {d && <p className="text-xs text-muted-foreground">v{d.version} · uploaded {fmtIST(d.uploaded_at)}</p>}
        {d?.status === "discrepancy" && <p data-testid={`doc-remarks-${stage}-${it.key}`} className="mt-1 text-xs text-destructive">Remark: {d.remarks}</p>}
      </div>
      <div className="flex items-center gap-2">
        <StatusPill testId={`doc-status-${stage}-${it.key}`} status={d ? d.status : "draft"} label={d ? d.status : "not uploaded"} />
        {d?.status !== "verified" && <>
          <input ref={ref} type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden" data-testid={`doc-file-${stage}-${it.key}`} onChange={(e) => up(e.target.files[0])} />
          <Button size="sm" variant="outline" disabled={busy} data-testid={`doc-upload-${stage}-${it.key}`} onClick={() => ref.current.click()}>
            <Upload className="mr-1 h-4 w-4" />{d ? "Re-upload" : "Upload"}</Button></>}
      </div>
    </li>
  );
};

export const DocumentsPanel = ({ stage, onChange }) => {
  const [d, setD] = useState(null);
  const load = useCallback(() => http.get(`/candidate/partb/documents/${stage}`).then((r) => { setD(r.data); onChange?.(); }), [stage]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  return (
    <Card testId={`documents-${stage}`} className="print:border-0">
      {stage === "initial" && <div className="mb-4"><PolicyHelp topic="documents" /></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="font-semibold">{d.title}</p>
          <p className="text-xs text-muted-foreground">{d.summary.uploaded}/{d.summary.required} uploaded · {d.summary.verified} verified · PDF/JPG/PNG up to 2 MB</p></div>
        <div className="flex items-center gap-2"><StatusPill testId={`documents-${stage}-status`} status={d.summary.status === "verified" ? "active" : d.summary.status} label={d.summary.status.replace("_", " ")} />
          <Button size="sm" variant="ghost" data-testid={`documents-${stage}-print`} onClick={() => window.print()}><Printer className="h-4 w-4" /></Button></div>
      </div>
      {d.locked_reason ? <p data-testid={`documents-${stage}-locked`} className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{d.locked_reason}</p> :
        <ul className="mt-2 divide-y divide-border">{d.items.map((it) => <DocRow key={it.key} stage={stage} it={it} reload={load} />)}</ul>}
    </Card>
  );
};

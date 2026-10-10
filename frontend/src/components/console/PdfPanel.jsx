import { useState } from "react";
import { FileText, Eye, Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { errMsg, fetchPdfBlobUrl, downloadUrl } from "@/lib/api";
import { Panel, Field } from "./Panel";

export const PdfPanel = ({ application, orders, delay }) => {
  const paid = orders.filter((o) => o.status === "paid");
  const [orderId, setOrderId] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(null);
  const selected = paid.find((o) => o.id === orderId) || paid[0];

  const docs = {
    summary: { path: `/pdf/application/${application?.application_ref}`, name: `${application?.application_ref}-summary.pdf`, title: "Application summary" },
    receipt: { path: `/pdf/receipt/${selected?.id}`, name: `${selected?.order_ref}-receipt.pdf`, title: "Payment receipt" },
  };

  const go = async (kind, mode) => {
    setBusy(`${kind}-${mode}`);
    try {
      const url = await fetchPdfBlobUrl(docs[kind].path);
      if (mode === "download") { downloadUrl(url, docs[kind].name); toast.success(`${docs[kind].title} downloaded`); }
      else setPreview({ url, title: docs[kind].title });
    } catch (e) {
      toast.error(errMsg(e));
    } finally { setBusy(null); }
  };

  const Btns = ({ kind, disabled, testPrefix }) => (
    <div className="flex gap-2">
      <Button data-testid={`${testPrefix}-preview-button`} size="sm" variant="outline" disabled={disabled || busy} onClick={() => go(kind, "preview")} className="btn-press flex-1">
        {busy === `${kind}-preview` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><Eye className="mr-1.5 h-3.5 w-3.5" />Preview</>}
      </Button>
      <Button data-testid={`${testPrefix}-button`} size="sm" disabled={disabled || busy} onClick={() => go(kind, "download")} className="btn-press flex-1">
        {busy === `${kind}-download` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <><Download className="mr-1.5 h-3.5 w-3.5" />Download</>}
      </Button>
    </div>
  );

  return (
    <Panel testId="pdf-panel" eyebrow="Documents · ReportLab" title="Server-rendered PDFs" icon={FileText} delay={delay} className="lg:col-span-4">
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-sm font-medium">Application summary</p>
          <p className="font-mono-x text-xs text-muted-foreground">{application?.application_ref} · {application?.candidate_name} · v{application?.snapshot_version}</p>
          <Btns kind="summary" disabled={!application} testPrefix="pdf-download-application-summary" />
        </div>
        <div className="space-y-2 border-t border-border pt-5">
          <Field label="Fee receipt (verified payments only)">
            <Select value={selected?.id || ""} onValueChange={setOrderId} disabled={!paid.length}>
              <SelectTrigger data-testid="pdf-receipt-order-select"><SelectValue placeholder="No paid orders yet" /></SelectTrigger>
              <SelectContent>
                {paid.map((o) => <SelectItem key={o.id} value={o.id}>{o.order_ref}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Btns kind="receipt" disabled={!selected} testPrefix="pdf-download-fee-receipt" />
        </div>
      </div>
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent data-testid="pdf-preview-modal-dialog" className="max-w-4xl border-border bg-card">
          <DialogHeader><DialogTitle>{preview?.title}</DialogTitle></DialogHeader>
          {preview && <iframe title="pdf-preview" src={preview.url} className="h-[70vh] w-full rounded-sm bg-white" />}
        </DialogContent>
      </Dialog>
    </Panel>
  );
};

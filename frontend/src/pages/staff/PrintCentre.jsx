import { useState } from "react";
import { Printer } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { errMsg, downloadFile } from "@/lib/api";
import { Card, PageHeader } from "@/components/portal/ui";
import { CandidateSearch } from "@/components/portal/CandidateSearch";

const DOCS = [
  ["application", "Application form", {}], ["allotment", "Allotment receipt", {}],
  ["payment", "Admission fee receipt", { fee: "admission_fee" }], ["payment", "Application fee receipt", { fee: "application_fee" }],
  ["cancellation", "Cancellation receipt", {}],
];

export default function PrintCentre() {
  const [c, setC] = useState(null);
  const print = async (kind, params) => {
    try { const n = await downloadFile(`/admin/print/${kind}/${c.id}`, `${kind}.pdf`, params); toast.success(`${n} generated`); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="print-centre-page">
      <PageHeader eyebrow="Admin" title="Print centre" description="Generate the current official PDF for a candidate. Each print is audited; document types follow your role." />
      <Card className="mb-6"><CandidateSearch prefix="print" onPick={setC} /></Card>
      {c && <Card testId="print-candidate-card">
        <p className="font-semibold">{c.name} <span className="font-mono text-xs text-muted-foreground">{c.candidate_ref}</span></p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DOCS.map(([kind, label, params]) => (
            <Button key={label} variant="outline" className="justify-start" data-testid={`print-${kind}-${params.fee || "doc"}`} onClick={() => print(kind, params)}>
              <Printer className="mr-2 h-4 w-4" />{label}</Button>))}
        </div>
      </Card>}
    </div>
  );
}

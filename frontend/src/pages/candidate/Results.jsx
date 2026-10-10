import { useEffect, useState } from "react";
import { Download, Hourglass } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST, downloadFile } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

export default function CandidateResults() {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/candidate/results").then((r) => setD(r.data)); }, []);
  const pdf = async () => { try { await downloadFile("/candidate/results/pdf", "result.pdf"); } catch (e) { toast.error(errMsg(e)); } };
  if (!d) return null;
  return (
    <div data-testid="candidate-results-page">
      <PageHeader eyebrow="Results" title="Your admission result" description={d.published ? `Published ${fmtIST(d.published_at)} · result version ${d.version}` : "Results appear here only after the institute publishes them."}
        actions={d.published && d.rows.length > 0 && <><Button data-testid="result-pdf-button" onClick={pdf}><Download className="mr-1.5 h-4 w-4" />Download PDF</Button>
          <Button variant="outline" data-testid="result-print-button" onClick={() => window.print()}>Print</Button></>} />
      {!d.published ? (
        <Card testId="results-not-published" className="flex items-center gap-4"><Hourglass className="h-6 w-6 text-[hsl(var(--gold))]" /><p className="text-sm">Results have not been published yet. We will notify you once they are out.</p></Card>
      ) : d.rows.length === 0 ? (
        <Card testId="results-none"><p className="text-sm">There is no published outcome for your application in this round.</p></Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <Table data-testid="candidate-results-table">
            <TableHeader><TableRow>{["Choice", "Programme", "Outcome", "Merit rank", "TFW"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {d.rows.map((r) => (
                <TableRow key={r.program_code} data-testid={`candidate-result-${r.program_code}`}>
                  <TableCell>{r.choice}</TableCell><TableCell className="font-medium">{r.program_name}</TableCell>
                  <TableCell><StatusPill testId={`candidate-result-outcome-${r.program_code}`} status={r.outcome} label={r.outcome_label} /></TableCell>
                  <TableCell className="tabular-nums">{r.rank ?? "—"}</TableCell>
                  <TableCell className="text-sm">{r.tfw_rank ? `${r.tfw_outcome_label} (TFW rank ${r.tfw_rank})` : "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </div>
  );
}

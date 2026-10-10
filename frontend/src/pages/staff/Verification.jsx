import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, fmtIST } from "@/lib/api";
import { Card, PageHeader, StatusPill } from "@/components/portal/ui";

export default function VerificationPage() {
  const [stage, setStage] = useState("initial");
  const [list, setList] = useState("registered");
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/verify/worklist", { params: { stage, list } }).then((r) => setD(r.data)); }, [stage, list]);
  return (
    <div data-testid="verification-page">
      <PageHeader eyebrow="Document verification" title="Verification worklists" description="Counselling and admission documents are verified in separate stages. Discrepancy remarks are sent to the candidate for a targeted re-upload." />
      <div className="mb-4 flex flex-wrap gap-4">
        <Tabs value={stage} onValueChange={setStage}><TabsList>
          <TabsTrigger data-testid="verify-stage-initial" value="initial">Counselling documents</TabsTrigger>
          <TabsTrigger data-testid="verify-stage-admission" value="admission">Admission documents</TabsTrigger></TabsList></Tabs>
        <Tabs value={list} onValueChange={setList}><TabsList>
          {["registered", "discrepancy", "verified"].map((k) => <TabsTrigger key={k} data-testid={`verify-list-${k}`} value={k}>{k} ({d?.counts[k] ?? 0})</TabsTrigger>)}</TabsList></Tabs>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="verify-worklist-table">
          <TableHeader><TableRow>{["Candidate", "Uploaded", "Verified", "Discrepancy", "Last upload", ""].map((h, i) => <TableHead key={i}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {d?.rows.length === 0 && <TableRow><TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">Worklist is empty.</TableCell></TableRow>}
            {d?.rows.map((r) => (
              <TableRow key={r.candidate_id} data-testid={`verify-row-${r.candidate_ref}`}>
                <TableCell className="text-sm">{r.name}<p className="font-mono text-xs text-muted-foreground">{r.candidate_ref}</p></TableCell>
                <TableCell className="tabular-nums">{r.uploaded}/{r.required}</TableCell><TableCell className="tabular-nums">{r.verified}</TableCell>
                <TableCell className="tabular-nums">{r.discrepancy}</TableCell><TableCell className="text-xs">{fmtIST(r.last_upload)}</TableCell>
                <TableCell><StatusPill status={r.stage_status} /> <Button asChild size="sm" variant="outline" className="ml-2"><Link data-testid={`verify-open-${r.candidate_ref}`} to={`/staff/verification/${r.candidate_id}?stage=${stage}`}>Review</Link></Button></TableCell>
              </TableRow>))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

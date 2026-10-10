import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST } from "@/lib/api";
import { Card, Empty, PageHeader, StatusPill } from "@/components/portal/ui";

const show = (v) => (v === null || v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));

const Detail = ({ e, onClose }) => (
  <Sheet open={!!e} onOpenChange={(o) => !o && onClose()}>
    <SheetContent data-testid="audit-detail-drawer" className="w-full overflow-y-auto sm:max-w-xl">
      {e && <>
        <SheetHeader><SheetTitle className="font-mono text-base">{e.action}</SheetTitle>
          <SheetDescription>{fmtIST(e.at)} · {e.actor.email || e.actor.role} ({e.actor.role})</SheetDescription></SheetHeader>
        <dl className="mt-6 grid grid-cols-[120px_1fr] gap-y-2 text-sm">
          {[["Entity", `${e.entity_type} ${e.entity_id || ""}`], ["Outcome", e.outcome], ["Reason", e.reason], ["Correlation ID", e.correlation_id], ["IP", e.ip]].map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="break-all font-mono text-xs">{show(v)}</dd></div>
          ))}
        </dl>
        <h3 className="mt-8 text-sm font-semibold">Changes</h3>
        {e.changes.length ? (
          <Table data-testid="audit-changes-table" className="mt-2">
            <TableHeader><TableRow><TableHead>Field</TableHead><TableHead>Before</TableHead><TableHead>After</TableHead></TableRow></TableHeader>
            <TableBody>{e.changes.map((c) => (
              <TableRow key={c.field}><TableCell className="font-mono text-xs">{c.field}</TableCell>
                <TableCell className="break-all bg-red-50/60 font-mono text-xs text-red-800">{show(c.before)}</TableCell>
                <TableCell className="break-all bg-emerald-50/60 font-mono text-xs text-emerald-800">{show(c.after)}</TableCell></TableRow>
            ))}</TableBody>
          </Table>
        ) : <p className="mt-2 text-sm text-muted-foreground">No field changes recorded.</p>}
      </>}
    </SheetContent>
  </Sheet>
);

export default function AuditPage() {
  const [f, setF] = useState({ action: "all", entity_type: "all", outcome: "all", actor: "", date_from: "", date_to: "" });
  const [page, setPage] = useState(1);
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [sel, setSel] = useState(null);
  const load = useCallback(() => {
    const params = { page, page_size: 25 };
    ["action", "entity_type", "outcome"].forEach((k) => { if (f[k] !== "all") params[k] = f[k]; });
    if (f.actor) params.actor = f.actor;
    if (f.date_from) params.date_from = new Date(`${f.date_from}T00:00:00+05:30`).toISOString();
    if (f.date_to) params.date_to = new Date(`${f.date_to}T23:59:59+05:30`).toISOString();
    http.get("/audit", { params }).then((r) => { setD(r.data); setError(""); }).catch((e) => setError(errMsg(e)));
  }, [f, page]);
  useEffect(() => { load(); }, [load]);
  const upd = (k) => (v) => { setPage(1); setF({ ...f, [k]: v?.target ? v.target.value : v }); };
  const pages = d ? Math.max(1, Math.ceil(d.total / d.page_size)) : 1;

  const Sel = ({ k, label, options, testId }) => (
    <Select value={f[k]} onValueChange={upd(k)}>
      <SelectTrigger data-testid={testId} className="w-full sm:w-48" aria-label={label}><SelectValue /></SelectTrigger>
      <SelectContent><SelectItem value="all">All {label}</SelectItem>{options.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
    </Select>
  );

  return (
    <div data-testid="audit-page">
      <PageHeader eyebrow="Compliance" title="Audit log" description="Append-only record of privileged actions, sign-ins and denied requests. No business user can edit or delete entries." />
      <div className="mb-4 grid gap-3 sm:flex sm:flex-wrap">
        <Sel k="action" label="actions" options={d?.actions || []} testId="audit-log-filter-action" />
        <Sel k="entity_type" label="entities" options={d?.entity_types || []} testId="audit-log-filter-entity" />
        <Sel k="outcome" label="outcomes" options={["success", "failure", "denied"]} testId="audit-log-filter-outcome" />
        <Input data-testid="audit-log-filter-actor" placeholder="Actor email" value={f.actor} onChange={upd("actor")} className="sm:w-56" />
        <Input data-testid="audit-log-filter-from" type="date" aria-label="From date" value={f.date_from} onChange={upd("date_from")} className="sm:w-40" />
        <Input data-testid="audit-log-filter-to" type="date" aria-label="To date" value={f.date_to} onChange={upd("date_to")} className="sm:w-40" />
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="audit-log-table">
          <TableHeader><TableRow>{["Time (IST)", "Actor", "Action", "Entity", "Outcome", "Changes"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {d?.items.map((e) => (
              <TableRow key={e.id} data-testid={`audit-row-${e.id}`} tabIndex={0} className="cursor-pointer"
                onClick={() => setSel(e)} onKeyDown={(ev) => ev.key === "Enter" && setSel(e)}>
                <TableCell className="whitespace-nowrap text-xs">{fmtIST(e.at)}</TableCell>
                <TableCell className="text-sm">{e.actor.email || e.actor.role}<div className="text-xs text-muted-foreground">{e.actor.role}</div></TableCell>
                <TableCell className="font-mono text-xs">{e.action}</TableCell>
                <TableCell className="max-w-[220px] truncate text-xs text-muted-foreground">{e.entity_type} {e.entity_id}</TableCell>
                <TableCell><StatusPill status={e.outcome} /></TableCell>
                <TableCell className="text-xs">{e.changes.length || "—"}</TableCell>
              </TableRow>
            ))}
            {d && !d.items.length && <TableRow><TableCell colSpan={6}><Empty testId="audit-empty" text={error || "No audit events match these filters. Widen the dates or clear the actor."} /></TableCell></TableRow>}
            {error && !d && <TableRow><TableCell colSpan={6}><Empty testId="audit-error" text={`Could not load the audit log. ${error}`} /></TableCell></TableRow>}
          </TableBody>
        </Table>
      </Card>
      <div className="mt-4 flex items-center justify-between text-sm">
        <span data-testid="audit-total" className="text-muted-foreground">{d?.total ?? 0} events</span>
        <div className="flex items-center gap-2">
          <Button data-testid="audit-prev-page" variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
          <span>{page} / {pages}</span>
          <Button data-testid="audit-next-page" variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
        </div>
      </div>
      <Detail e={sel} onClose={() => setSel(null)} />
    </div>
  );
}

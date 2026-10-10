import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { http, errMsg, downloadFile, fmtIST } from "@/lib/api";
import { Card, StatusPill } from "@/components/portal/ui";

export const AllotmentCard = ({ a }) => {
  const receipt = async () => { try { const n = await downloadFile("/candidate/partb/allotment/receipt", "allotment-receipt.pdf"); toast.success(`${n} downloaded`); } catch (e) { toast.error(errMsg(e)); } };
  if (!a) return <Card testId="allotment-none"><p className="font-semibold">Seat allotment</p><p className="mt-1 text-sm text-muted-foreground">No seat allotted yet. Allotment happens in merit and waiting-list rounds after consent and document review.</p></Card>;
  const live = a.seat_held && ["allotted", "provisional"].includes(a.status);
  return (
    <Card testId="allotment-card" className={live ? "border-emerald-300" : ""}>
      <p className="text-xs font-semibold uppercase tracking-wider text-primary">Seat allotment</p>
      <p data-testid="allotment-program" className="mt-2 text-lg font-semibold">{a.program_name}</p>
      <div className="mt-2 flex flex-wrap gap-2"><StatusPill testId="allotment-status" status={a.status === "allotted" ? "active" : a.status} label={a.status.replace("_", " ")} />
        <StatusPill status="draft" label={`${a.batch_kind} round · v${a.version}`} /></div>
      <p className="mt-2 text-xs text-muted-foreground">Updated {fmtIST(a.updated_at)}</p>
      {live && <Button className="mt-4" data-testid="allotment-receipt-button" onClick={receipt}><Download className="mr-1.5 h-4 w-4" />Allotment receipt (r{a.receipt_version})</Button>}
      {a.status === "on_hold" && <p className="mt-3 text-sm text-amber-800">Your seat is on hold pending review. The receipt is issued once it is confirmed.</p>}
    </Card>
  );
};

export const BettermentCard = ({ offers, onDone }) => {
  if (!offers.length) return null;
  const respond = async (bid, response) => {
    try { await http.post(`/candidate/partb/betterment/${bid}`, { response }); toast.success(response === "accept" ? "Betterment consent recorded" : "Offer declined"); onDone(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card testId="betterment-card">
      <p className="font-semibold">Betterment offers</p>
      <p className="mt-1 text-sm text-muted-foreground">You may move to a higher-preference course. Your current seat is released only if the new allotment succeeds.</p>
      <ul className="mt-3 divide-y divide-border">
        {offers.map((o) => (
          <li key={o.batch_id} data-testid={`betterment-offer-${o.program_code}`} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
            <span>{o.program_name} · waitlist #{o.waitlist_rank} <span className="text-xs text-muted-foreground">({o.batch_name}, until {o.end_date})</span></span>
            {o.response === "pending" ? <span className="flex gap-2">
              <Button size="sm" data-testid={`betterment-accept-${o.program_code}`} onClick={() => respond(o.batch_id, "accept")}>Accept</Button>
              <Button size="sm" variant="outline" data-testid={`betterment-decline-${o.program_code}`} onClick={() => respond(o.batch_id, "decline")}>Decline</Button></span>
              : <StatusPill testId={`betterment-response-${o.program_code}`} status={o.response === "accept" ? "active" : "denied"} label={o.response} />}
          </li>
        ))}
      </ul>
    </Card>
  );
};

export const NotificationsCard = ({ items, onRead }) => (
  <Card testId="notifications-card">
    <div className="flex items-center justify-between"><p className="font-semibold">Notifications</p>
      {items.some((n) => !n.read_at) && <Button size="sm" variant="ghost" data-testid="notifications-read-all" onClick={onRead}>Mark all read</Button>}</div>
    <ul className="mt-2 divide-y divide-border">
      {items.length === 0 && <li className="py-3 text-sm text-muted-foreground">No notifications.</li>}
      {items.map((n) => (
        <li key={n.id} data-testid={`notification-${n.kind}`} className="py-3">
          <p className={`text-sm ${n.read_at ? "" : "font-semibold"}`}>{n.title}</p>
          <p className="text-xs text-muted-foreground">{n.body} · {fmtIST(n.created_at)}{n.email_status ? ` · email ${n.email_status}` : ""}</p>
        </li>
      ))}
    </ul>
  </Card>
);

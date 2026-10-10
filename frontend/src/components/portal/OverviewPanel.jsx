import { useEffect, useState } from "react";
import { fmtINR } from "@/lib/api";
import { http } from "@/lib/api";
import { Card } from "./ui";

const GROUPS = [
  ["part_a", "Part A", [["registered", "Registered"], ["verified", "Verified"], ["app_fee_paid", "App fee paid"], ["submitted", "Submitted"]]],
  ["interviews", "GA / PI & results", [["sessions", "Sessions"], ["booked", "Booked"], ["scored", "Scored"], ["published_version", "Published result"]]],
  ["part_b", "Part B", [["eligible", "Eligible"], ["consented", "Consented"], ["allotted", "Allotted"], ["provisional", "Provisional"], ["on_hold", "On hold"], ["seats_filled", "Seats filled"]]],
  ["finance", "Finance", [["admission_paid", "Admission fees"], ["collected_inr", "Collected", fmtINR], ["refunded_inr", "Refunded", fmtINR], ["offline_pending", "Offline pending"], ["cancellations_pending", "Cancellations pending"], ["refunds_due", "Refunds due"]]],
];

export const OverviewPanel = () => {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/admin/overview").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <section data-testid="overview-panel" className="mt-10 space-y-6">
      {GROUPS.map(([key, title, items]) => (
        <div key={key}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}{key === "part_b" && ` · ${d.part_b.seats_filled}/${d.part_b.seats_capacity} seats${d.part_b.vacancy_reconciled ? "" : " · NOT RECONCILED"}`}</p>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {items.map(([k, label, f]) => (
              <Card key={k} testId={`overview-${key}-${k}`} className="p-4">
                <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
                <p className="mt-1 font-['Outfit'] text-2xl font-bold tabular-nums">{d[key][k] == null ? "—" : f ? f(d[key][k]) : d[key][k]}</p>
              </Card>))}
          </div>
        </div>
      ))}
    </section>
  );
};

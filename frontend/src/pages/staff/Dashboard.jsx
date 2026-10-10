import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import { http } from "@/lib/api";
import { useAuth, can } from "@/context/AuthContext";
import { OverviewPanel } from "@/components/portal/OverviewPanel";
import { Card, Empty, PageHeader } from "@/components/portal/ui";
import { STAFF_MENU } from "@/lib/menu";

const linkFor = (key) => STAFF_MENU.find((m) => m.to.endsWith(`/${key}`))?.to || (key === "payments" || key === "reconciliation" ? "/poc" : null);

export default function StaffDashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/dashboard").then((r) => setD(r.data)); }, []);
  return (
    <div data-testid="staff-dashboard">
      <PageHeader eyebrow={d?.role_label || user.role_label} title={`Good to see you, ${user.name.split(" ")[0]}`}
        description="Your workspace shows only the areas your role is permitted to use." />
      {d?.health && (
        <div data-testid="ops-health" className="mb-6 flex flex-wrap gap-2 text-xs">
          {[["Mongo", d.health.mongo], ["Storage", d.health.storage], ["Email", d.health.email]].map(([k, v]) => (
            <span key={k} className="rounded-full border border-border px-3 py-1">{k}: {v}</span>
          ))}
        </div>
      )}
      {d?.health?.email === "console" && <Empty testId="email-console-banner" text="Email is in console mode. Messages are written to the server log, so candidates have not received mail." />}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        {d?.kpis?.map((k, i) => (
          <Card key={k.label} testId={`kpi-${i}`} className="p-5">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{k.label}</p>
            <p className="mt-2 font-['Outfit'] text-3xl font-bold tabular-nums">{k.value}</p>
          </Card>
        ))}
      </div>
      {["reports.read", "partb.read", "payments.read", "applications.read"].some((p) => can(user, p)) && <OverviewPanel />}
      <h2 className="mb-4 mt-12 text-lg font-semibold">Your modules</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {d?.modules?.map((m) => {
          const to = linkFor(m.key);
          const body = (
            <Card testId={`module-card-${m.key}`} className="group h-full transition-colors duration-200 hover:border-primary/40">
              <div className="flex items-start justify-between">
                <p className="font-semibold">{m.title}</p>
                <ArrowUpRight className="h-4 w-4 text-muted-foreground transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{m.ready ? "Available now" : `Arrives in Phase ${m.phase}`}</p>
            </Card>
          );
          return to ? <Link key={m.key} to={to}>{body}</Link> : <div key={m.key}>{body}</div>;
        })}
      </div>
    </div>
  );
}

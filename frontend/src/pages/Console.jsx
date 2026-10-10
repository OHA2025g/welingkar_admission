import { useCallback, useEffect, useState } from "react";
import { http } from "@/lib/api";
import { Header } from "@/components/console/Header";
import { OtpPanel } from "@/components/console/OtpPanel";
import { PaymentPanel } from "@/components/console/PaymentPanel";
import { PaymentsTable } from "@/components/console/PaymentsTable";
import { PdfPanel } from "@/components/console/PdfPanel";
import { EventLog } from "@/components/console/EventLog";

export default function Console() {
  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState(null);
  const [application, setApplication] = useState(null);
  const [orders, setOrders] = useState([]);
  const [tick, setTick] = useState(0);

  const loadOrders = useCallback(async () => {
    const { data } = await http.get("/payments/orders");
    setOrders(data);
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    http.get("/poc/health").then((r) => setHealth(r.data));
    http.get("/payments/config").then((r) => setConfig(r.data));
    http.get("/poc/applications").then((r) => setApplication(r.data[0]));
    loadOrders();
  }, [loadOrders]);

  const bump = () => setTick((t) => t + 1);

  return (
    <main data-testid="integration-console" className="dark grid-lines relative z-10 min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1440px] px-4 py-10 sm:px-8 lg:px-12 lg:py-14">
        <Header health={health} />
        <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-6"><OtpPanel channel="email" health={health} onActivity={bump} /></div>
          <div className="lg:col-span-6"><OtpPanel channel="whatsapp" health={health} onActivity={bump} /></div>
          <div className="lg:col-span-8"><PaymentPanel config={config} application={application} /></div>
          <PdfPanel application={application} orders={orders} />
          <PaymentsTable orders={orders} mocked={config?.refunds_mocked} reload={loadOrders} />
          <EventLog tick={tick} />
          <PolicyCard health={health} />
        </div>
      </div>
    </main>
  );
}

const PolicyCard = ({ health }) => {
  const p = health?.otp_policy;
  const rows = [
    ["OTP", p ? `${p.digits} digits · ${p.ttl_minutes} min expiry` : "—"],
    ["Resend", p ? `${p.resend_cooldown_seconds}s cooldown · 5/hr/destination` : "—"],
    ["Attempts", p ? `${p.max_attempts} per challenge → locked` : "—"],
    ["Webhook", health?.payments?.webhook_signature_verification ? "Signed (whsec)" : "Unsigned → re-verified with Stripe"],
    ["Refunds", health?.payments?.refunds_mode || "—"],
    ["Locale", `${health?.timezone || "Asia/Kolkata"} · ${health?.currency || "INR"}`],
  ];
  return (
    <section data-testid="policy-card" className="panel rise p-5 sm:p-6 lg:col-span-4">
      <p className="font-mono-x text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Controls in force</p>
      <h2 className="mt-1 text-lg font-semibold">Policy snapshot</h2>
      <dl className="mt-5 divide-y divide-border">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 py-2.5 text-sm">
            <dt className="text-muted-foreground">{k}</dt>
            <dd data-testid={`policy-${k.toLowerCase()}`} className="font-mono-x text-right text-xs">{v}</dd>
          </div>
        ))}
      </dl>
      <a data-testid="openapi-link" href={`${process.env.REACT_APP_BACKEND_URL}/api/docs`} target="_blank" rel="noreferrer"
        className="font-mono-x mt-5 inline-block text-xs text-primary underline-offset-4 hover:underline">/api/openapi.json · docs →</a>
    </section>
  );
};

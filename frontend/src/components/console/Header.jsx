import { Mail, MessageCircle, CreditCard, Clock } from "lucide-react";
import { useNow } from "@/lib/api";
import { MockedBadge } from "./StatusBadge";

const Health = ({ icon: Icon, label, ok, testId }) => (
  <span data-testid={testId} className="inline-flex items-center gap-2 rounded-sm border border-border bg-secondary/40 px-2.5 py-1 text-xs">
    <span className={`h-1.5 w-1.5 rounded-full pulse-dot ${ok ? "bg-emerald-400" : "bg-red-400"}`} />
    <Icon className="h-3.5 w-3.5 text-muted-foreground" />
    {label}
  </span>
);

export const Header = ({ health }) => {
  const now = useNow();
  const clock = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(now);
  return (
    <header className="rise border-b border-border pb-8">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="font-mono-x text-[11px] uppercase tracking-[0.25em] text-primary">
            Welingkar · WeSchool Admissions Portal · Phase 0
          </p>
          <h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
            Integration <span className="text-[hsl(var(--gold))]">proof</span> console
          </h1>
          <p className="mt-3 max-w-2xl text-sm text-muted-foreground sm:text-base">
            Live checks for the risky integrations: dual-channel OTP, INR payment verification with idempotent records, refund state machine and server-rendered PDFs.
          </p>
        </div>
        <div className="flex flex-col items-start gap-3 lg:items-end">
          <div data-testid="ist-clock" className="font-mono-x flex items-center gap-2 text-2xl tabular-nums">
            <Clock className="h-4 w-4 text-muted-foreground" /> {clock}
            <span className="text-xs text-muted-foreground">IST</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <Health testId="health-email-badge" icon={Mail} label="Resend email" ok={health?.email?.configured} />
            <Health testId="health-whatsapp-badge" icon={MessageCircle} label="Twilio WhatsApp" ok={health?.whatsapp?.configured} />
            <Health testId="health-stripe-badge" icon={CreditCard} label="Stripe · INR test" ok={!!health?.payments} />
            {health?.whatsapp?.mocked && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                WhatsApp <MockedBadge testId="health-whatsapp-mocked-badge" />
              </span>
            )}
            {health?.payments?.refunds_mocked && (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                Refunds <MockedBadge testId="health-refunds-mocked-badge" />
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};

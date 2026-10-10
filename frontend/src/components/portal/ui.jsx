import { Link } from "react-router-dom";
import { ROLE_TONE } from "@/lib/menu";

export const BrandMark = ({ to = "/", light = false }) => (
  <Link to={to} data-testid="brand-home-link" className="flex items-center gap-3">
    <span className="flex h-9 w-9 items-center justify-center rounded-sm bg-primary font-['Outfit'] text-sm font-bold text-white">We</span>
    <span className="leading-tight">
      <span className={`block font-['Outfit'] text-base font-bold tracking-tight ${light ? "text-white" : "text-foreground"}`}>WeSchool</span>
      <span className={`block text-[10px] uppercase tracking-[0.18em] ${light ? "text-white/70" : "text-muted-foreground"}`}>Welingkar · Admissions</span>
    </span>
  </Link>
);

export const PageHeader = ({ eyebrow, title, description, actions }) => (
  <div className="mb-8 flex flex-col gap-4 border-b border-border pb-6 md:flex-row md:items-end md:justify-between">
    <div>
      {eyebrow && <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{eyebrow}</p>}
      <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">{title}</h1>
      {description && <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">{description}</p>}
    </div>
    {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
  </div>
);

export const Pill = ({ children, tone = "bg-secondary text-foreground border-border", testId }) => (
  <span data-testid={testId} className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tone}`}>{children}</span>
);

export const RolePill = ({ role, label, testId }) => (
  <Pill testId={testId} tone={ROLE_TONE[role] || "bg-sky-50 text-sky-800 border-sky-200"}>{label}</Pill>
);

const STATUS = {
  active: "bg-emerald-50 text-emerald-800 border-emerald-200", verified: "bg-emerald-50 text-emerald-800 border-emerald-200",
  success: "bg-emerald-50 text-emerald-800 border-emerald-200", draft: "bg-amber-50 text-amber-800 border-amber-200",
  partially_verified: "bg-amber-50 text-amber-800 border-amber-200", registered: "bg-slate-100 text-slate-700 border-slate-300",
  closed: "bg-slate-100 text-slate-700 border-slate-300", superseded: "bg-slate-100 text-slate-600 border-slate-300",
  inactive: "bg-slate-100 text-slate-600 border-slate-300", disabled: "bg-red-50 text-red-700 border-red-200",
  denied: "bg-red-50 text-red-700 border-red-200", failure: "bg-red-50 text-red-700 border-red-200",
  archived: "bg-slate-100 text-slate-600 border-slate-300",
  generated: "bg-sky-50 text-sky-800 border-sky-200", approved: "bg-amber-50 text-amber-800 border-amber-200",
  published: "bg-emerald-50 text-emerald-800 border-emerald-200", selected: "bg-emerald-50 text-emerald-800 border-emerald-200",
  waitlisted: "bg-amber-50 text-amber-800 border-amber-200", not_selected: "bg-red-50 text-red-700 border-red-200",
  present: "bg-emerald-50 text-emerald-800 border-emerald-200", absent: "bg-red-50 text-red-700 border-red-200",
  incomplete: "bg-slate-100 text-slate-700 border-slate-300", manual_selection: "bg-sky-50 text-sky-800 border-sky-200",
  paid: "bg-emerald-50 text-emerald-800 border-emerald-200", awaiting_verification: "bg-amber-50 text-amber-800 border-amber-200",
  rejected: "bg-red-50 text-red-700 border-red-200", requested: "bg-amber-50 text-amber-800 border-amber-200",
  refunded: "bg-emerald-50 text-emerald-800 border-emerald-200", closed: "bg-slate-100 text-slate-700 border-slate-300",
  duplicate_payment: "bg-red-50 text-red-700 border-red-200", amount_mismatch: "bg-red-50 text-red-700 border-red-200",
  refund_failed: "bg-red-50 text-red-700 border-red-200", cancelled: "bg-slate-100 text-slate-700 border-slate-300",
  pending_signoff: "bg-amber-50 text-amber-800 border-amber-200", signoff_rejected: "bg-red-50 text-red-700 border-red-200",
};

export const StatusPill = ({ status, testId, label }) => (
  <Pill testId={testId} tone={STATUS[status] || "bg-secondary text-foreground border-border"}>{label || String(status || "—").replace("_", " ")}</Pill>
);

export const Card = ({ children, className = "", testId }) => (
  <div data-testid={testId} className={`rounded-md border border-border bg-card p-6 shadow-[0_1px_0_rgba(15,23,42,0.04)] ${className}`}>{children}</div>
);

export const Empty = ({ text = "Nothing here yet.", testId }) => (
  <div data-testid={testId} className="rounded-md border border-dashed border-border p-10 text-center text-sm text-muted-foreground">{text}</div>
);

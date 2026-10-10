const TONES = {
  success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  warning: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  error: "bg-red-500/10 text-red-400 border-red-500/30",
  info: "bg-sky-500/10 text-sky-400 border-sky-500/30",
  neutral: "bg-slate-500/10 text-slate-300 border-slate-500/30",
};

const STATUS_TONE = {
  paid: "success", verified: "success", succeeded: "success", sent: "success", delivered: "success", read: "success",
  pending: "warning", created: "warning", pending_provider: "warning", queued: "warning", accepted: "warning",
  failed: "error", expired: "error", locked: "error", delivery_failed: "error", amount_mismatch: "error", undelivered: "error",
  superseded: "neutral",
};

export const StatusBadge = ({ status, tone, testId, children }) => (
  <span
    data-testid={testId}
    className={`font-mono-x inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[11px] uppercase tracking-wider ${TONES[tone || STATUS_TONE[status] || "neutral"]}`}
  >
    {children || String(status).replace("_", " ")}
  </span>
);

export const MockedBadge = ({ testId }) => (
  <span
    data-testid={testId}
    className="font-mono-x inline-flex items-center rounded-sm border border-amber-400/60 bg-amber-400/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-widest text-amber-300"
  >
    Mocked
  </span>
);

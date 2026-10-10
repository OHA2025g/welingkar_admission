export const Panel = ({ eyebrow, title, icon: Icon, right, className = "", delay = 0, testId, children }) => (
  <section data-testid={testId} className={`panel rise p-5 sm:p-6 ${className}`} style={{ animationDelay: `${delay}ms` }}>
    <header className="mb-5 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-sm border border-border bg-secondary/60">
            <Icon className="h-4 w-4 text-primary" strokeWidth={1.75} />
          </div>
        )}
        <div>
          <p className="font-mono-x text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</p>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        </div>
      </div>
      {right}
    </header>
    {children}
  </section>
);

export const Field = ({ label, hint, children }) => (
  <label className="block space-y-1.5">
    <span className="font-mono-x text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
    {children}
    {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
  </label>
);

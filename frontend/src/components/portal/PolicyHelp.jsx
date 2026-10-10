import { useEffect, useState } from "react";
import { http } from "@/lib/api";

export function PolicyHelp({ topic }) {
  const [help, setHelp] = useState(null);
  useEffect(() => {
    http.get("/candidate/help", { params: { topic } }).then((r) => setHelp(r.data)).catch(() => setHelp(null));
  }, [topic]);
  if (!help) return null;
  return (
    <aside data-testid={`policy-help-${topic}`} className="rounded-md border border-border bg-secondary/50 p-4 text-sm">
      <p className="text-xs font-semibold uppercase tracking-wider text-primary">{help.title}</p>
      <ul className="mt-2 space-y-1.5 text-muted-foreground">
        {help.lines.map((line) => <li key={line}>{line}</li>)}
      </ul>
    </aside>
  );
}

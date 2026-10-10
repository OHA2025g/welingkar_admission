import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Construction } from "lucide-react";
import { http, errMsg } from "@/lib/api";
import { MODULE_INFO } from "@/lib/menu";
import { Card, PageHeader } from "@/components/portal/ui";

export default function ModulePlaceholder() {
  const { module } = useParams();
  const info = MODULE_INFO[module];
  const [msg, setMsg] = useState("");
  useEffect(() => {
    http.get(`/modules/${module}`).then((r) => setMsg(r.data.message)).catch((e) => setMsg(errMsg(e)));
  }, [module]);
  return (
    <div data-testid={`module-page-${module}`}>
      <PageHeader eyebrow={`Phase ${info?.phase}`} title={info?.title || module} />
      <Card className="flex items-start gap-4">
        <Construction className="h-6 w-6 text-[hsl(var(--gold))]" />
        <div>
          <p className="font-semibold">Coming soon</p>
          <p data-testid="module-message" className="mt-1 text-sm text-muted-foreground">{msg}</p>
        </div>
      </Card>
    </div>
  );
}

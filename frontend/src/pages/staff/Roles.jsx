import { useEffect, useState } from "react";
import { Check, Minus } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http } from "@/lib/api";
import { Card, PageHeader } from "@/components/portal/ui";

export default function RolesPage() {
  const [d, setD] = useState(null);
  useEffect(() => { http.get("/admin/roles").then((r) => setD(r.data)); }, []);
  return (
    <div data-testid="roles-page">
      <PageHeader eyebrow="Access control" title="Roles & permissions" description="Enforced on the server for every API call. The menu only reflects what the server allows." />
      <Card className="overflow-x-auto p-0">
        <Table data-testid="permission-matrix-table">
          <TableHeader>
            <TableRow>
              <TableHead className="min-w-[260px]">Permission</TableHead>
              {d?.roles.map((r) => <TableHead key={r.key} className="text-center text-xs">{r.label}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {d?.permissions.map((p) => (
              <TableRow key={p.key}>
                <TableCell><p className="font-mono text-xs">{p.key}</p><p className="text-xs text-muted-foreground">{p.description}</p></TableCell>
                {d.roles.map((r) => (
                  <TableCell key={r.key} className="text-center">
                    {r.permissions.includes(p.key) ? <Check aria-label="granted" className="mx-auto h-4 w-4 text-emerald-600" /> : <Minus aria-label="not granted" className="mx-auto h-4 w-4 text-slate-300" />}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

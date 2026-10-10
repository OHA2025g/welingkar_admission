import { useCallback, useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtINR, downloadFile } from "@/lib/api";

const inr = (paise) => fmtINR((paise || 0) / 100);

export const DailySheet = () => {
  const [on, setOn] = useState("");
  const [sheet, setSheet] = useState(null);
  const load = useCallback((day) => {
    const q = day ? `?on=${day}` : "";
    return http.get(`/accounts/daily-sheet${q}`).then((r) => { setSheet(r.data); if (!day) setOn(r.data.date); });
  }, []);
  useEffect(() => { load(); }, [load]);
  const exp = async () => {
    try { await downloadFile(`/accounts/daily-sheet/export?on=${on}`, `collections-${on}.xlsx`); toast.success("Daily sheet downloaded"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (!sheet) return null;
  const rows = sheet.programmes;
  const t = sheet.totals;
  return (
    <div data-testid="daily-sheet">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input data-testid="daily-sheet-date" type="date" className="w-44" value={on} onChange={(e) => { setOn(e.target.value); load(e.target.value); }} />
        <Button data-testid="daily-sheet-download" variant="outline" onClick={exp}><Download className="mr-1.5 h-4 w-4" />Download sheet</Button>
      </div>
      <Table data-testid="daily-sheet-table">
        <TableHeader><TableRow>{["Programme", "Collections", "Collected", "Refunds", "Refunded"].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.program_code} data-testid={`daily-sheet-row-${r.program_code}`}>
              <TableCell>{r.program_code}</TableCell>
              <TableCell className="tabular-nums">{r.collected_count}</TableCell>
              <TableCell className="tabular-nums">{inr(r.collected_paise)}</TableCell>
              <TableCell className="tabular-nums">{r.refunded_count}</TableCell>
              <TableCell className="tabular-nums">{inr(r.refunded_paise)}</TableCell>
            </TableRow>
          ))}
          <TableRow data-testid="daily-sheet-total">
            <TableCell className="font-semibold">Total</TableCell>
            <TableCell className="tabular-nums font-semibold">{t.collected_count}</TableCell>
            <TableCell className="tabular-nums font-semibold">{inr(t.collected_paise)}</TableCell>
            <TableCell className="tabular-nums font-semibold">{t.refunded_count}</TableCell>
            <TableCell className="tabular-nums font-semibold">{inr(t.refunded_paise)}</TableCell>
          </TableRow>
          {!rows.length && <TableRow><TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">No collections or refunds on this day.</TableCell></TableRow>}
        </TableBody>
      </Table>
    </div>
  );
};

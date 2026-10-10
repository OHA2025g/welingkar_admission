import { fmtINR } from "@/lib/api";

export function ProgrammeCompare({ programs = [], admissionFee, applicationFee }) {
  if (!programs.length) return null;
  return (
    <div className="mt-8 overflow-x-auto">
      <table data-testid="programme-compare" className="w-full min-w-[36rem] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
            {["Programme", "Campus", "Seats", "Application fee", "PI"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {programs.map((p) => (
            <tr key={p.code || p.id} data-testid={`programme-compare-${p.code}`} className="border-b border-border">
              <td className="px-3 py-3 font-medium">{p.name}<div className="font-mono text-xs text-muted-foreground">{p.code}</div></td>
              <td className="px-3 py-3">{p.campus}</td>
              <td className="px-3 py-3 tabular-nums">{p.seat_capacity}</td>
              <td className="px-3 py-3 tabular-nums">{fmtINR(p.application_fee_inr ?? applicationFee)}</td>
              <td className="px-3 py-3">{(p.stages || []).includes("pi") ? "Required" : "Not required"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {admissionFee != null && <p className="mt-2 text-xs text-muted-foreground">Admission fee after a seat is allotted: {fmtINR(admissionFee)}.</p>}
    </div>
  );
}

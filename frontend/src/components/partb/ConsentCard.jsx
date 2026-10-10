import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { http, errMsg, fmtIST } from "@/lib/api";
import { Card, StatusPill } from "@/components/portal/ui";

const sel = "h-9 rounded-md border border-input bg-background px-3 text-sm";

export const ConsentCard = ({ data, onSaved }) => {
  const eligible = data.courses.filter((c) => c.outcome !== "rejected");
  const [courses, setCourses] = useState(Object.fromEntries(eligible.map((c) => [c.program_code, "accept"])));
  const [overall, setOverall] = useState(false);
  const save = async () => {
    try { await http.post("/candidate/partb/consent", { courses, overall }); toast.success("Consent recorded"); onSaved(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  if (data.consent) {
    return (
      <Card testId="consent-recorded">
        <p className="font-semibold">Consent recorded <span className="text-xs text-muted-foreground">v{data.consent.version} · {fmtIST(data.consent.created_at)}</span></p>
        <ul className="mt-2 space-y-1 text-sm">{Object.entries(data.consent.courses).map(([k, v]) => <li key={k}>{k}: <StatusPill status={v === "accept" ? "active" : "denied"} label={v} /></li>)}</ul>
        <p className="mt-2 text-xs text-muted-foreground">Overall admission consent given. Changes go through the admissions office (audited).</p>
      </Card>
    );
  }
  return (
    <Card testId="consent-form">
      <p className="font-semibold">Course & admission consent</p>
      <p className="mt-1 text-sm text-muted-foreground">Respond to each course, then give overall admission consent to unlock document upload.</p>
      <div className="mt-4 space-y-3">
        {eligible.map((c) => (
          <label key={c.program_code} className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <span>{c.program_name} <span className="text-xs text-muted-foreground">({c.outcome})</span></span>
            <select data-testid={`consent-course-${c.program_code}`} className={sel} value={courses[c.program_code]} onChange={(e) => setCourses({ ...courses, [c.program_code]: e.target.value })}>
              <option value="accept">Accept</option><option value="decline">Decline</option>
            </select>
          </label>
        ))}
      </div>
      <label className="mt-5 flex items-start gap-2 text-sm"><Checkbox data-testid="consent-overall-checkbox" checked={overall} onCheckedChange={(v) => setOverall(!!v)} />
        I give my overall consent for admission to WeSchool for the accepted courses and agree to the counselling rules.</label>
      <Button className="mt-4" data-testid="consent-submit-button" onClick={save}>Submit consent</Button>
    </Card>
  );
};

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarDays, MapPin, Users2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { http, fmtDate, fmtINR } from "@/lib/api";
import { BrandMark } from "@/components/portal/ui";
import { ProgrammeCompare } from "@/components/portal/ProgrammeCompare";
import { HERO_IMG } from "@/components/portal/AuthLayout";

export default function Landing() {
  const [data, setData] = useState(null);
  useEffect(() => { http.get("/public/portal").then((r) => setData(r.data)); }, []);
  const c = data?.cycle;
  const dates = c ? [["Applications open", c.application_open], ["Applications close", c.application_close],
    ["Part B counselling opens", c.part_b_open], ["Part B closes", c.part_b_close]] : [];

  return (
    <div data-testid="landing-page" className="min-h-screen bg-background">
      <div className="h-1 bg-primary" />
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-8">
        <BrandMark />
        <nav className="flex items-center gap-2">
          <Button asChild variant="ghost" size="sm"><Link data-testid="landing-staff-login-link" to="/staff/login">Staff</Link></Button>
          <Button asChild variant="outline" size="sm"><Link data-testid="landing-login-link" to="/candidate/login">Candidate login</Link></Button>
        </nav>
      </header>

      <section className="mx-auto grid max-w-7xl gap-10 px-4 pb-16 pt-8 sm:px-8 lg:grid-cols-12 lg:pt-14">
        <div className="lg:col-span-6">
          <p data-testid="landing-cycle-badge" className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Admissions {c?.code || ""} · Now open
          </p>
          <h1 className="mt-4 text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
            Build the next chapter at <span className="text-primary">WeSchool</span>.
          </h1>
          <p className="mt-6 max-w-xl text-base text-muted-foreground sm:text-lg">
            Apply to the PGDM and MMS programmes of Welingkar Institute of Management. Register once, verify your email and WhatsApp, and track every step of your admission here.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg" className="rounded-full px-7"><Link data-testid="landing-register-button" to="/candidate/register">Start application <ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
            <Button asChild size="lg" variant="outline" className="rounded-full px-7"><Link to="/candidate/login">I have an account</Link></Button>
          </div>
          {c && <p className="mt-6 text-sm text-muted-foreground">Application fee <span className="font-semibold text-foreground">{fmtINR(c.application_fee_inr)}</span> · payable after verification</p>}
        </div>
        <div className="relative lg:col-span-6">
          <img src={HERO_IMG} alt="Students on the WeSchool campus" className="aspect-[4/3] w-full rounded-md object-cover" />
          <div className="absolute -bottom-6 left-6 right-6 rounded-md border border-border bg-card p-5 shadow-lg sm:left-auto sm:w-80">
            <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground"><CalendarDays className="h-4 w-4 text-primary" />Important dates</p>
            <ul className="mt-3 space-y-2 text-sm">
              {dates.filter(([, d]) => d).map(([l, d]) => (
                <li key={l} className="flex justify-between gap-4"><span className="text-muted-foreground">{l}</span><span className="font-medium">{fmtDate(d)}</span></li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="border-t border-border bg-card">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-8">
          <div className="flex flex-col justify-between gap-2 md:flex-row md:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">Programmes</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight sm:text-3xl">Choose your route</h2>
            </div>
            <p className="text-sm text-muted-foreground">{data?.programs?.length || 0} programmes in cycle {c?.code}</p>
          </div>
          <div data-testid="landing-programs-list" className="mt-8 grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {data?.programs?.map((p) => (
              <div key={p.id} className="bg-card p-6 transition-colors duration-200 hover:bg-accent">
                <p className="text-xs font-semibold uppercase tracking-wider text-primary">{p.route}</p>
                <h3 className="mt-2 text-lg font-semibold">{p.name}</h3>
                <div className="mt-4 flex gap-5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" />{p.campus}</span>
                  <span className="flex items-center gap-1.5"><Users2 className="h-3.5 w-3.5" />{p.seat_capacity} seats</span>
                  <span>{p.duration_months} months</span>
                </div>
              </div>
            ))}
          </div>
          <ProgrammeCompare programs={data?.programs} applicationFee={c?.application_fee_inr} admissionFee={c?.admission_fee_inr} />
        </div>
      </section>
      <footer className="mx-auto max-w-7xl px-4 py-8 text-xs text-muted-foreground sm:px-8">
        Welingkar Institute of Management Development & Research · Times shown in IST · Fees in INR
      </footer>
    </div>
  );
}

import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, Info, FileText, CreditCard, ClipboardCheck, LogOut, CalendarClock, Trophy, Armchair, Wallet, Ban } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { BrandMark } from "@/components/portal/ui";
import { NotificationBell } from "@/components/portal/NotificationBell";

const NAV = [
  { to: "/candidate/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/candidate/admission-info", label: "Admission info", icon: Info },
  { to: "/candidate/application", label: "Application form", icon: FileText, verified: true },
  { to: "/candidate/payment", label: "Fee & invoice", icon: CreditCard, verified: true },
  { to: "/candidate/after-submission", label: "After submission", icon: ClipboardCheck, verified: true },
  { to: "/candidate/interviews", label: "Interviews", icon: CalendarClock, verified: true },
  { to: "/candidate/results", label: "Results", icon: Trophy },
  { to: "/candidate/part-b", label: "Part B", icon: Armchair },
  { to: "/candidate/admission-fee", label: "Admission fee", icon: Wallet },
  { to: "/candidate/cancellation", label: "Cancellation", icon: Ban },
];

export default function CandidateShell() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const verified = user.identity_status === "verified";
  return (
    <div className="min-h-screen bg-background">
      <div className="h-1 bg-primary" />
      <header className="sticky top-0 z-20 border-b border-border bg-card/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-8">
          <BrandMark to="/candidate/dashboard" />
          <div className="flex items-center gap-3">
            <NotificationBell />
            <span data-testid="candidate-header-name" className="hidden text-sm sm:inline">{user.name} · <span className="font-mono text-xs text-muted-foreground">{user.candidate_ref}</span></span>
            <Button data-testid="candidate-logout-button" variant="outline" size="sm" onClick={async () => { await logout(); nav("/candidate/login"); }}><LogOut className="mr-1.5 h-4 w-4" />Sign out</Button>
          </div>
        </div>
        <nav aria-label="Candidate navigation" className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-4 pb-1 sm:px-8">
          {NAV.filter((n) => !n.verified || verified).map((n) => (
            <NavLink key={n.to} to={n.to} data-testid={`candidate-nav-${n.to.split("/").pop()}`}
              className={({ isActive }) => `flex min-h-11 shrink-0 items-center gap-2 border-b-2 px-3 py-2.5 text-sm transition-colors duration-150 ${isActive ? "border-primary font-semibold text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              <n.icon className="h-4 w-4" />{n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8 pb-24 sm:px-8 sm:py-10"><Outlet /></main>
    </div>
  );
}

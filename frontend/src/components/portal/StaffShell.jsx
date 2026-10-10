import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LogOut, Menu, Timer, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet";
import { useAuth, can } from "@/context/AuthContext";
import { STAFF_MENU } from "@/lib/menu";
import { mmss } from "@/lib/api";
import { BrandMark, RolePill } from "./ui";
import { NotificationBell } from "./NotificationBell";
import { ChangePasswordDialog } from "./ChangePasswordDialog";

const SessionTimer = () => {
  const { user, lastActivity, logout } = useAuth();
  const [left, setLeft] = useState(user.idle_minutes * 60);
  useEffect(() => {
    const t = setInterval(() => {
      const s = Math.max(0, Math.round(user.idle_minutes * 60 - (Date.now() - lastActivity.current) / 1000));
      setLeft(s);
      if (s === 0) logout(`Signed out after ${user.idle_minutes} minutes of inactivity.`);
    }, 1000);
    return () => clearInterval(t);
  }, [user, lastActivity, logout]);
  return (
    <span data-testid="session-idle-timer" title="Idle session timeout" className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-xs tabular-nums ${left < 120 ? "border-red-300 bg-red-50 text-red-700" : "border-border text-muted-foreground"}`}>
      <Timer className="h-3.5 w-3.5" /> {mmss(left)}
    </span>
  );
};

const Nav = ({ onNavigate }) => {
  const { user } = useAuth();
  return (
    <nav aria-label="Staff navigation" className="space-y-0.5">
      {STAFF_MENU.filter((m) => !m.perm || can(user, m.perm)).map((m) => (
        <NavLink key={m.to} to={m.to} onClick={onNavigate} data-testid={`nav-${m.to.split("/").pop()}`}
          className={({ isActive }) => `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 ${isActive ? "bg-white/10 font-semibold text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}>
          <m.icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />{m.label}
        </NavLink>
      ))}
    </nav>
  );
};

const Sidebar = ({ onNavigate }) => (
  <div className="flex h-full flex-col bg-[hsl(var(--navy))] px-4 py-6">
    <div className="px-2"><BrandMark to="/staff/dashboard" light /></div>
    <p className="mt-8 px-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">Staff console</p>
    <div className="mt-3 flex-1 overflow-y-auto"><Nav onNavigate={onNavigate} /></div>
    <p className="px-3 text-[11px] text-slate-500">Cycle 2026-28 · Asia/Kolkata</p>
  </div>
);

export default function StaffShell() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState(false);
  const out = async () => { await logout(); nav("/staff/login"); };
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 lg:block"><Sidebar /></aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-border bg-card/90 px-4 backdrop-blur-md sm:px-8">
          <div className="flex items-center gap-3">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button data-testid="mobile-menu-button" variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu"><Menu className="h-5 w-5" /></Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-72 border-0 p-0"><SheetTitle className="sr-only">Menu</SheetTitle><Sidebar onNavigate={() => setOpen(false)} /></SheetContent>
            </Sheet>
            <RolePill testId="topbar-role-badge" role={user.role} label={user.role_label} />
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <NotificationBell />
            <SessionTimer />
            <span data-testid="topbar-user-name" className="hidden text-sm font-medium sm:inline">{user.name}</span>
            <Button data-testid="change-password-button" variant="ghost" size="icon" onClick={() => setPw(true)} aria-label="Change password"><KeyRound className="h-4 w-4" /></Button>
            <Button data-testid="logout-button" variant="outline" size="sm" onClick={out}><LogOut className="mr-1.5 h-4 w-4" />Sign out</Button>
          </div>
        </header>
        {user.must_change_password && (
          <div data-testid="must-change-password-banner" className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 sm:px-8">
            You are using a temporary password. <button className="font-semibold underline" onClick={() => setPw(true)}>Change it now</button>.
          </div>
        )}
        <main className="flex-1 px-4 py-8 sm:px-8 lg:px-10"><Outlet /></main>
      </div>
      <ChangePasswordDialog open={pw} onOpenChange={setPw} />
    </div>
  );
}

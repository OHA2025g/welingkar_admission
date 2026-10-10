import { LayoutDashboard, Users, ShieldCheck, CalendarRange, GraduationCap, ScrollText, UserSquare2, ClipboardList,
  FileCheck2, Star, ClipboardCheck, Upload, UserCheck, Armchair, CalendarClock, Trophy, Wallet, BarChart3, History, Receipt, Ban, Printer, Download } from "lucide-react";

export const STAFF_MENU = [
  { to: "/staff/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/staff/users", label: "Users", icon: Users, perm: "users.manage" },
  { to: "/staff/roles", label: "Roles & permissions", icon: ShieldCheck, perm: "roles.read" },
  { to: "/staff/cycles", label: "Admission cycles", icon: CalendarRange, perm: "cycles.read" },
  { to: "/staff/programs", label: "Programs & seats", icon: GraduationCap, perm: "programs.read" },
  { to: "/staff/policies", label: "Policies", icon: ScrollText, perm: "policies.read" },
  { to: "/staff/candidates", label: "Candidates", icon: UserSquare2, perm: "candidates.read" },
  { to: "/staff/part-a", label: "Part A dashboard", icon: BarChart3, perm: "applications.read" },
  { to: "/staff/applications", label: "Applications", icon: ClipboardList, perm: "applications.read" },
  { to: "/staff/verification", label: "Document verification", icon: FileCheck2, perm: "documents.verify" },
  { to: "/staff/partb-imports", label: "Part B imports", icon: Upload, perm: "partb.import" },
  { to: "/staff/partb-candidates", label: "Part B candidates", icon: UserCheck, perm: "partb.read" },
  { to: "/staff/allotment", label: "Seat allotment", icon: Armchair, perm: "partb.read" },
  { to: "/staff/scoring", label: "GA / PI scoring", icon: Star, perm: "assessments.score" },
  { to: "/staff/interviews", label: "Interviews", icon: CalendarClock, perm: "interviews.manage" },
  { to: "/staff/evaluations", label: "Evaluation reports", icon: ClipboardCheck, perm: "evaluations.read" },
  { to: "/staff/results", label: "Results", icon: Trophy, perm: "results.read" },
  { to: "/staff/accounts", label: "Payments & reconciliation", icon: Receipt, perm: "payments.read" },
  { to: "/staff/cancellations", label: "Cancellations", icon: Ban, perm: ["cancellations.review", "payments.read", "partb.read"] },
  { to: "/staff/print", label: "Print centre", icon: Printer, perm: "print.center" },
  { to: "/poc", label: "Payments console", icon: Wallet, perm: "payments.read" },
  { to: "/staff/reports", label: "Reports", icon: BarChart3, perm: "reports.read" },
  { to: "/staff/audit", label: "Audit log", icon: History, perm: "audit.read" },
  { to: "/staff/download", label: "Download portal", icon: Download, perm: "users.manage" },
];

export const MODULE_INFO = {
  applications: { title: "Application worklist", perm: "applications.process", phase: 2 },
  documents: { title: "Document verification queue", perm: "documents.verify", phase: 4 },
  assessments: { title: "GA / PI scoring", perm: "assessments.score", phase: 3 },
  interviews: { title: "Interview locations, sessions & attendance", perm: "interviews.manage", phase: 3 },
  results: { title: "Result versions & publication", perm: "results.publish", phase: 3 },
  reports: { title: "Reports", perm: "reports.read", phase: 5 },
};

export const ROLE_TONE = {
  super_admin: "bg-primary/10 text-primary border-primary/30",
  auditor: "bg-slate-100 text-slate-700 border-slate-300",
  accounts_operator: "bg-emerald-50 text-emerald-800 border-emerald-200",
  candidate: "bg-amber-50 text-amber-800 border-amber-200",
};

export const INDIAN_STATES = ["Andhra Pradesh", "Assam", "Bihar", "Chhattisgarh", "Delhi", "Goa", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jammu & Kashmir", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Odisha",
  "Punjab", "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Other"];

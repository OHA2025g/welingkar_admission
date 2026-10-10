import { Link } from "react-router-dom";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

export default function AccessDenied() {
  const { user } = useAuth();
  return (
    <div data-testid="access-denied-page" className="flex min-h-[60vh] items-center px-4">
      <div className="max-w-lg">
        <ShieldAlert className="h-10 w-10 text-primary" strokeWidth={1.5} />
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.2em] text-primary">Error 403</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight">Access denied</h1>
        <p className="mt-3 text-muted-foreground">
          Your role{user?.role_label ? ` (${user.role_label})` : ""} does not have permission to view this area. The attempt has been recorded in the audit log.
        </p>
        <Button asChild className="mt-6"><Link data-testid="access-denied-home-link" to={user?.home || "/"}>Go to my dashboard</Link></Button>
      </div>
    </div>
  );
}

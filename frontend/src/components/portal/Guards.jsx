import { Navigate, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth, can } from "@/context/AuthContext";
import AccessDenied from "@/pages/AccessDenied";

export const Loading = () => (
  <div className="flex min-h-[50vh] items-center justify-center text-muted-foreground" data-testid="loading-state">
    <Loader2 className="h-6 w-6 animate-spin" />
  </div>
);

export const RequireStaff = ({ children }) => {
  const { user } = useAuth();
  const loc = useLocation();
  if (user === null) return <Loading />;
  if (!user) return <Navigate to="/staff/login" state={{ from: loc.pathname }} replace />;
  if (user.role === "candidate") return <AccessDenied />;
  return children;
};

export const RequireCandidate = ({ children }) => {
  const { user } = useAuth();
  if (user === null) return <Loading />;
  if (!user) return <Navigate to="/candidate/login" replace />;
  if (user.role !== "candidate") return <AccessDenied />;
  return children;
};

export const RequirePerm = ({ perm, children }) => {
  const { user } = useAuth();
  if (user === null) return <Loading />;
  if (!user) return <Navigate to="/staff/login" replace />;
  return can(user, perm) ? children : <AccessDenied />;
};

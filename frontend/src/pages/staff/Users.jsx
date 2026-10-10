import { useCallback, useEffect, useState } from "react";
import { Plus, Pencil, KeyRound, Copy } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { http, errMsg, fmtIST } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { PageHeader, RolePill, StatusPill, Card } from "@/components/portal/ui";

const useRoles = () => {
  const [roles, setRoles] = useState([]);
  useEffect(() => { http.get("/admin/roles").then((r) => setRoles(r.data.roles.filter((x) => x.key !== "candidate"))); }, []);
  return roles;
};

const UserDialog = ({ open, onClose, roles, editing, onSaved }) => {
  const [f, setF] = useState({ name: "", email: "", role: "", status: "active" });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setF(editing ? { name: editing.name, email: editing.email, role: editing.role, status: editing.status } : { name: "", email: "", role: "", status: "active" }); }, [open, editing]);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      if (editing) { await http.patch(`/admin/users/${editing.id}`, { name: f.name, role: f.role, status: f.status }); toast.success("User updated"); onSaved(); }
      else { const { data } = await http.post("/admin/users", { name: f.name, email: f.email, role: f.role }); onSaved(data.temporary_password, data.user.email); }
      onClose();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent data-testid="user-dialog">
        <DialogHeader><DialogTitle>{editing ? "Edit staff user" : "Add staff user"}</DialogTitle></DialogHeader>
        <form onSubmit={save} className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="u-name">Name</Label><Input id="u-name" data-testid="user-name-input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
          <div className="space-y-1.5"><Label htmlFor="u-email">Email</Label><Input id="u-email" data-testid="user-email-input" type="email" value={f.email} disabled={!!editing} onChange={(e) => setF({ ...f, email: e.target.value })} required /></div>
          <div className="space-y-1.5"><Label>Role</Label>
            <Select value={f.role} onValueChange={(v) => setF({ ...f, role: v })}>
              <SelectTrigger data-testid="user-role-select"><SelectValue placeholder="Select role" /></SelectTrigger>
              <SelectContent>{roles.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}</SelectContent>
            </Select></div>
          {editing && <div className="space-y-1.5"><Label>Status</Label>
            <Select value={f.status} onValueChange={(v) => setF({ ...f, status: v })}>
              <SelectTrigger data-testid="user-status-select"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="active">Active</SelectItem><SelectItem value="disabled">Disabled</SelectItem></SelectContent>
            </Select></div>}
          <Button data-testid="user-save-button" type="submit" className="w-full" disabled={busy || !f.role || !f.name}>{editing ? "Save changes" : "Create user"}</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default function UsersPage() {
  const { user: me } = useAuth();
  const roles = useRoles();
  const [users, setUsers] = useState([]);
  const [role, setRole] = useState("all");
  const [q, setQ] = useState("");
  const [dialog, setDialog] = useState(null);
  const [secret, setSecret] = useState(null);

  const load = useCallback(() => {
    http.get("/admin/users", { params: { ...(role !== "all" ? { role } : {}), ...(q ? { q } : {}) } }).then((r) => setUsers(r.data));
  }, [role, q]);
  useEffect(() => { load(); }, [load]);

  const reset = async (u) => {
    try { const { data } = await http.post(`/admin/users/${u.id}/reset-password`); setSecret({ email: u.email, pw: data.temporary_password }); }
    catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div data-testid="users-page">
      <PageHeader eyebrow="Super Admin" title="Staff users" description="Create staff accounts and assign exactly one role. Role changes and disabling end the user's active sessions."
        actions={<Button data-testid="add-user-button" onClick={() => setDialog({})}><Plus className="mr-1.5 h-4 w-4" />Add user</Button>} />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row">
        <Input data-testid="users-search-input" placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} className="sm:max-w-xs" />
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger data-testid="users-role-filter" className="sm:w-56"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="all">All roles</SelectItem>{roles.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Card className="overflow-x-auto p-0">
        <Table data-testid="users-table">
          <TableHeader><TableRow>{["Name", "Email", "Role", "Status", "Last sign-in", ""].map((h) => <TableHead key={h}>{h}</TableHead>)}</TableRow></TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id} data-testid={`user-row-${u.id}`}>
                <TableCell className="font-medium">{u.name}{u.id === me.id && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}</TableCell>
                <TableCell className="text-sm">{u.email}</TableCell>
                <TableCell><RolePill role={u.role} label={u.role_label} /></TableCell>
                <TableCell><StatusPill status={u.status} /></TableCell>
                <TableCell className="text-xs text-muted-foreground">{fmtIST(u.last_login_at)}</TableCell>
                <TableCell className="whitespace-nowrap text-right">
                  <Button data-testid={`edit-user-${u.id}`} variant="ghost" size="sm" onClick={() => setDialog({ editing: u })}><Pencil className="mr-1 h-3.5 w-3.5" />Edit</Button>
                  <Button data-testid={`reset-password-${u.id}`} variant="ghost" size="sm" onClick={() => reset(u)} disabled={u.id === me.id}><KeyRound className="mr-1 h-3.5 w-3.5" />Reset</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
      <UserDialog open={!!dialog} editing={dialog?.editing} roles={roles} onClose={() => setDialog(null)}
        onSaved={(pw, email) => { load(); if (pw) setSecret({ email, pw }); }} />
      <Dialog open={!!secret} onOpenChange={(o) => !o && setSecret(null)}>
        <DialogContent data-testid="temp-password-dialog">
          <DialogHeader><DialogTitle>Temporary password</DialogTitle>
            <DialogDescription>Share this securely with {secret?.email}. It is shown only once; the user must change it after signing in.</DialogDescription></DialogHeader>
          <div className="flex items-center gap-2 rounded-md border border-border bg-secondary p-3">
            <code data-testid="temp-password-value" className="flex-1 font-mono text-base">{secret?.pw}</code>
            <Button variant="ghost" size="icon" aria-label="Copy" onClick={() => { navigator.clipboard?.writeText(secret.pw); toast.success("Copied"); }}><Copy className="h-4 w-4" /></Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

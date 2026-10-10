import { useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { http, errMsg } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export const ChangePasswordDialog = ({ open, onOpenChange }) => {
  const { refresh } = useAuth();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await http.post("/auth/change-password", { current_password: cur, new_password: next });
      toast.success("Password changed");
      setCur(""); setNext(""); onOpenChange(false); refresh();
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="change-password-dialog">
        <DialogHeader><DialogTitle>Change password</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5"><Label htmlFor="cp-cur">Current password</Label>
            <Input id="cp-cur" data-testid="change-password-current-input" type="password" value={cur} onChange={(e) => setCur(e.target.value)} required /></div>
          <div className="space-y-1.5"><Label htmlFor="cp-new">New password</Label>
            <Input id="cp-new" data-testid="change-password-new-input" type="password" value={next} onChange={(e) => setNext(e.target.value)} required />
            <p className="text-xs text-muted-foreground">At least 8 characters with letters and numbers.</p></div>
          <Button data-testid="change-password-submit-button" type="submit" disabled={busy} className="w-full">Update password</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};

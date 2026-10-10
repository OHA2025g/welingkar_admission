import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { http, errMsg } from "@/lib/api";

const today = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });

// Shared by candidates (txn reference + optional proof) and Accounts (record offline, proof required).
export const OfflinePaymentForm = ({ modes, endpoint, extra = {}, proofRequired, onDone, prefix }) => {
  const [mode, setMode] = useState(modes[0]);
  const [ref, setRef] = useState("");
  const [date, setDate] = useState(today());
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    const fd = new FormData();
    Object.entries({ mode, txn_ref: ref, txn_date: date, ...extra }).forEach(([k, v]) => fd.append(k, v));
    if (file) fd.append("proof", file);
    try { await http.post(endpoint, fd); toast.success("Offline payment submitted"); setRef(""); setFile(null); onDone?.(); }
    catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} data-testid={`${prefix}-offline-form`} className="grid gap-3 sm:grid-cols-2">
      <div><Label>Mode</Label>
        <Select value={mode} onValueChange={setMode}>
          <SelectTrigger data-testid={`${prefix}-offline-mode`}><SelectValue /></SelectTrigger>
          <SelectContent>{modes.map((m) => <SelectItem key={m} value={m}>{m.toUpperCase()}</SelectItem>)}</SelectContent>
        </Select></div>
      <div><Label>Transaction reference</Label><Input data-testid={`${prefix}-offline-txn-ref`} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="UTR / DD number" /></div>
      <div><Label>Transaction date</Label><Input data-testid={`${prefix}-offline-txn-date`} type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
      <div><Label>Proof (PDF/JPG/PNG, ≤2 MB){proofRequired ? "" : " — optional"}</Label>
        <Input data-testid={`${prefix}-offline-proof`} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] || null)} /></div>
      <Button type="submit" data-testid={`${prefix}-offline-submit`} disabled={busy || ref.trim().length < 6 || (proofRequired && !file)} className="sm:col-span-2">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Submit offline payment"}
      </Button>
    </form>
  );
};

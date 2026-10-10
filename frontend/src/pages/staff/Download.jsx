import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, PageHeader } from "@/components/portal/ui";
import { fmtIST, http, errMsg } from "@/lib/api";

const STEPS = [
  "Install Python 3.11, Node 18+ with Yarn, and MongoDB.",
  "Unzip, then in backend/: create a venv, pip install -r requirements.txt, copy .env.example to .env, run uvicorn server:app --port 8001.",
  "In frontend/: copy .env.example to .env (REACT_APP_BACKEND_URL=http://localhost:8001), yarn install, yarn start.",
  "The backend seeds demo data on first start, or restore seed/weschool-seed.archive.gz with mongorestore.",
  "Without hosted email and storage keys: email runs in console mode and uploads go to local disk. Use your own Stripe test key. Details are in README_LOCAL.md.",
];

const mb = (b) => `${(b / 1024 / 1024).toFixed(1)} MB`;

export default function DownloadPage() {
  const [meta, setMeta] = useState(undefined);
  const [snaps, setSnaps] = useState([]);
  const [phrase, setPhrase] = useState("");
  const [pick, setPick] = useState("");
  useEffect(() => { fetch(`/downloads/weschool-portal.json?t=${Date.now()}`).then((r) => (r.ok ? r.json() : null)).then(setMeta).catch(() => setMeta(null)); }, []);
  useEffect(() => { http.get("/admin/snapshots").then((r) => setSnaps(r.data)).catch(() => setSnaps([])); }, []);
  const create = async () => {
    try { const { data } = await http.post("/admin/snapshots"); setSnaps((rows) => [{ name: data.name, bytes: data.bytes }, ...rows]); toast.success("Snapshot saved"); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const restore = async () => {
    try { await http.post(`/admin/snapshots/${pick}/restore`, { phrase }); toast.success("Snapshot restored. Sign in again if your session was replaced."); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="download-page">
      <PageHeader eyebrow="Super Admin" title="Download the portal" description="Full source (backend + frontend), docs and a seed-data snapshot to run on your own machine. No real secrets are included." />
      <Card testId="download-card" className="max-w-3xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="font-mono text-sm">weschool-portal.zip</p>
            <p data-testid="download-size" className="text-xs text-muted-foreground">{meta === undefined ? "Checking size…" : meta ? `${mb(meta.size_bytes)} · built ${fmtIST(meta.built_at)}` : "Size unavailable"}</p>
          </div>
          <Button asChild data-testid="download-zip-button"><a href="/downloads/weschool-portal.zip" download><Download className="mr-1.5 h-4 w-4" />Download zip</a></Button>
        </div>
        <ol data-testid="download-steps" className="mt-6 list-decimal space-y-2 pl-5 text-sm">{STEPS.map((s) => <li key={s}>{s}</li>)}</ol>
      </Card>
      <Card testId="snapshot-card" className="mt-6 max-w-3xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-semibold">Database snapshot</p>
            <p className="text-xs text-muted-foreground">Passwords and bank account numbers are left out. Restore replaces application data and keeps passwords for accounts that already exist.</p>
          </div>
          <Button data-testid="snapshot-create" onClick={create}>Save snapshot</Button>
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {snaps.map((s) => (
            <li key={s.name} className="flex items-center justify-between gap-3">
              <button type="button" className={`font-mono text-xs ${pick === s.name ? "font-semibold text-primary" : ""}`} onClick={() => setPick(s.name)}>{s.name}</button>
              <a className="text-xs text-primary" href={`/api/admin/snapshots/${s.name}`}>Download</a>
            </li>
          ))}
          {!snaps.length && <li className="text-muted-foreground">No snapshots yet.</li>}
        </ul>
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <Input data-testid="snapshot-phrase" placeholder="Type RESTORE WECHOOL" value={phrase} onChange={(e) => setPhrase(e.target.value)} />
          <Button variant="destructive" data-testid="snapshot-restore" disabled={!pick || phrase !== "RESTORE WECHOOL"} onClick={restore}>Restore</Button>
        </div>
      </Card>
    </div>
  );
}

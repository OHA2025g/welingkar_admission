import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { http } from "@/lib/api";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState({ unread: 0, items: [] });
  const load = () => http.get("/notifications").then((r) => setNotes(r.data)).catch(() => {});
  useEffect(() => { load(); }, []);
  const read = async () => {
    const { data } = await http.post("/notifications/read-all");
    setNotes(data);
  };
  return (
    <div className="relative">
      <Button type="button" variant="ghost" size="icon" data-testid="notification-bell" aria-label="Notifications" onClick={() => setOpen((v) => !v)}>
        <Bell className="h-4 w-4" />
        {notes.unread > 0 && <span data-testid="notification-unread" className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-primary" />}
      </Button>
      {open && (
        <div data-testid="notification-panel" className="absolute right-0 z-30 mt-2 w-[min(20rem,calc(100vw-2rem))] rounded-md border border-border bg-card p-3 shadow-lg">
          <div className="mb-2 flex items-center justify-between gap-3">
            <p className="text-sm font-semibold">Notices {notes.unread > 0 ? `(${notes.unread} unread)` : ""}</p>
            {notes.unread > 0 && <button type="button" className="text-xs font-semibold text-primary" data-testid="notification-mark-read" onClick={read}>Mark read</button>}
          </div>
          {!notes.items.length ? <p className="text-sm text-muted-foreground">No notices yet.</p> : (
            <ul className="max-h-72 space-y-3 overflow-y-auto">
              {notes.items.map((n) => (
                <li key={n.id} data-testid={`notification-${n.id}`} className="text-sm">
                  <p className={`font-medium ${n.read_at ? "text-muted-foreground" : ""}`}>{n.title}</p>
                  <p className="text-xs text-muted-foreground">{n.body}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Terminal, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { http, fmtIST } from "@/lib/api";
import { Panel } from "./Panel";

const LEVEL = { success: "text-emerald-400", warning: "text-amber-400", error: "text-red-400", info: "text-sky-400" };

export const EventLog = ({ tick, delay }) => {
  const [events, setEvents] = useState([]);
  const [channel, setChannel] = useState("all");

  const load = useCallback(async () => {
    const { data } = await http.get("/poc/events", { params: channel === "all" ? {} : { channel } });
    setEvents(data);
  }, [channel]);

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [load, tick]);

  const clear = async () => { await http.delete("/poc/events"); load(); };

  return (
    <Panel testId="event-log-panel" eyebrow="Server audit stream" title="Integration events" icon={Terminal} delay={delay} className="lg:col-span-8"
      right={
        <div className="flex gap-2">
          <Select value={channel} onValueChange={setChannel}>
            <SelectTrigger data-testid="integration-event-log-filter-select" className="h-8 w-32 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {["all", "email", "whatsapp", "stripe"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button data-testid="integration-event-log-clear-button" size="sm" variant="ghost" onClick={clear} className="btn-press h-8"><Trash2 className="h-3.5 w-3.5" /></Button>
        </div>
      }>
      <div data-testid="integration-event-log-container" className="font-mono-x h-[340px] overflow-y-auto rounded-sm border border-border bg-[#05080E] p-3 text-xs leading-relaxed">
        {events.length === 0 && <p className="text-muted-foreground">Waiting for events…</p>}
        {events.map((e) => (
          <div key={e.id} className="flex gap-3 py-0.5">
            <span className="shrink-0 text-slate-500">{fmtIST(e.at).replace(" IST", "")}</span>
            <span className={`w-20 shrink-0 uppercase ${LEVEL[e.level] || ""}`}>{e.channel}</span>
            <span className="shrink-0 text-slate-400">{e.kind}</span>
            <span className="text-slate-200">{e.message}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
};

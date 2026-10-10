import { useCallback, useEffect, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { http } from "@/lib/api";
import { PageHeader } from "@/components/portal/ui";
import { LocationsTab } from "@/components/interviews/LocationsTab";
import { SessionsTab } from "@/components/interviews/SessionsTab";
import { AllocationTab } from "@/components/interviews/AllocationTab";
import { SlotReportTab } from "@/components/interviews/SlotReportTab";

export default function InterviewsPage() {
  const [locations, setLocations] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [panelists, setPanelists] = useState([]);
  const load = useCallback(() => {
    http.get("/interviews/locations").then((r) => setLocations(r.data));
    http.get("/interviews/sessions").then((r) => setSessions(r.data));
    http.get("/interviews/panelists").then((r) => setPanelists(r.data));
  }, []);
  useEffect(() => { load(); }, [load]);
  return (
    <div data-testid="interviews-page">
      <PageHeader eyebrow="Interview logistics" title="Locations, sessions & attendance" description="All times are IST. Session capacity is enforced atomically, so slots are never overbooked." />
      <Tabs defaultValue="sessions">
        <TabsList className="mb-6">
          <TabsTrigger data-testid="tab-sessions" value="sessions">Sessions</TabsTrigger>
          <TabsTrigger data-testid="tab-locations" value="locations">Locations & rooms</TabsTrigger>
          <TabsTrigger data-testid="tab-allocation" value="allocation">Allocation</TabsTrigger>
          <TabsTrigger data-testid="tab-slot-report" value="slots">Slot report</TabsTrigger>
        </TabsList>
        <TabsContent value="sessions"><SessionsTab sessions={sessions} locations={locations} panelists={panelists} reload={load} /></TabsContent>
        <TabsContent value="locations"><LocationsTab locations={locations} reload={load} /></TabsContent>
        <TabsContent value="allocation"><AllocationTab locations={locations} reload={load} /></TabsContent>
        <TabsContent value="slots"><SlotReportTab /></TabsContent>
      </Tabs>
    </div>
  );
}

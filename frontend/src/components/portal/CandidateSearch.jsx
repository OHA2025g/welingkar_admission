import { useState } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { http } from "@/lib/api";

export const CandidateSearch = ({ onPick, prefix }) => {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState(null);
  const go = async (e) => { e.preventDefault(); const { data } = await http.get("/admin/candidates/search", { params: { q } }); setHits(data); };
  return (
    <div>
      <form onSubmit={go} className="flex gap-2">
        <Input data-testid={`${prefix}-search-input`} placeholder="Application ref, candidate ID, email or name" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-md" />
        <Button type="submit" data-testid={`${prefix}-search-button`} disabled={q.trim().length < 3}><Search className="mr-1.5 h-4 w-4" />Find</Button>
      </form>
      {hits && <ul className="mt-3 flex flex-wrap gap-2">
        {hits.length === 0 && <li className="text-sm text-muted-foreground">No match.</li>}
        {hits.map((h) => <li key={h.id}><Button size="sm" variant="outline" data-testid={`${prefix}-hit-${h.id}`} onClick={() => onPick(h)}>{h.name} · {h.candidate_ref}</Button></li>)}
      </ul>}
    </div>
  );
};

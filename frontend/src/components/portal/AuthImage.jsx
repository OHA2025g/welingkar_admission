import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";
import { http } from "@/lib/api";

export const AuthImage = ({ fileId, alt, className = "", testId }) => {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    if (!fileId) return undefined;
    let u;
    http.get(`/files/${fileId}`, { responseType: "blob" }).then((r) => { u = URL.createObjectURL(r.data); setUrl(u); }).catch(() => setUrl(null));
    return () => u && URL.revokeObjectURL(u);
  }, [fileId]);
  if (!url) return <div data-testid={testId} className={`flex items-center justify-center bg-secondary text-muted-foreground ${className}`}><UserRound className="h-8 w-8" /></div>;
  return <img data-testid={testId} src={url} alt={alt} draggable={false} onContextMenu={(e) => e.preventDefault()} className={`select-none object-cover ${className}`} />;
};

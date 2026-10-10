import axios from "axios";
import { useEffect, useState } from "react";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const http = axios.create({ baseURL: API, withCredentials: true });

http.interceptors.response.use(
  (r) => r,
  (e) => {
    const code = e?.response?.data?.detail?.code;
    if (e?.response?.status === 401 && ["session_expired", "session_revoked", "account_inactive"].includes(code)) {
      window.dispatchEvent(new CustomEvent("ws:session-ended", { detail: e.response.data.detail }));
    }
    return Promise.reject(e);
  }
);

export const fmtDate = (d) =>
  d ? new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(new Date(d)) : "—";

export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return e?.message || "Request failed";
};
export const errCode = (e) => e?.response?.data?.detail?.code;

export const fmtINR = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(n || 0);

export const fmtIST = (iso) =>
  iso
    ? new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata", day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
      }).format(new Date(iso)) + " IST"
    : "—";

export const newKey = (p) => `${p}-${crypto.randomUUID()}`;

export const secondsUntil = (iso, now) => (iso ? Math.max(0, Math.ceil((new Date(iso) - now) / 1000)) : 0);
export const mmss = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

export const useNow = (ms = 1000) => {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
};

export const fetchPdfBlobUrl = async (path) => {
  const res = await http.get(path, { responseType: "blob" });
  return URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
};

export const downloadUrl = (url, filename) => {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { a.remove(); if (url.startsWith("blob:")) URL.revokeObjectURL(url); }, 5000);
};

const parseBlobError = async (e) => {
  const d = e?.response?.data;
  if (d instanceof Blob) { try { e.response.data = JSON.parse(await d.text()); } catch { /* not JSON */ } }
  return e;
};

export const downloadFile = async (path, fallbackName, params) => {
  try {
    const r = await http.get(path, { params, responseType: "blob" });
    const name = /filename="?([^";]+)"?/.exec(r.headers["content-disposition"] || "")?.[1] || fallbackName;
    const blob = new Blob([r.data], { type: r.headers["content-type"] || r.data.type || "application/octet-stream" });
    downloadUrl(URL.createObjectURL(blob), name);
    return name;
  } catch (e) { throw await parseBlobError(e); }
};

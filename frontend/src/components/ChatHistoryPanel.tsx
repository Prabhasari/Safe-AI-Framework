// frontend/src/components/ChatHistoryPanel.tsx

import { useEffect, useState } from "react";
import {
  X, Clock, Shield, ChevronRight,
  Trash2, Search, CheckCircle2, RotateCcw,
} from "lucide-react";

/* ── Exported type (used in SecureGenerator.tsx too) ─────────────────────── */
export type HistoryEntry = {
  id:             string;
  timestamp:      string;
  prompt:         string;
  code:           string;
  original_code?: string;
  fix_summary?: {
    initial_issues?:   number;
    semgrep_fixed?:    number;
    llm_fixed?:        number;
    remaining_issues?: number;
    fix_rate_percent?: number;
  };
  languages?: string[];
  decision?:  string;
  uml?: {                          // ← NEW
    class_svg?:             string | null;
    package_svg?:           string | null;
    sequence_svg?:          string | null;
    component_svg?:         string | null;
    activity_svg?:          string | null;
    ai_class_svg?:          string | null;
    ai_package_svg?:        string | null;
    ai_sequence_svg?:       string | null;
    ai_component_svg?:      string | null;
    ai_activity_svg?:       string | null;
  };
};

type Props = {
  open:      boolean;
  onClose:   () => void;
  onRestore: (entry: HistoryEntry) => void;
};

/* ── Constants ───────────────────────────────────────────────────────────── */
const API_HISTORY = "http://localhost:8000/api/history";
const LS_KEY      = "secure_gen_history";

/* ── Small helpers ───────────────────────────────────────────────────────── */
function formatTime(ts: string): string {
  try {
    const d    = new Date(ts);
    const diff = Date.now() - d.getTime();
    const mins = Math.floor(diff / 60_000);
    const hrs  = Math.floor(diff / 3_600_000);
    const days = Math.floor(diff / 86_400_000);
    if (mins <  1) return "Just now";
    if (mins < 60) return `${mins}m ago`;
    if (hrs  < 24) return `${hrs}h ago`;
    if (days <  7) return `${days}d ago`;
    return d.toLocaleDateString();
  } catch {
    return ts;
  }
}

function statusColor(entry: HistoryEntry): string {
  const r = entry.fix_summary?.fix_rate_percent ?? 100;
  if (r >= 100) return "#10b981";
  if (r >=  70) return "#f59e0b";
  return "#ef4444";
}

/* ══════════════════════════════════════════════════════════════════════════ */
export default function ChatHistoryPanel({ open, onClose, onRestore }: Props) {
  const [entries,  setEntries]  = useState<HistoryEntry[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [search,   setSearch]   = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  /* load whenever the panel opens */
  // eslint-disable-next-line react-hooks/immutability
  useEffect(() => { if (open) fetchHistory(); }, [open]);

  async function fetchHistory() {
    setLoading(true);
    try {
      const res = await fetch(API_HISTORY);
      if (res.ok) {
        const data = await res.json();
        setEntries(data.history ?? []);
        setLoading(false);
        return;
      }
    } catch { /* fall through */ }
    // localStorage fallback
    try {
      const raw = localStorage.getItem(LS_KEY);
      setEntries(raw ? JSON.parse(raw) : []);
    } catch { setEntries([]); }
    setLoading(false);
  }

  async function deleteEntry(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setDeleting(id);
    try { await fetch(`${API_HISTORY}/${id}`, { method: "DELETE" }); } catch { /**/ }
    const updated = entries.filter((en) => en.id !== id);
    setEntries(updated);
    try { localStorage.setItem(LS_KEY, JSON.stringify(updated)); } catch { /**/ }
    setDeleting(null);
  }

  async function clearAll() {
    if (!confirm("Clear all generation history?")) return;
    try { await fetch(API_HISTORY, { method: "DELETE" }); } catch { /**/ }
    setEntries([]);
    try { localStorage.removeItem(LS_KEY); } catch { /**/ }
  }

  const filtered = entries.filter((e) =>
    e.prompt.toLowerCase().includes(search.toLowerCase())
  );

  if (!open) return null;

  /* ── Render ─────────────────────────────────────────────────────────── */
  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0,
          background: "rgba(0,0,0,0.55)",
          zIndex: 200, backdropFilter: "blur(3px)",
        }}
      />

      {/* Slide-in panel */}
      <div
        style={{
          position: "fixed", top: 0, right: 0, bottom: 0, width: 440,
          background: "#13111e", borderLeft: "1px solid #2d2a3d",
          zIndex: 201, display: "flex", flexDirection: "column",
          animation: "hp-slide 0.25s cubic-bezier(0.16,1,0.3,1)",
        }}
      >
        <style>{`
          @keyframes hp-slide {
            from { transform: translateX(100%); opacity: 0; }
            to   { transform: translateX(0);    opacity: 1; }
          }
          .hp-row:hover  { background: #1a1730 !important; }
          .hp-row:hover .hp-del { opacity: 1 !important; }
          .hp-del { opacity: 0; transition: opacity .15s; }
        `}</style>

        {/* ── Header ── */}
        <div style={{
          padding: "18px 20px 16px", borderBottom: "1px solid #2d2a3d",
          background: "#1a1730", display: "flex", alignItems: "center",
          justifyContent: "space-between", flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 34, height: 34, borderRadius: 9, flexShrink: 0,
              background: "linear-gradient(135deg,#6366f1,#8b5cf6)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Clock size={17} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0" }}>
                Generation History
              </div>
              <div style={{ fontSize: 11, color: "#64748b", marginTop: 1 }}>
                {entries.length} saved session{entries.length !== 1 ? "s" : ""}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            {entries.length > 0 && (
              <button onClick={clearAll} style={{
                padding: "6px 11px", borderRadius: 7, border: "1px solid #3d3a50",
                background: "transparent", color: "#ef4444", fontSize: 11,
                fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
              }}>
                <Trash2 size={12} /> Clear All
              </button>
            )}
            <button onClick={onClose} style={{
              width: 32, height: 32, borderRadius: 8, border: "1px solid #2d2a3d",
              background: "transparent", color: "#94a3b8", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
            }}>
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── Search ── */}
        <div style={{ padding: "12px 16px", borderBottom: "1px solid #1e1b2e", flexShrink: 0 }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 13px", background: "#0f0d1a",
            borderRadius: 8, border: "1px solid #2d2a3d",
          }}>
            <Search size={13} color="#475569" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search history…"
              style={{ flex: 1, background: "none", border: "none", outline: "none", color: "#94a3b8", fontSize: 13 }}
            />
            {search && (
              <button onClick={() => setSearch("")}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0, color: "#475569" }}>
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        {/* ── List ── */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {loading ? (
            <div style={{ padding: 48, textAlign: "center", color: "#475569", fontSize: 13 }}>
              Loading history…
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: 56, textAlign: "center" }}>
              <Clock size={36} color="#2d2a3d" style={{ display: "block", margin: "0 auto 14px" }} />
              <div style={{ fontSize: 14, fontWeight: 600, color: "#475569" }}>
                {search ? "No results found" : "No history yet"}
              </div>
              <div style={{ fontSize: 12, color: "#334155", marginTop: 5 }}>
                {search ? "Try a different search" : "Generated code will appear here"}
              </div>
            </div>
          ) : (
            filtered.map((entry) => {
              const isOpen = expanded === entry.id;
              const sc     = statusColor(entry);

              return (
                <div key={entry.id} style={{ borderBottom: "1px solid #1a1730" }}>

                  {/* Row */}
                  <div
                    className="hp-row"
                    onClick={() => setExpanded(isOpen ? null : entry.id)}
                    style={{
                      padding: "13px 16px", cursor: "pointer",
                      background: isOpen ? "#1a1730" : "transparent",
                      transition: "background .15s",
                      display: "flex", gap: 10, alignItems: "flex-start",
                    }}
                  >
                    {/* status dot */}
                    <div style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: sc, boxShadow: `0 0 6px ${sc}70`,
                      marginTop: 5, flexShrink: 0,
                    }} />

                    {/* text */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13, fontWeight: 500, color: "#e2e8f0",
                        lineHeight: 1.4, whiteSpace: "nowrap",
                        overflow: "hidden", textOverflow: "ellipsis",
                      }}>
                        {entry.prompt}
                      </div>

                      {/* chips */}
                      <div style={{ display: "flex", gap: 8, marginTop: 5, alignItems: "center", flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, color: "#475569" }}>
                          {formatTime(entry.timestamp)}
                        </span>

                        {(entry.languages ?? []).length > 0 && (
                          <span style={{
                            fontSize: 10, color: "#8b5cf6",
                            background: "rgba(139,92,246,.12)",
                            padding: "2px 7px", borderRadius: 4,
                            fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em",
                          }}>
                            {entry.languages![0]}
                          </span>
                        )}

                        {(entry.fix_summary?.initial_issues ?? 0) > 0 && (
                          <span style={{ fontSize: 11, color: sc, display: "flex", alignItems: "center", gap: 3 }}>
                            <Shield size={10} />
                            {entry.fix_summary!.fix_rate_percent?.toFixed(0)}% fixed
                          </span>
                        )}

                        {(entry.fix_summary?.initial_issues ?? 0) === 0 && (
                          <span style={{ fontSize: 11, color: "#10b981", display: "flex", alignItems: "center", gap: 3 }}>
                            <CheckCircle2 size={10} /> Clean
                          </span>
                        )}
                      </div>
                    </div>

                    {/* icons */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <button
                        className="hp-del"
                        onClick={(e) => deleteEntry(entry.id, e)}
                        disabled={deleting === entry.id}
                        title="Delete entry"
                        style={{
                          width: 26, height: 26, borderRadius: 6, border: "1px solid #2d2a3d",
                          background: "transparent", color: "#ef4444", cursor: "pointer",
                          display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                      <ChevronRight
                        size={14} color="#475569"
                        style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0)", transition: "transform .2s" }}
                      />
                    </div>
                  </div>

                  {/* Expanded section */}
                  {isOpen && (
                    <div style={{ background: "#0f0d1a", padding: "14px 16px 18px" }}>

                      {/* stats */}
                      {(entry.fix_summary?.initial_issues ?? 0) > 0 && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 14 }}>
                          {[
                            { label: "Initial",   val: entry.fix_summary!.initial_issues,  color: "#ef4444" },
                            {
                              label: "Fixed",
                              val: (entry.fix_summary!.semgrep_fixed ?? 0) + (entry.fix_summary!.llm_fixed ?? 0),
                              color: "#10b981",
                            },
                            {
                              label: "Remaining",
                              val:   entry.fix_summary!.remaining_issues,
                              color: (entry.fix_summary!.remaining_issues ?? 0) === 0 ? "#10b981" : "#f59e0b",
                            },
                          ].map(({ label, val, color }) => (
                            <div key={label} style={{
                              padding: "9px 10px", background: "#13111e",
                              borderRadius: 8, border: "1px solid #2d2a3d", textAlign: "center",
                            }}>
                              <div style={{ fontSize: 20, fontWeight: 700, color }}>{val}</div>
                              <div style={{ fontSize: 10, color: "#475569", marginTop: 3 }}>{label}</div>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* code preview */}
                      <div style={{
                        fontSize: 10, color: "#475569", fontWeight: 600,
                        textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6,
                      }}>
                        Code Preview
                      </div>
                      <div style={{ position: "relative", marginBottom: 14 }}>
                        <pre style={{
                          margin: 0, padding: "10px 12px", background: "#0a0910",
                          borderRadius: 7, border: "1px solid #2d2a3d",
                          fontSize: 11, color: "#64748b", maxHeight: 110,
                          overflow: "hidden", fontFamily: "monospace",
                          lineHeight: 1.5, whiteSpace: "pre-wrap",
                        }}>
                          {(entry.code ?? "").slice(0, 400)}
                        </pre>
                        <div style={{
                          position: "absolute", bottom: 0, left: 0, right: 0, height: 36,
                          background: "linear-gradient(transparent,#0a0910)",
                          borderRadius: "0 0 7px 7px",
                        }} />
                      </div>

                      {/* restore button */}
                      <button
                        onClick={() => { onRestore(entry); onClose(); }}
                        style={{
                          width: "100%", padding: "11px", borderRadius: 9, border: "none",
                          background: "linear-gradient(135deg,#8b5cf6,#6366f1)",
                          color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
                          display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                        }}
                      >
                        <RotateCcw size={14} />
                        Restore this generation
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        {entries.length > 0 && (
          <div style={{
            padding: "11px 16px", borderTop: "1px solid #2d2a3d",
            fontSize: 11, color: "#334155", textAlign: "center",
            flexShrink: 0, background: "#0f0d1a",
          }}>
            Showing {filtered.length} of {entries.length} entries · last 100 kept
          </div>
        )}
      </div>
    </>
  );
}
// frontend/src/components/DastPanel.tsx

import { useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown,
  ChevronRight, Container, Shield, Zap,
} from "lucide-react";

/* ── Types ───────────────────────────────────────────────────────────────── */
export type DastFinding = {
  check_id:  string;
  severity:  "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  message:   string;
  owasp?:    string;
  cwe?:      string | null;
  line?:     number | null;
  snippet?:  string | null;
  source:    "pattern_scan" | "docker_execution";
  runtime:   boolean;
};

export type DastSummary = {
  total:           number;
  critical:        number;
  high:            number;
  medium:          number;
  low:             number;
  docker_executed: boolean;
  owasp_coverage:  string[];
};

export type DastReport = {
  ok:                boolean;
  docker_available:  boolean;
  findings:          DastFinding[];
  pattern_findings:  DastFinding[];
  runtime_findings:  DastFinding[];
  execution_results: Array<{
    lang:      string;
    executed?: boolean;
    exit_code?: number;
    timed_out?: boolean;
    stdout?:   string;
    stderr?:   string;
    skipped?:  boolean;
    reason?:   string;
    error?:    string;
  }>;
  languages: string[];
  summary:   DastSummary;
};

type Props = {
  dast: DastReport;
};

/* ── Severity helpers ────────────────────────────────────────────────────── */
const SEV_COLOR: Record<string, string> = {
  CRITICAL: "#ef4444",
  HIGH:     "#f97316",
  MEDIUM:   "#f59e0b",
  LOW:      "#3b82f6",
};

const SEV_BG: Record<string, string> = {
  CRITICAL: "rgba(239,68,68,0.1)",
  HIGH:     "rgba(249,115,22,0.1)",
  MEDIUM:   "rgba(245,158,11,0.1)",
  LOW:      "rgba(59,130,246,0.1)",
};

function SevBadge({ sev }: { sev: string }) {
  const color = SEV_COLOR[sev] ?? "#64748b";
  const bg    = SEV_BG[sev]   ?? "rgba(100,116,139,0.1)";
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
      padding: "2px 7px", borderRadius: 4,
      color, background: bg, textTransform: "uppercase",
      border: `1px solid ${color}40`,
    }}>
      {sev}
    </span>
  );
}

/* ── Single finding row ──────────────────────────────────────────────────── */
function FindingRow({ finding, index }: { finding: DastFinding; index: number }) {
  const [open, setOpen] = useState(false);
  const color = SEV_COLOR[finding.severity] ?? "#64748b";

  return (
    <div style={{
      borderRadius: 8, border: `1px solid ${color}30`,
      background: "#0a0910", overflow: "hidden", marginBottom: 8,
    }}>
      {/* header row */}
      <div
        onClick={() => setOpen(!open)}
        style={{
          padding: "10px 12px", cursor: "pointer", display: "flex",
          alignItems: "flex-start", gap: 10,
        }}
      >
        <div style={{
          width: 22, height: 22, borderRadius: 6, flexShrink: 0, marginTop: 1,
          background: SEV_BG[finding.severity],
          display: "flex", alignItems: "center", justifyContent: "center",
          border: `1px solid ${color}40`,
        }}>
          <AlertTriangle size={11} color={color} />
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
            <SevBadge sev={finding.severity} />
            <span style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
              #{index + 1} · {finding.check_id}
            </span>
            {finding.source === "docker_execution" && (
              <span style={{
                fontSize: 9, padding: "1px 6px", borderRadius: 3,
                background: "rgba(99,102,241,0.15)", color: "#818cf8",
                fontWeight: 600,
              }}>🐳 runtime</span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "#cbd5e1", marginTop: 4, lineHeight: 1.5 }}>
            {finding.message}
          </div>
        </div>

        <ChevronRight
          size={13} color="#475569"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .2s", flexShrink: 0, marginTop: 4 }}
        />
      </div>

      {/* expanded detail */}
      {open && (
        <div style={{ padding: "0 12px 12px 44px", display: "flex", flexDirection: "column", gap: 6 }}>
          {finding.owasp && (
            <div style={{ fontSize: 11, color: "#94a3b8" }}>
              <span style={{ color: "#64748b" }}>OWASP: </span>
              <span style={{ color: "#f97316", fontWeight: 600 }}>{finding.owasp}</span>
            </div>
          )}
          {finding.cwe && (
            <div style={{ fontSize: 11, color: "#94a3b8" }}>
              <span style={{ color: "#64748b" }}>CWE: </span>{finding.cwe}
            </div>
          )}
          {finding.line && (
            <div style={{ fontSize: 11, color: "#94a3b8" }}>
              <span style={{ color: "#64748b" }}>Line: </span>{finding.line}
            </div>
          )}
          {finding.snippet && (
            <pre style={{
              margin: 0, fontSize: 10, color: "#64748b", background: "#050409",
              padding: "6px 10px", borderRadius: 6, fontFamily: "monospace",
              whiteSpace: "pre-wrap", wordBreak: "break-all",
              border: "1px solid #1e1b2e",
            }}>
              {finding.snippet}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/* ── OWASP coverage chip ─────────────────────────────────────────────────── */
function OwaspChip({ label }: { label: string }) {
  // Extract category letter e.g. "A10" from "A10 - SSRF"
  const match = label.match(/^(A\d+)/);
  const tag   = match ? match[1] : label.slice(0, 3);
  return (
    <span style={{
      fontSize: 10, padding: "3px 9px", borderRadius: 5, fontWeight: 700,
      background: "rgba(239,68,68,0.1)", color: "#fca5a5",
      border: "1px solid rgba(239,68,68,0.2)",
    }}>
      {tag}
    </span>
  );
}

/* ── Docker execution result row ─────────────────────────────────────────── */
function ExecRow({ exec }: { exec: Props["dast"]["execution_results"][0] }) {
  const [open, setOpen] = useState(false);

  const statusColor = exec.skipped
    ? "#64748b"
    : exec.timed_out
    ? "#f59e0b"
    : exec.exit_code === 0
    ? "#10b981"
    : "#ef4444";

  const statusLabel = exec.skipped
    ? "skipped"
    : exec.timed_out
    ? "timed out"
    : exec.executed
    ? `exit ${exec.exit_code}`
    : "failed";

  return (
    <div style={{
      borderRadius: 7, border: "1px solid #1e1b2e",
      background: "#050409", marginBottom: 6, overflow: "hidden",
    }}>
      <div
        onClick={() => setOpen(!open)}
        style={{
          padding: "8px 12px", display: "flex", alignItems: "center",
          gap: 8, cursor: "pointer",
        }}
      >
        <Container size={12} color="#6366f1" />
        <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600, flex: 1 }}>
          {exec.lang}
        </span>
        <span style={{
          fontSize: 10, color: statusColor, fontWeight: 600,
          padding: "2px 7px", borderRadius: 4, background: `${statusColor}18`,
        }}>
          {statusLabel}
        </span>
        <ChevronDown
          size={12} color="#475569"
          style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }}
        />
      </div>

      {open && (exec.stdout || exec.stderr || exec.reason || exec.error) && (
        <div style={{ padding: "0 12px 10px 12px" }}>
          {(exec.stdout || exec.stderr) && (
            <pre style={{
              margin: 0, fontSize: 10, color: "#64748b", background: "#0a0910",
              padding: "8px 10px", borderRadius: 6, fontFamily: "monospace",
              whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto",
              border: "1px solid #1e1b2e",
            }}>
              {(exec.stdout || "") + (exec.stderr || "")}
            </pre>
          )}
          {(exec.reason || exec.error) && (
            <div style={{ fontSize: 11, color: "#64748b", marginTop: 4 }}>
              {exec.reason ?? exec.error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════ */
/*  Main DastPanel component                                                  */
/* ══════════════════════════════════════════════════════════════════════════ */
export default function DastPanel({ dast }: Props) {
  const [findingsOpen, setFindingsOpen] = useState(true);
  const [execOpen,     setExecOpen]     = useState(false);

  const { summary, findings, execution_results } = dast;
  const noIssues = summary.total === 0;

  return (
    <div style={{
      background: "#1a1f2e", borderRadius: 16, padding: 24,
      border: "1px solid #2d3548",
    }}>
      {/* ── Header ── */}
      <div style={{
        fontSize: 11, fontWeight: 600, color: "#64748b",
        textTransform: "uppercase", letterSpacing: "0.1em",
        marginBottom: 20, display: "flex", alignItems: "center", gap: 8,
      }}>
        <Activity size={14} color="#f59e0b" />
        Dynamic Analysis (DAST)

        {/* Docker badge */}
        <span style={{
          marginLeft: "auto", fontSize: 10, padding: "2px 9px",
          borderRadius: 4, fontWeight: 600,
          background: dast.docker_available
            ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)",
          color: dast.docker_available ? "#10b981" : "#f59e0b",
          border: `1px solid ${dast.docker_available ? "rgba(16,185,129,0.3)" : "rgba(245,158,11,0.3)"}`,
        }}>
          {dast.docker_available ? "🐳 Docker active" : "⚡ Pattern scan"}
        </span>
      </div>

      {/* ── Severity counters ── */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr",
        gap: 8, marginBottom: 16,
      }}>
        {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => {
          const val   = summary[sev.toLowerCase() as keyof DastSummary] as number;
          const color = SEV_COLOR[sev];
          const bg    = SEV_BG[sev];
          return (
            <div key={sev} style={{
              padding: "10px 8px", background: "#0f1419",
              borderRadius: 10, border: `1px solid ${val > 0 ? color + "40" : "#2d3548"}`,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: val > 0 ? color : "#334155" }}>
                {val}
              </div>
              <div style={{ fontSize: 9, color: "#475569", marginTop: 3, fontWeight: 600, letterSpacing: "0.04em" }}>
                {sev}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Clean state ── */}
      {noIssues && (
        <div style={{
          padding: 14, background: "rgba(16,185,129,0.08)",
          borderRadius: 8, border: "1px solid rgba(16,185,129,0.25)",
          display: "flex", alignItems: "center", gap: 8,
          fontSize: 13, color: "#10b981", fontWeight: 500, marginBottom: 16,
        }}>
          <CheckCircle2 size={16} />
          No runtime vulnerabilities detected!
        </div>
      )}

      {/* ── OWASP coverage chips ── */}
      {summary.owasp_coverage.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{
            fontSize: 10, color: "#475569", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6,
          }}>
            OWASP Risks Detected
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {summary.owasp_coverage.map((o) => (
              <OwaspChip key={o} label={o} />
            ))}
          </div>
        </div>
      )}

      {/* ── Findings list ── */}
      {findings.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div
            onClick={() => setFindingsOpen(!findingsOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 10,
              padding: "8px 10px", borderRadius: 7, background: "#0f1419",
              border: "1px solid #2d3548",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Shield size={12} color="#f97316" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8" }}>
                Findings ({findings.length})
              </span>
            </div>
            <ChevronDown
              size={13} color="#475569"
              style={{ transform: findingsOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }}
            />
          </div>

          {findingsOpen && findings.map((f, i) => (
            <FindingRow key={`${f.check_id}-${i}`} finding={f} index={i} />
          ))}
        </div>
      )}

      {/* ── Docker execution results ── */}
      {execution_results.length > 0 && (
        <div>
          <div
            onClick={() => setExecOpen(!execOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 8,
              padding: "8px 10px", borderRadius: 7, background: "#0f1419",
              border: "1px solid #2d3548",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Zap size={12} color="#6366f1" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8" }}>
                Sandbox Executions ({execution_results.length})
              </span>
            </div>
            <ChevronDown
              size={13} color="#475569"
              style={{ transform: execOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }}
            />
          </div>

          {execOpen && execution_results.map((e, i) => (
            <ExecRow key={`${e.lang}-${i}`} exec={e} />
          ))}
        </div>
      )}

      {/* ── Source breakdown ── */}
      <div style={{
        marginTop: 14, padding: "8px 12px", borderRadius: 7,
        background: "#0f1419", border: "1px solid #1e1b2e",
        display: "flex", gap: 20,
      }}>
        <div style={{ fontSize: 11, color: "#475569" }}>
          <span style={{ color: "#64748b" }}>Pattern scan: </span>
          <span style={{ color: "#94a3b8", fontWeight: 600 }}>{dast.pattern_findings.length}</span>
        </div>
        <div style={{ fontSize: 11, color: "#475569" }}>
          <span style={{ color: "#64748b" }}>Runtime: </span>
          <span style={{ color: "#6366f1", fontWeight: 600 }}>{dast.runtime_findings.length}</span>
        </div>
        <div style={{ fontSize: 11, color: "#475569" }}>
          <span style={{ color: "#64748b" }}>Languages: </span>
          <span style={{ color: "#94a3b8", fontWeight: 600 }}>{dast.languages.join(", ") || "—"}</span>
        </div>
      </div>
    </div>
  );
}
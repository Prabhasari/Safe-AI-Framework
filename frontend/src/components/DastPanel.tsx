// frontend/src/components/DastPanel.tsx

import { useState } from "react";
import {
  Activity, AlertTriangle, CheckCircle2, ChevronDown,
  ChevronRight, Container, Shield, Zap, Terminal,
  FileCode, Wrench, XCircle, Clock, Cpu, Hash,
} from "lucide-react";

/* ── Types ───────────────────────────────────────────────────────────────── */
export type DastFinding = {
  check_id:  string;
  severity:  "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  message:   string;
  owasp?:    string;
  cwe?:      string | null;
  line?:     number | null;
  file?:     string | null;
  snippet?:  string | null;
  fix_hint?: string | null;
  source:    "pattern_scan" | "docker_execution";
  runtime:   boolean;
  proof_of_execution?: ProofOfExecution | null;
};

export type ProofOfExecution = {
  image:        string;
  image_id?:    string | null;
  container_id?: string | null;
  started_at?:  string;
  elapsed_ms?:  number;
  exit_code?:   number;
  timed_out?:   boolean;
  stdout_lines?: string[];
  stderr_lines?: string[];
  entrypoint?:  string;
  files?:       string[];
  isolation?: {
    network:    string;
    read_only:  boolean;
    memory:     string;
    cpus:       string;
    pids_limit: number;
    cap_drop:   string;
  };
};

export type DastFixResult = {
  attempted:     boolean;
  fixed:         boolean;
  fixed_code?:   string | null;
  fixes_applied: number;
  unfixable?:    DastFinding[];
  error?:        string | null;
};

export type DastSummary = {
  total:            number;
  critical:         number;
  high:             number;
  medium:           number;
  low:              number;
  docker_executed:  boolean;
  owasp_coverage:   string[];
  fix_attempted?:   boolean;
  fixes_applied?:   number;
  unfixable_count?: number;
};

export type DastReport = {
  ok:                  boolean;
  docker_available:    boolean;
  findings:            DastFinding[];
  pattern_findings:    DastFinding[];
  runtime_findings:    DastFinding[];
  execution_results:   Array<{
    lang:       string;
    executed?:  boolean;
    exit_code?: number;
    timed_out?: boolean;
    stdout?:    string;
    stderr?:    string;
    skipped?:   boolean;
    reason?:    string;
    error?:     string;
    proof_of_execution?: ProofOfExecution | null;
  }>;
  proof_of_executions?: ProofOfExecution[];
  languages:  string[];
  summary:    DastSummary;
  fix_result?: DastFixResult;
};

/* ── NEW: Stage 6 LLM fix result type (from pipeline.py dast_llm_fix) ────── */
export type DastLlmFixResult = {
  fixed?:         boolean;
  attempted?:     boolean;
  fixes_applied?: number;
  issues_before?: number;
  issues_after?:  number;
  error?:         string;
  reason?:        string;
};

/* ── Updated Props — added dastLlmFix ────────────────────────────────────── */
type Props = {
  dast:        DastReport;
  dastLlmFix?: DastLlmFixResult | null;  // Stage 6 result from pipeline.py
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
    }}>{sev}</span>
  );
}

/* ── Proof of execution card ─────────────────────────────────────────────── */
function ProofCard({ proof }: { proof: ProofOfExecution }) {
  const [open, setOpen] = useState(false);
  const success = !proof.timed_out && (proof.exit_code === 0 || proof.exit_code !== undefined);

  return (
    <div style={{
      borderRadius: 8, border: "1px solid rgba(99,102,241,0.35)",
      background: "#080611", overflow: "hidden", marginBottom: 8,
    }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ padding: "10px 14px", cursor: "pointer", display: "flex", alignItems: "center", gap: 10 }}
      >
        <Terminal size={13} color="#6366f1" />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, color: "#a5b4fc", fontWeight: 600 }}>
            Execution Proof — {proof.image}
          </div>
          <div style={{ fontSize: 10, color: "#475569", marginTop: 2, display: "flex", gap: 12 }}>
            {proof.elapsed_ms !== undefined && (
              <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <Clock size={9} /> {proof.elapsed_ms}ms
              </span>
            )}
            {proof.exit_code !== undefined && (
              <span style={{ color: proof.exit_code === 0 ? "#10b981" : "#f97316" }}>
                exit {proof.exit_code}
              </span>
            )}
            {proof.container_id && (
              <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                <Hash size={9} /> {proof.container_id}
              </span>
            )}
          </div>
        </div>
        <div style={{
          fontSize: 10, padding: "2px 8px", borderRadius: 4,
          background: success ? "rgba(16,185,129,0.12)" : "rgba(245,158,11,0.12)",
          color: success ? "#10b981" : "#f59e0b", fontWeight: 600,
        }}>
          {proof.timed_out ? "timed out" : success ? "✔ ran" : "⚠ error"}
        </div>
        <ChevronDown size={12} color="#475569" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
      </div>

      {open && (
        <div style={{ padding: "0 14px 14px 14px", display: "flex", flexDirection: "column", gap: 8 }}>
          {proof.isolation && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 6 }}>
              {[
                { icon: <Cpu size={9} />,       label: "CPUs",    val: proof.isolation.cpus },
                { icon: <Container size={9} />, label: "Memory",  val: proof.isolation.memory },
                { icon: <Shield size={9} />,    label: "Network", val: proof.isolation.network },
              ].map(({ icon, label, val }) => (
                <div key={label} style={{
                  padding: "6px 8px", background: "#0a0910", borderRadius: 6,
                  border: "1px solid #1e1b2e", textAlign: "center",
                }}>
                  <div style={{ color: "#6366f1", marginBottom: 2 }}>{icon}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 600 }}>{val}</div>
                  <div style={{ fontSize: 9, color: "#475569" }}>{label}</div>
                </div>
              ))}
            </div>
          )}
          {proof.image_id && (
            <div style={{ fontSize: 10, color: "#475569", fontFamily: "monospace" }}>
              <span style={{ color: "#334155" }}>Image digest: </span>
              <span style={{ color: "#6366f1" }}>{proof.image_id}</span>
            </div>
          )}
          {proof.entrypoint && (
            <div style={{ fontSize: 10, color: "#475569" }}>
              <span style={{ color: "#334155" }}>Entrypoint: </span>
              <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>{proof.entrypoint}</span>
            </div>
          )}
          {(proof.stdout_lines ?? []).length > 0 && (
            <div>
              <div style={{ fontSize: 9, color: "#334155", marginBottom: 4, fontWeight: 600, textTransform: "uppercase" }}>STDOUT</div>
              <pre style={{
                margin: 0, fontSize: 10, color: "#64748b", background: "#050409",
                padding: "6px 10px", borderRadius: 6, fontFamily: "monospace",
                whiteSpace: "pre-wrap", maxHeight: 80, overflow: "auto",
                border: "1px solid #1e1b2e",
              }}>
                {(proof.stdout_lines ?? []).join("\n") || "(empty)"}
              </pre>
            </div>
          )}
          {(proof.stderr_lines ?? []).length > 0 && (
            <div>
              <div style={{ fontSize: 9, color: "#334155", marginBottom: 4, fontWeight: 600, textTransform: "uppercase" }}>STDERR</div>
              <pre style={{
                margin: 0, fontSize: 10, color: "#f97316", background: "#050409",
                padding: "6px 10px", borderRadius: 6, fontFamily: "monospace",
                whiteSpace: "pre-wrap", maxHeight: 80, overflow: "auto",
                border: "1px solid rgba(249,115,22,0.2)",
              }}>
                {(proof.stderr_lines ?? []).join("\n")}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Single finding row ──────────────────────────────────────────────────── */
function FindingRow({
  finding, index, isUnfixable,
}: {
  finding: DastFinding; index: number; isUnfixable?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const color = SEV_COLOR[finding.severity] ?? "#64748b";

  return (
    <div style={{
      borderRadius: 8,
      border: `1px solid ${isUnfixable ? color + "60" : color + "30"}`,
      background: isUnfixable ? "#0d0008" : "#0a0910",
      overflow: "hidden", marginBottom: 8,
    }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ padding: "10px 12px", cursor: "pointer", display: "flex", alignItems: "flex-start", gap: 10 }}
      >
        <div style={{
          width: 22, height: 22, borderRadius: 6, flexShrink: 0, marginTop: 1,
          background: SEV_BG[finding.severity],
          display: "flex", alignItems: "center", justifyContent: "center",
          border: `1px solid ${color}40`,
        }}>
          {isUnfixable
            ? <XCircle size={11} color={color} />
            : <AlertTriangle size={11} color={color} />}
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
                background: "rgba(99,102,241,0.15)", color: "#818cf8", fontWeight: 600,
              }}>🐳 runtime</span>
            )}
            {isUnfixable && (
              <span style={{
                fontSize: 9, padding: "1px 6px", borderRadius: 3,
                background: "rgba(239,68,68,0.15)", color: "#fca5a5", fontWeight: 600,
              }}>⚠ manual fix required</span>
            )}
          </div>

          {(finding.file || finding.line) && (
            <div style={{
              display: "flex", alignItems: "center", gap: 5,
              marginTop: 4, padding: "3px 8px", borderRadius: 4,
              background: `${color}12`, border: `1px solid ${color}25`,
              width: "fit-content",
            }}>
              <FileCode size={10} color={color} />
              <span style={{ fontSize: 11, color, fontFamily: "monospace", fontWeight: 600 }}>
                {finding.file ?? "unknown"}
                {finding.line ? ` : line ${finding.line}` : ""}
              </span>
            </div>
          )}

          <div style={{ fontSize: 12, color: "#cbd5e1", marginTop: 4, lineHeight: 1.5 }}>
            {finding.message}
          </div>
        </div>

        <ChevronRight
          size={13} color="#475569"
          style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .2s", flexShrink: 0, marginTop: 4 }}
        />
      </div>

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
          {finding.fix_hint && (
            <div style={{
              padding: "8px 10px", borderRadius: 6,
              background: "rgba(16,185,129,0.07)",
              border: "1px solid rgba(16,185,129,0.2)",
            }}>
              <div style={{ fontSize: 9, color: "#10b981", fontWeight: 700, marginBottom: 3, textTransform: "uppercase", display: "flex", alignItems: "center", gap: 4 }}>
                <Wrench size={9} /> How to Fix
              </div>
              <div style={{ fontSize: 11, color: "#6ee7b7", lineHeight: 1.5 }}>
                {finding.fix_hint}
              </div>
            </div>
          )}
          {finding.snippet && (
            <div>
              <div style={{ fontSize: 9, color: "#334155", marginBottom: 3, fontWeight: 600, textTransform: "uppercase" }}>Matched snippet</div>
              <pre style={{
                margin: 0, fontSize: 10, color: "#64748b", background: "#050409",
                padding: "6px 10px", borderRadius: 6, fontFamily: "monospace",
                whiteSpace: "pre-wrap", wordBreak: "break-all",
                border: "1px solid #1e1b2e",
              }}>
                {finding.snippet}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── OWASP chip ──────────────────────────────────────────────────────────── */
function OwaspChip({ label }: { label: string }) {
  const match = label.match(/^(A\d+)/);
  const tag   = match ? match[1] : label.slice(0, 3);
  return (
    <span style={{
      fontSize: 10, padding: "3px 9px", borderRadius: 5, fontWeight: 700,
      background: "rgba(239,68,68,0.1)", color: "#fca5a5",
      border: "1px solid rgba(239,68,68,0.2)",
    }}>{tag}</span>
  );
}

/* ── Docker execution result row ─────────────────────────────────────────── */
function ExecRow({ exec }: { exec: DastReport["execution_results"][0] }) {
  const [open, setOpen] = useState(false);
  const proof = exec.proof_of_execution;

  const statusColor = exec.skipped
    ? "#64748b" : exec.timed_out ? "#f59e0b"
    : exec.exit_code === 0 ? "#10b981" : "#ef4444";

  const statusLabel = exec.skipped ? "skipped"
    : exec.timed_out ? "timed out"
    : exec.executed ? `exit ${exec.exit_code}` : "failed";

  return (
    <div style={{ borderRadius: 7, border: "1px solid #1e1b2e", background: "#050409", marginBottom: 6, overflow: "hidden" }}>
      <div
        onClick={() => setOpen(!open)}
        style={{ padding: "8px 12px", display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
      >
        <Container size={12} color="#6366f1" />
        <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 600, flex: 1 }}>{exec.lang}</span>
        {proof?.elapsed_ms !== undefined && (
          <span style={{ fontSize: 10, color: "#475569" }}>{proof.elapsed_ms}ms</span>
        )}
        <span style={{
          fontSize: 10, color: statusColor, fontWeight: 600,
          padding: "2px 7px", borderRadius: 4, background: `${statusColor}18`,
        }}>{statusLabel}</span>
        <ChevronDown size={12} color="#475569" style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
      </div>

      {open && (
        <div style={{ padding: "0 12px 10px 12px" }}>
          {proof && <ProofCard proof={proof} />}
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
export default function DastPanel({ dast, dastLlmFix }: Props) {
  const [findingsOpen,  setFindingsOpen]  = useState(true);
  const [unfixableOpen, setUnfixableOpen] = useState(true);
  const [execOpen,      setExecOpen]      = useState(false);
  const [proofOpen,     setProofOpen]     = useState(false);

  const { summary, findings, execution_results } = dast;
  const fixResult  = dast.fix_result;
  const unfixable  = fixResult?.unfixable ?? [];
  const proofList  = dast.proof_of_executions ?? [];
  const noIssues   = summary.total === 0;

  // ── Stage 6 LLM fix stats (passed from pipeline.py via SecureGenerator) ──
  const llmFixApplied     = dastLlmFix?.fixed === true;
  const llmFixCount       = dastLlmFix?.fixes_applied ?? 0;
  const remainingAfterFix = summary.total - llmFixCount;

  // Separate normal findings from unfixable for display
  const unfixableIds = new Set(unfixable.map(f => f.check_id + (f.line ?? "")));
  const fixableShown = findings.filter(f => !unfixableIds.has(f.check_id + (f.line ?? "")));

  return (
    <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>

      {/* ── Header ── */}
      <div style={{
        fontSize: 11, fontWeight: 600, color: "#64748b",
        textTransform: "uppercase", letterSpacing: "0.1em",
        marginBottom: 20, display: "flex", alignItems: "center", gap: 8,
      }}>
        <Activity size={14} color="#f59e0b" />
        Dynamic Analysis (DAST)
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
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 8, marginBottom: 16 }}>
        {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => {
          const val   = summary[sev.toLowerCase() as keyof DastSummary] as number;
          const color = SEV_COLOR[sev];
          return (
            <div key={sev} style={{
              padding: "10px 8px", background: "#0f1419",
              borderRadius: 10, border: `1px solid ${val > 0 ? color + "40" : "#2d3548"}`,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: val > 0 ? color : "#334155" }}>{val}</div>
              <div style={{ fontSize: 9, color: "#475569", marginTop: 3, fontWeight: 600, letterSpacing: "0.04em" }}>{sev}</div>
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

      {/* ── Stage 6 LLM fix summary banner ─────────────────────────────────
           This reads from pipeline.py's dast_llm_fix (Stage 6), which is the
           actual fix result. dast.fix_result is always attempted=False because
           dast-service delegates fixing to pipeline.py Stage 6.
      ── */}
      {llmFixApplied && llmFixCount > 0 && (
        <div style={{
          padding: "14px 16px", borderRadius: 10, marginBottom: 16,
          background: "rgba(16,185,129,0.07)",
          border: "1px solid rgba(16,185,129,0.3)",
          display: "flex", alignItems: "center", gap: 14,
        }}>
          <CheckCircle2 size={20} color="#10b981" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, color: "#10b981", fontWeight: 700, marginBottom: 3 }}>
              LLM Auto-fixed {llmFixCount} of {summary.total} DAST finding(s)
            </div>
            <div style={{ fontSize: 11, color: "#6ee7b7", lineHeight: 1.5 }}>
              {remainingAfterFix > 0
                ? `${remainingAfterFix} finding(s) still require manual review`
                : "All findings resolved — code is clean"}
            </div>
          </div>
          {/* Stat cards: Found / Fixed / Remaining */}
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            {[
              { label: "Found",     val: summary.total,     color: "#f97316" },
              { label: "Fixed",     val: llmFixCount,        color: "#10b981" },
              { label: "Remaining", val: remainingAfterFix,
                color: remainingAfterFix === 0 ? "#10b981" : "#f59e0b" },
            ].map(({ label, val, color }) => (
              <div key={label} style={{
                padding: "8px 12px", background: "#0f1419",
                borderRadius: 8, border: "1px solid #2d3548", textAlign: "center",
                minWidth: 56,
              }}>
                <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{val}</div>
                <div style={{ fontSize: 9, color: "#475569", fontWeight: 600, marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── OWASP coverage ── */}
      {summary.owasp_coverage.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, color: "#475569", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
            OWASP Risks Detected
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
            {summary.owasp_coverage.map((o) => <OwaspChip key={o} label={o} />)}
          </div>
        </div>
      )}

      {/* ── Unfixable findings ── */}
      {unfixable.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div
            onClick={() => setUnfixableOpen(!unfixableOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 10,
              padding: "8px 10px", borderRadius: 7,
              background: "rgba(239,68,68,0.07)",
              border: "1px solid rgba(239,68,68,0.3)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <XCircle size={12} color="#ef4444" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#fca5a5" }}>
                Unfixable — Manual Review Required ({unfixable.length})
              </span>
            </div>
            <ChevronDown size={13} color="#ef4444" style={{ transform: unfixableOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
          </div>
          {unfixableOpen && unfixable.map((f, i) => (
            <FindingRow key={`uf-${f.check_id}-${i}`} finding={f} index={i} isUnfixable />
          ))}
        </div>
      )}

      {/* ── All findings ── */}
      {fixableShown.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div
            onClick={() => setFindingsOpen(!findingsOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 10,
              padding: "8px 10px", borderRadius: 7, background: "#0f1419", border: "1px solid #2d3548",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Shield size={12} color="#f97316" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8" }}>
                All Findings ({findings.length})
              </span>
            </div>
            <ChevronDown size={13} color="#475569" style={{ transform: findingsOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
          </div>
          {findingsOpen && findings.map((f, i) => (
            <FindingRow key={`f-${f.check_id}-${i}`} finding={f} index={i} />
          ))}
        </div>
      )}

      {/* ── Proof of Execution ── */}
      {proofList.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div
            onClick={() => setProofOpen(!proofOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 8,
              padding: "8px 10px", borderRadius: 7,
              background: "rgba(99,102,241,0.07)", border: "1px solid rgba(99,102,241,0.25)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Terminal size={12} color="#6366f1" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#a5b4fc" }}>
                Execution Proof ({proofList.length} container{proofList.length !== 1 ? "s" : ""})
              </span>
            </div>
            <ChevronDown size={13} color="#6366f1" style={{ transform: proofOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
          </div>
          {proofOpen && proofList.map((proof, i) => (
            <ProofCard key={i} proof={proof} />
          ))}
        </div>
      )}

      {/* ── Sandbox execution results ── */}
      {execution_results.length > 0 && (
        <div>
          <div
            onClick={() => setExecOpen(!execOpen)}
            style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              cursor: "pointer", marginBottom: 8,
              padding: "8px 10px", borderRadius: 7, background: "#0f1419", border: "1px solid #2d3548",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <Zap size={12} color="#6366f1" />
              <span style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8" }}>
                Sandbox Executions ({execution_results.length})
              </span>
            </div>
            <ChevronDown size={13} color="#475569" style={{ transform: execOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} />
          </div>
          {execOpen && execution_results.map((e, i) => (
            <ExecRow key={`${e.lang}-${i}`} exec={e} />
          ))}
        </div>
      )}

      {/* ── Footer — source breakdown + fix counts ── */}
      <div style={{
        marginTop: 14, padding: "10px 14px", borderRadius: 8,
        background: "#0f1419", border: "1px solid #1e1b2e",
        display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center",
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

        {/* ── Fix counts — always show when there are findings ── */}
        <div style={{ marginLeft: "auto", display: "flex", gap: 16, alignItems: "center" }}>
          <span style={{ fontSize: 11, color: "#475569" }}>
            <span style={{ color: "#64748b" }}>Total found: </span>
            <span style={{ color: "#f97316", fontWeight: 600 }}>{summary.total}</span>
          </span>
          {llmFixApplied ? (
            <>
              <span style={{ fontSize: 11, color: "#475569" }}>
                <span style={{ color: "#64748b" }}>LLM fixed: </span>
                <span style={{ color: "#10b981", fontWeight: 600 }}>{llmFixCount}</span>
              </span>
              <span style={{ fontSize: 11, color: "#475569" }}>
                <span style={{ color: "#64748b" }}>Remaining: </span>
                <span style={{
                  color: remainingAfterFix === 0 ? "#10b981" : "#f59e0b",
                  fontWeight: 600,
                }}>
                  {remainingAfterFix}
                </span>
              </span>
            </>
          ) : (
            summary.total > 0 && (
              <span style={{ fontSize: 11, color: "#475569" }}>
                <span style={{ color: "#64748b" }}>Fixed: </span>
                <span style={{ color: "#64748b", fontWeight: 600 }}>0</span>
                <span style={{ color: "#64748b" }}>  Remaining: </span>
                <span style={{ color: "#f59e0b", fontWeight: 600 }}>{summary.total}</span>
              </span>
            )
          )}
        </div>
      </div>
    </div>
  );
}
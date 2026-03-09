// frontend/src/pages/SecureGenerator.tsx

import { useState } from "react";
import UmlViewerModal, { type DiagramType, type AiUmlStore } from "../components/UmlViewerModal.tsx";
import ChatHistoryPanel, { type HistoryEntry } from "../components/ChatHistoryPanel.tsx";
import DastPanel, { type DastReport } from "../components/DastPanel.tsx";
import {
  CheckCircle2, MinusCircle, Shield, Sparkles,
  Copy, Check, Code2, ChevronDown, Zap, BarChart3, Clock, Settings, ArrowLeft,
  Network, Package, GitBranch, Boxes, Activity, Eye,
} from "lucide-react";

/* ══════════════════════════════════════════════════════════════════════════
   Types
══════════════════════════════════════════════════════════════════════════ */

type Finding = {
  check_id?: string;
  severity?: string;
  message?: string;
  path?: string;
  start?: { line?: number };
  has_autofix?: boolean;
};

type SemgrepReport = {
  ok?: boolean;
  initial_findings?: number;
  final_findings?: number;
  autofix_applied?: boolean;
  fixes_applied?: number;
  auto_fixable_count?: number;
  manual_only_count?: number;
  packs?: string[];
  languages?: string[];
  file_count?: number;
  categorized_findings?: {
    initially_auto_fixable?: Finding[];
    initially_manual_only?: Finding[];
    still_remaining?: Finding[];
    remaining_needs_llm?: Finding[];
  };
};

type LlmFixReport = {
  fixed?: boolean;
  attempted?: boolean;
  issues_before?: number;
  issues_after?: number;
  fixes_applied?: number;
  error?: string;
  reason?: string;
};

type UmlValidationEntry = { ok: boolean; errors: string[] };
type UmlValidationMap = Partial<
  Record<"class" | "package" | "sequence" | "component" | "activity", UmlValidationEntry>
>;

type UmlReport = {
  ok?: boolean;
  file_count?: number;
  error?: string | null;
  cir?: unknown;
  class_svg?: string | null;
  package_svg?: string | null;
  sequence_svg?: string | null;
  component_svg?: string | null;
  activity_svg?: string | null;
  ai_class_svg?: string | null;
  ai_package_svg?: string | null;
  ai_sequence_svg?: string | null;
  ai_component_svg?: string | null;
  ai_activity_svg?: string | null;
  ai_class_plantuml?: string | null;
  ai_package_plantuml?: string | null;
  ai_sequence_plantuml?: string | null;
  ai_component_plantuml?: string | null;
  ai_activity_plantuml?: string | null;
  validation?: UmlValidationMap;
  ai_validation?: UmlValidationMap;
};

type Report = {
  policy_version?: string;
  prompt_after_enhancement?: string;
  semgrep?: SemgrepReport;
  llm_fix?: LlmFixReport;
  dast?: DastReport;           // ← DAST report
  dast_llm_fix?: LlmFixReport; // ← DAST LLM re-fix
  uml?: UmlReport;
  total_fixes_applied?: number;
  fix_summary?: {
    initial_issues?: number;
    semgrep_fixed?: number;
    llm_fixed?: number;
    dast_findings?: number;
    dast_fixed?: number;
    remaining_issues?: number;
    dast_remaining?: number;
    fix_rate_percent?: number;
  };
};

type ApiResult = {
  code: string;
  original_code?: string;
  report: Report;
  decision?: string;
};

/* ══════════════════════════════════════════════════════════════════════════
   Constants
══════════════════════════════════════════════════════════════════════════ */

const API         = "http://localhost:8000/api/generate";
const HISTORY_API = "http://localhost:8000/api/history/save";
const UML_AI_API  = "http://localhost:7081/uml/ai";

type DiagramMeta = {
  type: DiagramType;
  label: string;
  description: string;
  svgKey: keyof UmlReport;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Icon: React.ComponentType<any>;
};

const DIAGRAM_META: DiagramMeta[] = [
  { type: "class",     label: "Class Diagram",     description: "Classes, fields & relationships", svgKey: "class_svg",     Icon: Network   },
  { type: "package",   label: "Package Diagram",   description: "Namespace & module structure",    svgKey: "package_svg",   Icon: Package   },
  { type: "sequence",  label: "Sequence Diagram",  description: "Runtime call interactions",       svgKey: "sequence_svg",  Icon: GitBranch },
  { type: "component", label: "Component Diagram", description: "Architectural components",        svgKey: "component_svg", Icon: Boxes     },
  { type: "activity",  label: "Activity Diagram",  description: "Control-flow & method calls",     svgKey: "activity_svg",  Icon: Activity  },
];

/* ══════════════════════════════════════════════════════════════════════════
   Helpers
══════════════════════════════════════════════════════════════════════════ */

function buildAiCacheFromReport(umlData: UmlReport | undefined): AiUmlStore {
  if (!umlData) return {};
  const cache: AiUmlStore = {};
  const mapping: Array<{ diagType: DiagramType; svgKey: keyof UmlReport; puKey: keyof UmlReport }> = [
    { diagType: "class",     svgKey: "ai_class_svg",     puKey: "ai_class_plantuml"     },
    { diagType: "package",   svgKey: "ai_package_svg",   puKey: "ai_package_plantuml"   },
    { diagType: "sequence",  svgKey: "ai_sequence_svg",  puKey: "ai_sequence_plantuml"  },
    { diagType: "component", svgKey: "ai_component_svg", puKey: "ai_component_plantuml" },
    { diagType: "activity",  svgKey: "ai_activity_svg",  puKey: "ai_activity_plantuml"  },
  ];
  for (const { diagType, svgKey, puKey } of mapping) {
    const svg = umlData[svgKey] as string | null | undefined;
    if (svg) cache[diagType] = { svg, plantuml: (umlData[puKey] as string | null | undefined) ?? undefined };
  }
  return cache;
}

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function saveToHistory(prompt: string, result: ApiResult): Promise<void> {
  const umlData = result.report?.uml;
  const entry: HistoryEntry = {
    id:            generateId(),
    timestamp:     new Date().toISOString(),
    prompt,
    code:          result.code,
    original_code: result.original_code,
    fix_summary:   result.report?.fix_summary,
    languages:     result.report?.semgrep?.languages,
    decision:      result.decision,
    uml: umlData ? {
      class_svg:        umlData.class_svg,
      package_svg:      umlData.package_svg,
      sequence_svg:     umlData.sequence_svg,
      component_svg:    umlData.component_svg,
      activity_svg:     umlData.activity_svg,
      ai_class_svg:     umlData.ai_class_svg,
      ai_package_svg:   umlData.ai_package_svg,
      ai_sequence_svg:  umlData.ai_sequence_svg,
      ai_component_svg: umlData.ai_component_svg,
      ai_activity_svg:  umlData.ai_activity_svg,
    } : undefined,
  };
  try {
    await fetch(HISTORY_API, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(entry),
    });
  } catch {
    try {
      const raw = localStorage.getItem("secure_gen_history");
      const existing: HistoryEntry[] = raw ? JSON.parse(raw) : [];
      existing.unshift(entry);
      localStorage.setItem("secure_gen_history", JSON.stringify(existing.slice(0, 50)));
    } catch { /**/ }
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   Main component
══════════════════════════════════════════════════════════════════════════ */

export default function SecureGenerator() {
  const [prompt, setPrompt]             = useState("");
  const [out, setOut]                   = useState<ApiResult | null>(null);
  const [loading, setLoading]           = useState(false);
  const [copied, setCopied]             = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  const [securityReportOpen, setSecurityReportOpen] = useState(false);

  // UML modal
  const [umlOpen, setUmlOpen]       = useState(false);
  const [umlTab, setUmlTab]         = useState<DiagramType>("class");
  const [aiUmlCache, setAiUmlCache] = useState<AiUmlStore>({});

  // History panel
  const [historyOpen, setHistoryOpen] = useState(false);

  /* ── Generate ─────────────────────────────────────────────────────────── */
  const onGenerate = async () => {
    setLoading(true);
    setOut(null);
    setCopied(false);
    setUmlOpen(false);
    setShowOriginal(false);
    setAiUmlCache({});
    setSecurityReportOpen(false);

    try {
      const res  = await fetch(API, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ prompt }),
      });
      const data = (await res.json()) as ApiResult;
      setOut(data);

      const prebuilt = buildAiCacheFromReport(data?.report?.uml);
      if (Object.keys(prebuilt).length > 0) setAiUmlCache(prebuilt);

      await saveToHistory(prompt, data);
    } catch (e) {
      console.error(e);
      alert("Request failed — is the backend running on :8000?");
    } finally {
      setLoading(false);
    }
  };

  /* ── Restore history entry ────────────────────────────────────────────── */
  const onRestoreHistory = (entry: HistoryEntry) => {
    setPrompt(entry.prompt);

    const restoredUml: UmlReport | undefined = entry.uml ? {
      class_svg:        entry.uml.class_svg,
      package_svg:      entry.uml.package_svg,
      sequence_svg:     entry.uml.sequence_svg,
      component_svg:    entry.uml.component_svg,
      activity_svg:     entry.uml.activity_svg,
      ai_class_svg:     entry.uml.ai_class_svg,
      ai_package_svg:   entry.uml.ai_package_svg,
      ai_sequence_svg:  entry.uml.ai_sequence_svg,
      ai_component_svg: entry.uml.ai_component_svg,
      ai_activity_svg:  entry.uml.ai_activity_svg,
    } : undefined;

    const restoredAiCache = restoredUml ? buildAiCacheFromReport(restoredUml) : {};

    setOut({
      code:          entry.code,
      original_code: entry.original_code,
      decision:      entry.decision,
      report: {
        fix_summary: entry.fix_summary,
        semgrep:     { languages: entry.languages },
        uml:         restoredUml,
      } as Report,
    });
    setAiUmlCache(restoredAiCache);
    setShowOriginal(false);
    setCopied(false);
    setUmlOpen(false);
  };

  /* ── Helpers ──────────────────────────────────────────────────────────── */
  const copyCode = async () => {
    if (!out?.code) return;
    await navigator.clipboard.writeText(out.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openViewer = () => {
    if (!uml) return;
    const defaultTab: DiagramType =
      uml.class_svg     ? "class"     :
      uml.package_svg   ? "package"   :
      uml.sequence_svg  ? "sequence"  :
      uml.component_svg ? "component" : "activity";
    setUmlTab(defaultTab);
    setUmlOpen(true);
  };

  const fixSummary = out?.report?.fix_summary;
  const uml        = out?.report?.uml;
  const dast       = out?.report?.dast;

  /* ── RENDER ───────────────────────────────────────────────────────────── */
  return (
    <div style={{ display: "flex", width: "100vw", height: "100vh", background: "#0f172a", overflow: "hidden" }}>

      {/* ── Sidebar ── */}
      <div style={{
        width: 60, background: "#1e1b2e", display: "flex", flexDirection: "column",
        alignItems: "center", padding: "20px 0", gap: 20, borderRight: "1px solid #2d2a3d",
      }}>
        <button
          onClick={() => window.history.back()}
          style={{ width: 40, height: 40, background: "none", border: "none", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", padding: 0 }}
        >
          <ArrowLeft size={22} color="#e2e8f0" strokeWidth={2.5} />
        </button>

        <div style={{ width: 40, height: 40, borderRadius: 12, background: "linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Zap size={24} color="#fff" />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 20 }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: "#8b5cf6", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
            <Shield size={20} color="#fff" />
          </div>

          <button
            onClick={() => setHistoryOpen(true)}
            title="View generation history"
            style={{
              width: 40, height: 40, borderRadius: 10, padding: 0,
              background: historyOpen ? "rgba(139,92,246,0.15)" : "transparent",
              border:     historyOpen ? "1px solid #8b5cf6"     : "1px solid transparent",
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: "pointer", transition: "background .2s, border-color .2s",
            }}
          >
            <Clock size={20} color={historyOpen ? "#8b5cf6" : "#94a3b8"} />
          </button>

          <div style={{ width: 40, height: 40, borderRadius: 10, background: "transparent", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", opacity: 0.5 }}>
            <BarChart3 size={20} color="#94a3b8" />
          </div>
        </div>

        <div style={{ marginTop: "auto" }}>
          <div style={{ width: 40, height: 40, borderRadius: 10, background: "transparent", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", opacity: 0.5 }}>
            <Settings size={20} color="#94a3b8" />
          </div>
        </div>
      </div>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ padding: "20px 32px", borderBottom: "1px solid #1e293b", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#f1f5f9" }}>
              Secure Code Generator
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#64748b" }}>
              AI-powered code generation with SAST · DAST · UML visualization
            </p>
          </div>

          {/* Pipeline status badges — shown while loading */}
          {loading && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {["SAST", "DAST", "UML"].map((stage) => (
                <span key={stage} style={{
                  fontSize: 10, padding: "3px 10px", borderRadius: 4, fontWeight: 700,
                  background: "rgba(139,92,246,0.15)", color: "#a78bfa",
                  border: "1px solid rgba(139,92,246,0.3)",
                  animation: "pulse 1.5s infinite",
                }}>
                  {stage}
                </span>
              ))}
              <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>
            </div>
          )}
        </div>

        {/* Scrollable area */}
        <div style={{ flex: 1, overflow: "auto", padding: "32px" }}>
          <div style={{ display: "grid", gridTemplateColumns: out ? "500px 1fr" : "1fr", gap: 24, maxWidth: 1600 }}>

            {/* ════════════════════════════════
                Left Column
            ════════════════════════════════ */}
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

              {/* Input card */}
              <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>
                <label style={{ display: "block", marginBottom: 12, fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  Describe the code you want to generate
                </label>
                <textarea
                  rows={6}
                  style={{ width: "100%", padding: 16, borderRadius: 12, border: "1px solid #2d3548", fontSize: 13, fontFamily: "inherit", resize: "vertical", outline: "none", boxSizing: "border-box", background: "#0f1419", color: "#94a3b8", transition: "border-color 0.2s", lineHeight: 1.6 }}
                  placeholder="e.g., give javascript code for student management system..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onFocus={(e) => (e.target.style.borderColor = "#8b5cf6")}
                  onBlur={(e)  => (e.target.style.borderColor = "#2d3548")}
                />

                <div style={{ marginTop: 20, display: "flex", gap: 12 }}>
                  <button
                    onClick={onGenerate}
                    disabled={loading || !prompt.trim()}
                    style={{
                      flex: 1, padding: "14px 24px", borderRadius: 10, border: "none",
                      background: loading || !prompt.trim() ? "#2d3548" : "linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)",
                      color: "white", fontSize: 14, fontWeight: 600,
                      cursor: loading || !prompt.trim() ? "not-allowed" : "pointer",
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                    }}
                  >
                    <Sparkles size={18} />
                    {loading ? "Generating & Analyzing..." : "Generate Secure Code"}
                  </button>

                  {out?.code && (
                    <button
                      onClick={copyCode}
                      style={{ padding: "14px 20px", borderRadius: 10, border: "1px solid #2d3548", background: copied ? "#8b5cf6" : "transparent", color: copied ? "#fff" : "#94a3b8", fontSize: 14, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}
                    >
                      {copied ? <Check size={18} /> : <Copy size={18} />}
                    </button>
                  )}
                </div>
              </div>

              {/* UML diagrams card */}
              {out && (
                <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
                    <Network size={14} color="#8b5cf6" />
                    UML Diagrams
                  </div>

                  {!uml || uml.error ? (
                    <div style={{ padding: 16, background: "#0f1419", borderRadius: 8, border: "1px solid #2d3548", color: "#64748b", fontSize: 13, textAlign: "center" }}>
                      {uml?.error ? `UML generation: ${uml.error}` : "No UML diagrams available (e.g. non-Java/Python code)."}
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 18 }}>
                        {DIAGRAM_META.map(({ type, label, description, svgKey, Icon }) => {
                          const ready = Boolean(uml[svgKey]);
                          return (
                            <div key={type} style={{ padding: "12px 14px", background: "#0f1419", borderRadius: 10, border: `1px solid ${ready ? "#8b5cf6" : "#2d3548"}`, display: "flex", alignItems: "center", gap: 12 }}>
                              <div style={{ width: 34, height: 34, borderRadius: 8, flexShrink: 0, background: ready ? "linear-gradient(135deg,rgba(139,92,246,0.25),rgba(99,102,241,0.25))" : "rgba(71,85,105,0.15)", display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${ready ? "rgba(139,92,246,0.35)" : "rgba(71,85,105,0.3)"}` }}>
                                <Icon size={17} color={ready ? "#a78bfa" : "#475569"} />
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: ready ? "#c4b5fd" : "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</div>
                                <div style={{ fontSize: 10, color: "#475569", marginTop: 2 }}>{description}</div>
                              </div>
                              <div style={{ flexShrink: 0 }}>
                                {ready ? <CheckCircle2 size={16} color="#8b5cf6" /> : <MinusCircle size={16} color="#334155" />}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <button
                        onClick={openViewer}
                        style={{ width: "100%", padding: "12px 20px", borderRadius: 10, border: "none", background: "linear-gradient(135deg,#8b5cf6,#6366f1)", color: "white", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
                      >
                        <Eye size={17} />
                        Open UML Viewer
                      </button>
                    </>
                  )}
                </div>
              )}

              {/* SAST Auto-fix results */}
              {out && fixSummary && (fixSummary.initial_issues ?? 0) > 0 && (
                <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
                    <Shield size={14} color="#8b5cf6" />
                    SAST Auto-Fix Results
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
                    {[
                      { label: "Initial Issues", val: fixSummary.initial_issues,  color: "#ef4444" },
                      { label: "Semgrep Fixed",  val: fixSummary.semgrep_fixed,   color: "#10b981" },
                      { label: "LLM Fixed",      val: fixSummary.llm_fixed ?? 0,  color: "#3b82f6" },
                      { label: "Remaining",      val: fixSummary.remaining_issues, color: (fixSummary.remaining_issues ?? 0) === 0 ? "#10b981" : "#f59e0b" },
                    ].map(({ label, val, color }) => (
                      <div key={label} style={{ padding: 16, background: "#0f1419", borderRadius: 12, border: "1px solid #2d3548" }}>
                        <div style={{ fontSize: 10, color: "#64748b", marginBottom: 8, textTransform: "uppercase", fontWeight: 600, letterSpacing: "0.05em" }}>{label}</div>
                        <div style={{ fontSize: 28, fontWeight: 700, color }}>{val ?? 0}</div>
                      </div>
                    ))}
                  </div>

                  <div style={{ marginBottom: 16 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12 }}>
                      <span style={{ color: "#64748b" }}>
                        Fixed {(fixSummary.semgrep_fixed ?? 0) + (fixSummary.llm_fixed ?? 0)}/{fixSummary.initial_issues}
                      </span>
                      <span style={{ color: "#10b981", fontWeight: 700 }}>
                        {fixSummary.fix_rate_percent?.toFixed(0)}%
                      </span>
                    </div>
                    <div style={{ width: "100%", height: 8, background: "#0f1419", borderRadius: 999, overflow: "hidden" }}>
                      <div style={{ width: `${fixSummary.fix_rate_percent ?? 0}%`, height: "100%", background: "#10b981", transition: "width 0.5s ease", borderRadius: 999 }} />
                    </div>
                  </div>

                  {(fixSummary.remaining_issues ?? 0) === 0 && (
                    <div style={{ padding: 12, background: "rgba(16,185,129,0.1)", borderRadius: 8, border: "1px solid rgba(16,185,129,0.3)", display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#10b981", fontWeight: 500 }}>
                      <CheckCircle2 size={16} />
                      All {fixSummary.initial_issues} SAST vulnerabilities fixed!
                    </div>
                  )}
                </div>
              )}

              {/* ════════════════════════
                  DAST Panel  ← NEW
              ════════════════════════ */}
              {out && dast && dast.ok && (
                <DastPanel dast={dast} />
              )}

            </div>{/* end left column */}

            {/* ════════════════════════════════
                Right Column
            ════════════════════════════════ */}
            {out && (
              <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

                {/* Generated Code */}
                <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", display: "flex", alignItems: "center", gap: 8 }}>
                      <Code2 size={14} color="#8b5cf6" />
                      Generated Code
                      {/* Decision badge */}
                      {out.decision && (
                        <span style={{
                          fontSize: 9, padding: "2px 8px", borderRadius: 4, fontWeight: 700,
                          background: out.decision === "CODE_FIXED"
                            ? "rgba(16,185,129,0.15)"
                            : out.decision === "CODE_WITH_DAST_WARNINGS"
                            ? "rgba(245,158,11,0.15)"
                            : "rgba(99,102,241,0.15)",
                          color: out.decision === "CODE_FIXED"
                            ? "#10b981"
                            : out.decision === "CODE_WITH_DAST_WARNINGS"
                            ? "#f59e0b"
                            : "#818cf8",
                        }}>
                          {out.decision.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>
                    {out.original_code && out.original_code !== out.code && (
                      <button
                        onClick={() => setShowOriginal(!showOriginal)}
                        style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #8b5cf6", background: showOriginal ? "#8b5cf6" : "transparent", color: showOriginal ? "#fff" : "#8b5cf6", fontSize: 11, fontWeight: 600, cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.05em" }}
                      >
                        {showOriginal ? "Show Fixed" : "Show Original"}
                      </button>
                    )}
                  </div>
                  <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12, lineHeight: 1.7, background: "#0a0f1a", color: "#e2e8f0", padding: 20, borderRadius: 10, overflow: "auto", maxHeight: 500, fontFamily: "'Fira Code','Cascadia Code',monospace" }}>
                    {showOriginal ? out.original_code : out.code}
                  </pre>
                </div>

                {/* Security Report */}
                <div style={{ background: "#1a1f2e", borderRadius: 16, padding: 24, border: "1px solid #2d3548" }}>
                  <div
                    style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
                    onClick={() => setSecurityReportOpen(!securityReportOpen)}
                  >
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.1em", display: "flex", alignItems: "center", gap: 8 }}>
                      <Shield size={14} color="#a855f7" />
                      Security Report
                    </div>
                    <ChevronDown size={16} color="#64748b" style={{ transform: securityReportOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }} />
                  </div>

                  <div style={{ marginTop: 12, fontSize: 11, color: "#64748b" }}>
                    Policy: {out.report.policy_version ?? "LLM01-2025-v1"}
                  </div>

                  {securityReportOpen && (
                    <>
                      {/* DAST summary inside report */}
                      {dast && (
                        <div style={{ marginTop: 16, padding: 14, background: "#0a0f1a", borderRadius: 8, border: "1px solid #2d3548" }}>
                          <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, marginBottom: 10, display: "flex", alignItems: "center", gap: 6 }}>
                            <Activity size={12} color="#f59e0b" />
                            DAST Summary
                          </div>
                          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                            {[
                              { label: "Total",    val: dast.summary?.total,    color: "#94a3b8" },
                              { label: "Critical", val: dast.summary?.critical, color: "#ef4444" },
                              { label: "High",     val: dast.summary?.high,     color: "#f97316" },
                              { label: "Medium",   val: dast.summary?.medium,   color: "#f59e0b" },
                            ].map(({ label, val, color }) => (
                              <div key={label} style={{ textAlign: "center" }}>
                                <div style={{ fontSize: 18, fontWeight: 700, color }}>{val ?? 0}</div>
                                <div style={{ fontSize: 10, color: "#475569" }}>{label}</div>
                              </div>
                            ))}
                            <div style={{ marginLeft: "auto", fontSize: 11, color: dast.docker_available ? "#10b981" : "#f59e0b", display: "flex", alignItems: "center", gap: 4 }}>
                              {dast.docker_available ? "🐳 Docker" : "⚡ Pattern"}
                            </div>
                          </div>
                        </div>
                      )}

                      <div style={{ marginTop: 16, display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#8b5cf6", fontWeight: 500 }}>
                        <Code2 size={14} />
                        Enhanced Prompt
                      </div>
                      <pre style={{ whiteSpace: "pre-wrap", margin: "12px 0 0 0", fontSize: 11, background: "#0a0f1a", color: "#64748b", padding: 16, borderRadius: 8, maxHeight: 300, overflow: "auto", fontFamily: "monospace", lineHeight: 1.6 }}>
                        {out.report.prompt_after_enhancement}
                      </pre>
                    </>
                  )}
                </div>
              </div>
            )}

          </div>
        </div>
      </div>

      {/* ── UML Modal ── */}
      {uml && !uml.error && (
        <UmlViewerModal
          open={umlOpen}
          uml={uml}
          tab={umlTab}
          setTab={setUmlTab}
          onClose={() => setUmlOpen(false)}
          code={out?.code ?? null}
          cir={uml?.cir ?? null}
          umlAiApi={UML_AI_API}
          aiStore={aiUmlCache}
          setAiStore={setAiUmlCache}
        />
      )}

      {/* ── History Panel ── */}
      <ChatHistoryPanel
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onRestore={onRestoreHistory}
      />
    </div>
  );
}
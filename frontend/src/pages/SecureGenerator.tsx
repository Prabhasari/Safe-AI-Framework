// frontend/src/pages/SecureGenerator.tsx

import { useState } from "react";
import UmlViewerModal, { type DiagramType, type AiUmlStore } from "../components/UmlViewerModal.tsx";
import ChatHistoryPanel, { type HistoryEntry } from "../components/ChatHistoryPanel.tsx";
import DastPanel, { type DastReport } from "../components/DastPanel.tsx";
import {
  CheckCircle2, MinusCircle, Shield, Sparkles,
  Copy, Check, Code2, ChevronDown, Zap, Clock, ArrowLeft,
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
  dast?: DastReport;
  dast_llm_fix?: LlmFixReport;
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
  const [sastOpen, setSastOpen] = useState(false);

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
    <div style={{ display: "flex", width: "100vw", height: "100vh", background: "#1a1328", overflow: "hidden" }}>

      {/* ── Sidebar ── */}
      <div style={{
        width: 60, background: "#120e1f", display: "flex", flexDirection: "column",
        alignItems: "center", padding: "20px 0", gap: 20, borderRight: "1px solid #2d1f45",
      }}>
        <button
          onClick={() => window.history.back()}
          style={{ width: 40, height: 40, background: "none", border: "none", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer", padding: 0 }}
        >
          <ArrowLeft size={22} color="#ffffff" strokeWidth={2.5} />
        </button>

        <div style={{ width: 40, height: 40, borderRadius: 12, background: "#4F0C87", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Zap size={24} color="#fff" />
        </div>

        <button
          onClick={() => setHistoryOpen(true)}
          title="View generation history"
          style={{
            width: 40, height: 40, borderRadius: 10, padding: 0,
            background: historyOpen ? "rgba(79,12,135,0.25)" : "transparent",
            border:     historyOpen ? "1px solid #4F0C87"    : "1px solid transparent",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "pointer", transition: "background .2s, border-color .2s",
          }}
        >
          <Clock size={20} color={historyOpen ? "#c084fc" : "#ffffff"} />
        </button>
      </div>

      {/* ── Main ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

        {/* Header */}
        <div style={{ padding: "20px 32px", borderBottom: "1px solid #2d1f45", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#ffffff" }}>
              Secure Code Generator
            </h1>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#c4b5d6" }}>
              AI-powered code generation with SAST · DAST · UML visualization
            </p>
          </div>

          {/* Pipeline status badges — shown while loading */}
          {loading && (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {["SAST", "DAST", "UML"].map((stage) => (
                <span key={stage} style={{
                  fontSize: 10, padding: "3px 10px", borderRadius: 4, fontWeight: 700,
                  background: "rgba(79,12,135,0.3)", color: "#ffffff",
                  border: "1px solid rgba(79,12,135,0.6)",
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
              <div style={{ background: "#231636", borderRadius: 16, padding: 24, border: "1px solid #3d2060" }}>
                <label style={{ display: "block", marginBottom: 12, fontSize: 11, fontWeight: 600, color: "#c4b5d6", textTransform: "uppercase", letterSpacing: "0.1em" }}>
                  Describe the code you want to generate
                </label>
                <textarea
                  rows={6}
                  style={{ width: "100%", padding: 16, borderRadius: 12, border: "1px solid #3d2060", fontSize: 13, fontFamily: "inherit", resize: "vertical", outline: "none", boxSizing: "border-box", background: "#150f24", color: "#ffffff", transition: "border-color 0.2s", lineHeight: 1.6 }}
                  placeholder="e.g., give javascript code for student management system..."
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onFocus={(e) => (e.target.style.borderColor = "#4F0C87")}
                  onBlur={(e)  => (e.target.style.borderColor = "#3d2060")}
                />

                <div style={{ marginTop: 20, display: "flex", gap: 12 }}>
                  <button
                    onClick={onGenerate}
                    disabled={loading || !prompt.trim()}
                    style={{
                      flex: 1, padding: "14px 24px", borderRadius: 10, border: "none",
                      background: loading || !prompt.trim() ? "#3d2060" : "#4F0C87",
                      color: "#ffffff", fontSize: 14, fontWeight: 600,
                      cursor: loading || !prompt.trim() ? "not-allowed" : "pointer",
                      display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                      transition: "background 0.2s",
                    }}
                  >
                    <Sparkles size={18} />
                    {loading ? "Generating & Analyzing..." : "Generate Secure Code"}
                  </button>

                  {out?.code && (
                    <button
                      onClick={copyCode}
                      style={{ padding: "14px 20px", borderRadius: 10, border: "1px solid #3d2060", background: copied ? "#4F0C87" : "transparent", color: "#ffffff", fontSize: 14, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}
                    >
                      {copied ? <Check size={18} /> : <Copy size={18} />}
                    </button>
                  )}
                </div>
              </div>

              {/* UML diagrams card */}
              {out && (
                <div style={{ background: "#231636", borderRadius: 16, padding: 24, border: "1px solid #3d2060" }}>
                  <div style={{ fontSize: 11, fontWeight: 600, color: "#c4b5d6", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 20, display: "flex", alignItems: "center", gap: 8 }}>
                    <Network size={14} color="#c084fc" />
                    UML Diagrams
                  </div>

                  {!uml || uml.error ? (
                    <div style={{ padding: 16, background: "#150f24", borderRadius: 8, border: "1px solid #3d2060", color: "#c4b5d6", fontSize: 13, textAlign: "center" }}>
                      {uml?.error ? `UML generation: ${uml.error}` : "No UML diagrams available (e.g. non-Java/Python code)."}
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 18 }}>
                        {DIAGRAM_META.map(({ type, label, description, svgKey, Icon }) => {
                          const ready = Boolean(uml[svgKey]);
                          return (
                            <div key={type} style={{ padding: "12px 14px", background: "#150f24", borderRadius: 10, border: `1px solid ${ready ? "#4F0C87" : "#3d2060"}`, display: "flex", alignItems: "center", gap: 12 }}>
                              <div style={{ width: 34, height: 34, borderRadius: 8, flexShrink: 0, background: ready ? "rgba(79,12,135,0.3)" : "rgba(61,32,96,0.3)", display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${ready ? "rgba(79,12,135,0.5)" : "rgba(61,32,96,0.4)"}` }}>
                                <Icon size={17} color={ready ? "#c084fc" : "#7a5a9a"} />
                              </div>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: ready ? "#ffffff" : "#9a7ab5", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{label}</div>
                                <div style={{ fontSize: 10, color: "#9a7ab5", marginTop: 2 }}>{description}</div>
                              </div>
                              <div style={{ flexShrink: 0 }}>
                                {ready ? <CheckCircle2 size={16} color="#c084fc" /> : <MinusCircle size={16} color="#4d3566" />}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                      <button
                        onClick={openViewer}
                        style={{ width: "100%", padding: "12px 20px", borderRadius: 10, border: "none", background: "#4F0C87", color: "#ffffff", fontSize: 13, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}
                      >
                        <Eye size={17} />
                        Open UML Viewer
                      </button>
                    </>
                  )}
                </div>
              )}

            </div>{/* end left column */}

            {/* ════════════════════════════════
                Right Column
            ════════════════════════════════ */}
            {out && (
              <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

                {/* Generated Code */}
                <div style={{ background: "#231636", borderRadius: 16, padding: 24, border: "1px solid #3d2060" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#c4b5d6", textTransform: "uppercase", letterSpacing: "0.1em", display: "flex", alignItems: "center", gap: 8 }}>
                      <Code2 size={14} color="#c084fc" />
                      Generated Code
                      {/* Decision badge */}
                      {out.decision && (
                        <span style={{
                          fontSize: 9, padding: "2px 8px", borderRadius: 4, fontWeight: 700,
                          background: out.decision === "CODE_FIXED"
                            ? "rgba(16,185,129,0.15)"
                            : out.decision === "CODE_WITH_DAST_WARNINGS"
                            ? "rgba(245,158,11,0.15)"
                            : "rgba(79,12,135,0.25)",
                          color: out.decision === "CODE_FIXED"
                            ? "#10b981"
                            : out.decision === "CODE_WITH_DAST_WARNINGS"
                            ? "#f59e0b"
                            : "#ffffff",
                        }}>
                          {out.decision.replace(/_/g, " ")}
                        </span>
                      )}
                    </div>
                    {out.original_code && out.original_code !== out.code && (
                      <button
                        onClick={() => setShowOriginal(!showOriginal)}
                        style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #4F0C87", background: showOriginal ? "#4F0C87" : "transparent", color: "#ffffff", fontSize: 11, fontWeight: 600, cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.05em" }}
                      >
                        {showOriginal ? "Show Fixed" : "Show Original"}
                      </button>
                    )}
                  </div>
                  <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12, lineHeight: 1.7, background: "#110c1e", color: "#ffffff", padding: 20, borderRadius: 10, overflow: "auto", maxHeight: 500, fontFamily: "'Fira Code','Cascadia Code',monospace" }}>
                    {showOriginal ? out.original_code : out.code}
                  </pre>
                </div>

              </div>
            )}

          </div>

          {/* ════════════════════════════════════════════════════════════
              Security Report — full-width below both columns
          ════════════════════════════════════════════════════════════ */}
          {out && (
            <div style={{ marginTop: 24, maxWidth: 1600 }}>
              <div style={{ background: "#231636", borderRadius: 16, border: "1px solid #3d2060", overflow: "hidden" }}>

                {/* ── Collapsible header ── */}
                <div
                  onClick={() => setSecurityReportOpen(!securityReportOpen)}
                  style={{
                    padding: "18px 28px", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    borderBottom: securityReportOpen ? "1px solid #3d2060" : "none",
                    background: securityReportOpen ? "#1e1030" : "transparent",
                    transition: "background 0.2s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: "rgba(79,12,135,0.3)", border: "1px solid rgba(192,132,252,0.3)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <Shield size={15} color="#c084fc" />
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#ffffff", letterSpacing: "0.04em" }}>
                        Security Report
                      </div>
                      <div style={{ fontSize: 11, color: "#9a7ab5", marginTop: 1 }}>
                        Policy: {out.report.policy_version ?? "LLM01-2025-v1"}
                        {fixSummary && (
                          <span style={{ marginLeft: 12 }}>
                            · SAST{" "}
                            <span style={{ color: (fixSummary.remaining_issues ?? 0) === 0 ? "#10b981" : "#f59e0b", fontWeight: 600 }}>
                              {(fixSummary.remaining_issues ?? 0) === 0 ? "✔ clean" : `${fixSummary.remaining_issues} remaining`}
                            </span>
                          </span>
                        )}
                        {dast && dast.ok && (
                          <span style={{ marginLeft: 12 }}>
                            · DAST{" "}
                            <span style={{ color: (dast.summary?.total ?? 0) === 0 ? "#10b981" : "#f97316", fontWeight: 600 }}>
                              {(dast.summary?.total ?? 0) === 0 ? "✔ clean" : `${dast.summary?.total} finding(s)`}
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Quick score pills */}
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {fixSummary && (fixSummary.initial_issues ?? 0) > 0 && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 20, background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)" }}>
                        <Shield size={11} color="#10b981" />
                        <span style={{ fontSize: 11, color: "#10b981", fontWeight: 600 }}>
                          SAST {fixSummary.fix_rate_percent?.toFixed(0)}% fixed
                        </span>
                      </div>
                    )}
                    {dast && dast.ok && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 20, background: dast.docker_available ? "rgba(99,102,241,0.12)" : "rgba(245,158,11,0.1)", border: `1px solid ${dast.docker_available ? "rgba(99,102,241,0.3)" : "rgba(245,158,11,0.25)"}` }}>
                        <span style={{ fontSize: 11, color: dast.docker_available ? "#a5b4fc" : "#f59e0b", fontWeight: 600 }}>
                          {dast.docker_available ? "🐳 Docker" : "⚡ Pattern"} · {dast.summary?.total ?? 0} finding(s)
                        </span>
                      </div>
                    )}
                    <ChevronDown
                      size={16} color="#9a7ab5"
                      style={{ transform: securityReportOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.25s", marginLeft: 4 }}
                    />
                  </div>
                </div>

                {/* ── Expanded body ── */}
                {securityReportOpen && (
                  <div style={{ padding: "28px 28px 24px" }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>

                      {/* ── Left: SAST ── */}
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: "#c4b5d6", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ width: 3, height: 14, borderRadius: 2, background: "#c084fc" }} />
                          SAST Auto-Fix Results
                        </div>

                        {fixSummary && (fixSummary.initial_issues ?? 0) > 0 ? (
                          <>
                            {/* 4 metric cards in 2×2 — clickable to expand findings */}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 16 }}>
                              {[
                                { label: "Initial Issues", val: fixSummary.initial_issues,  color: "#ef4444", bg: "rgba(239,68,68,0.08)",   border: "rgba(239,68,68,0.2)"   },
                                { label: "Semgrep Fixed",  val: fixSummary.semgrep_fixed,   color: "#10b981", bg: "rgba(16,185,129,0.08)",  border: "rgba(16,185,129,0.2)"  },
                                { label: "LLM Fixed",      val: fixSummary.llm_fixed ?? 0,  color: "#60a5fa", bg: "rgba(96,165,250,0.08)",  border: "rgba(96,165,250,0.2)"  },
                                { label: "Remaining",      val: fixSummary.remaining_issues, color: (fixSummary.remaining_issues ?? 0) === 0 ? "#10b981" : "#f59e0b", bg: (fixSummary.remaining_issues ?? 0) === 0 ? "rgba(16,185,129,0.08)" : "rgba(245,158,11,0.08)", border: (fixSummary.remaining_issues ?? 0) === 0 ? "rgba(16,185,129,0.2)" : "rgba(245,158,11,0.2)" },
                              ].map(({ label, val, color, bg, border }) => (
                                <div key={label} style={{ padding: "14px 16px", background: bg, borderRadius: 10, border: `1px solid ${border}` }}>
                                  <div style={{ fontSize: 9, color: "#9a7ab5", marginBottom: 6, textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.06em" }}>{label}</div>
                                  <div style={{ fontSize: 28, fontWeight: 800, color, lineHeight: 1 }}>{val ?? 0}</div>
                                </div>
                              ))}
                            </div>

                            {/* Progress bar */}
                            <div style={{ padding: "12px 14px", background: "#110c1e", borderRadius: 10, border: "1px solid #2d1f45", marginBottom: 10 }}>
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 11 }}>
                                <span style={{ color: "#9a7ab5" }}>
                                  Fixed {(fixSummary.semgrep_fixed ?? 0) + (fixSummary.llm_fixed ?? 0)} of {fixSummary.initial_issues} issues
                                </span>
                                <span style={{ color: "#10b981", fontWeight: 700 }}>
                                  {fixSummary.fix_rate_percent?.toFixed(0)}%
                                </span>
                              </div>
                              <div style={{ width: "100%", height: 7, background: "#1e1530", borderRadius: 999, overflow: "hidden" }}>
                                <div style={{ width: `${fixSummary.fix_rate_percent ?? 0}%`, height: "100%", background: "linear-gradient(90deg, #4F0C87, #10b981)", transition: "width 0.6s ease", borderRadius: 999 }} />
                              </div>
                            </div>

                            {/* Success banner */}
                            {(fixSummary.remaining_issues ?? 0) === 0 && (
                              <div style={{ marginBottom: 10, padding: "10px 14px", background: "rgba(16,185,129,0.08)", borderRadius: 8, border: "1px solid rgba(16,185,129,0.25)", display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#10b981", fontWeight: 600 }}>
                                <CheckCircle2 size={14} />
                                All {fixSummary.initial_issues} SAST vulnerabilities resolved!
                              </div>
                            )}

                            {/* ── Clickable findings toggle ── */}
                            {(() => {
                              const cat = out?.report?.semgrep?.categorized_findings;
                              const allFindings = [
                                ...(cat?.initially_auto_fixable ?? []),
                                ...(cat?.initially_manual_only ?? []),
                              ];
                              if (allFindings.length === 0) return null;

                              const SEV_COLOR: Record<string, string> = { CRITICAL: "#ef4444", ERROR: "#ef4444", HIGH: "#f97316", MEDIUM: "#f59e0b", WARNING: "#f59e0b", LOW: "#60a5fa", INFO: "#94a3b8" };
                              const SEV_BG:    Record<string, string> = { CRITICAL: "rgba(239,68,68,0.1)", ERROR: "rgba(239,68,68,0.1)", HIGH: "rgba(249,115,22,0.1)", MEDIUM: "rgba(245,158,11,0.1)", WARNING: "rgba(245,158,11,0.1)", LOW: "rgba(96,165,250,0.1)", INFO: "rgba(148,163,184,0.1)" };

                              return (
                                <div>
                                  {/* Toggle button */}
                                  <button
                                    onClick={() => setSastOpen(!sastOpen)}
                                    style={{
                                      width: "100%", padding: "10px 14px", borderRadius: 9,
                                      background: sastOpen ? "#1e1030" : "#110c1e",
                                      border: `1px solid ${sastOpen ? "#4F0C87" : "#2d1f45"}`,
                                      color: "#c4b5d6", fontSize: 12, fontWeight: 600,
                                      cursor: "pointer", display: "flex", alignItems: "center",
                                      justifyContent: "space-between", transition: "all 0.2s",
                                    }}
                                  >
                                    <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
                                      <Shield size={13} color="#c084fc" />
                                      View {allFindings.length} Detected Vulnerabilit{allFindings.length === 1 ? "y" : "ies"}
                                    </span>
                                    <ChevronDown size={14} color="#9a7ab5" style={{ transform: sastOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
                                  </button>

                                  {/* Findings list */}
                                  {sastOpen && (
                                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                                      {allFindings.map((f, i) => {
                                        const sev = (f.severity ?? "INFO").toUpperCase();
                                        const color = SEV_COLOR[sev] ?? "#94a3b8";
                                        const bg    = SEV_BG[sev]    ?? "rgba(148,163,184,0.1)";
                                        return (
                                          <div key={i} style={{
                                            padding: "10px 12px", borderRadius: 8,
                                            background: "#0d0818",
                                            border: `1px solid ${color}30`,
                                          }}>
                                            {/* Row 1: badge + rule id */}
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                                              <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, color, background: bg, border: `1px solid ${color}40`, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                                {sev}
                                              </span>
                                              <span style={{ fontSize: 10, color: "#6b7a9a", fontFamily: "monospace" }}>
                                                {f.check_id ?? "unknown"}
                                              </span>
                                              {f.has_autofix && (
                                                <span style={{ marginLeft: "auto", fontSize: 9, color: "#10b981", background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)", padding: "1px 6px", borderRadius: 4, fontWeight: 600 }}>
                                                  ✔ auto-fixed
                                                </span>
                                              )}
                                            </div>
                                            {/* Row 2: message */}
                                            <div style={{ fontSize: 11, color: "#c4b5d6", lineHeight: 1.5, marginBottom: f.path ? 5 : 0 }}>
                                              {f.message ?? "No description"}
                                            </div>
                                            {/* Row 3: file + line */}
                                            {f.path && (
                                              <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 4 }}>
                                                <Code2 size={10} color={color} />
                                                <span style={{ fontSize: 10, color, fontFamily: "monospace", fontWeight: 600 }}>
                                                  {f.path}{f.start?.line ? ` : line ${f.start.line}` : ""}
                                                </span>
                                              </div>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              );
                            })()}
                          </>
                        ) : (
                          /* ── No issues found ── */
                          <div style={{ padding: "24px 16px", background: "rgba(16,185,129,0.06)", borderRadius: 10, border: "1px solid rgba(16,185,129,0.2)", textAlign: "center" }}>
                            <CheckCircle2 size={28} color="#10b981" style={{ marginBottom: 10 }} />
                            <div style={{ fontSize: 14, color: "#10b981", fontWeight: 700, marginBottom: 4 }}>No SAST Issues Found</div>
                            <div style={{ fontSize: 11, color: "#9a7ab5", lineHeight: 1.5 }}>
                              Static analysis completed — no vulnerabilities detected in the generated code.
                            </div>
                          </div>
                        )}
                      </div>

                      {/* ── Right: DAST ── */}
                      <div>
                        <div style={{ fontSize: 11, fontWeight: 700, color: "#c4b5d6", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
                          <div style={{ width: 3, height: 14, borderRadius: 2, background: "#f59e0b" }} />
                          Dynamic Analysis (DAST)
                        </div>

                        {dast && dast.ok ? (
                          <DastPanel dast={dast} />
                        ) : (
                          <div style={{ padding: "20px 16px", background: "#110c1e", borderRadius: 10, border: "1px solid #2d1f45", textAlign: "center" }}>
                            <div style={{ fontSize: 13, color: "#9a7ab5" }}>DAST results unavailable</div>
                          </div>
                        )}
                      </div>

                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>

      {/* ── UML Modal ── */}
      {uml && !uml.error && (
        <UmlViewerModal
          open={umlOpen}
          uml={uml as UmlReport}
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
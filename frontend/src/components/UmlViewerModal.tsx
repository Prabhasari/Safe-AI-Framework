import React, { useEffect, useMemo, useRef, useState } from "react";
import { X, Box, Boxes, GitBranch, Eye } from "lucide-react";

export type DiagramType = "class" | "package" | "sequence" | "component";

type UmlValidation = {
  ok: boolean;
  errors: string[];
};

type UmlReport = {
  ok?: boolean;
  file_count?: number;
  error?: string | null;
  class_svg?: string | null;
  package_svg?: string | null;
  sequence_svg?: string | null;
  component_svg?: string | null;
  validation?: Partial<Record<DiagramType, UmlValidation>>;
};

type AiUmlResponse = {
  ok?: boolean;
  diagram_type: DiagramType;
  plantuml: string;
  svg?: string | null;
  error?: string | null;
};

export type AiUmlStore = Partial<
  Record<DiagramType, { svg: string | null; plantuml?: string }>
>;

type UmlSource = "rule" | "ai";

function errMsg(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try {
    return JSON.stringify(e);
  } catch {
    return "Unknown error";
  }
}

export default function UmlViewerModal({
  open,
  uml,
  tab,
  setTab,
  onClose,
  code,
  cir,
  umlAiApi,
  aiStore,
  setAiStore,
}: {
  open: boolean;
  uml: UmlReport;
  tab: DiagramType;
  setTab: React.Dispatch<React.SetStateAction<DiagramType>>;
  onClose: () => void;

  /** AI generation inputs */
  code: string | null;
  cir: unknown | null;
  umlAiApi: string;
  aiStore: AiUmlStore;
  setAiStore: React.Dispatch<React.SetStateAction<AiUmlStore>>;
}) {

  const [source, setSource] = useState<UmlSource>("rule");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // prevent duplicate in-flight requests per tab
  const inflightRef = useRef<Partial<Record<DiagramType, boolean>>>({});

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const validation = uml?.validation || {};
  const vinfo = (k: DiagramType) => validation[k];

  const ruleSvgs = useMemo(
    () =>
      ({
        class: uml?.class_svg ?? null,
        package: uml?.package_svg ?? null,
        sequence: uml?.sequence_svg ?? null,
        component: uml?.component_svg ?? null,
      }) as Record<DiagramType, string | null>,
    [uml]
  );

  const aiSvgs = useMemo(
    () =>
      ({
        class: aiStore.class?.svg ?? null,
        package: aiStore.package?.svg ?? null,
        sequence: aiStore.sequence?.svg ?? null,
        component: aiStore.component?.svg ?? null,
      }) as Record<DiagramType, string | null>,
    [aiStore]
  );

  const hasAnyAi = useMemo(
    () => Boolean(aiSvgs.class || aiSvgs.package || aiSvgs.sequence || aiSvgs.component),
    [aiSvgs]
  );

  const effectiveSource: UmlSource = source === "ai" && !hasAnyAi ? "rule" : source;

  const activeSvg = useMemo(() => {
    return effectiveSource === "ai" ? aiSvgs[tab] : ruleSvgs[tab];
  }, [effectiveSource, tab, aiSvgs, ruleSvgs]);

  const tabEnabled = useMemo(() => {
    return (k: DiagramType) => {
      const ruleHasSvg = !!ruleSvgs[k];
      const ruleHasValidation = !!validation[k];
      const aiHasSvg = !!aiSvgs[k];
      return ruleHasSvg || ruleHasValidation || aiHasSvg;
    };
  }, [aiSvgs, ruleSvgs, validation]);

  const canGenerateAi = useMemo(() => Boolean(cir || code), [cir, code]);

  const generateAiFor = async (k: DiagramType) => {
    if (!canGenerateAi) {
      setAiError("No code/CIR available to generate AI UML.");
      return;
    }
    if (aiSvgs[k]) return;
    if (inflightRef.current[k]) return;

    inflightRef.current[k] = true;
    setAiLoading(true);
    setAiError(null);

    try {
      const payload: { diagram_type: DiagramType; cir?: unknown | null; code?: string | null } = {
        diagram_type: k,
        cir: cir ?? null,
        code: cir ? null : code ?? null,
      };

      const res = await fetch(umlAiApi, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status}: ${txt}`);
      }

      const data: AiUmlResponse = await res.json();
      if (data.error) throw new Error(data.error);

      const svg = data.svg ?? null;

      setAiStore((prev) => ({
        ...prev,
        [data.diagram_type]: { svg, plantuml: data.plantuml },
      }));
    } catch (e) {
      setAiError(errMsg(e));
    } finally {
      inflightRef.current[k] = false;
      setAiLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    if (source !== "ai") return;
    if (aiSvgs[tab]) return;
    void generateAiFor(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, source, tab]);

  if (!open || !uml || uml.error) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,0.55)",
        display: "flex",
        alignItems: "stretch",
        justifyContent: "stretch",
        zIndex: 1000,
        padding: 0,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100vw",
          height: "100vh",
          background: "#ffffff",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "16px 20px 12px 20px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 10,
                background: "#e0f2fe",
                display: "grid",
                placeItems: "center",
                border: "1px solid #bae6fd",
              }}
            >
              <Eye size={18} color="#0369a1" />
            </div>

            <div>
              <div style={{ fontWeight: 700, fontSize: 16, color: "#0f172a" }}>
                UML Diagram Viewer
              </div>
              <div style={{ fontSize: 12, color: "#64748b" }}>
                AI mode auto-generates per tab
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {/* Source toggle */}
            <div
              style={{
                display: "inline-flex",
                border: "1px solid #e2e8f0",
                borderRadius: 999,
                overflow: "hidden",
                background: "#f8fafc",
              }}
            >
              <button
                onClick={() => setSource("rule")}
                style={{
                  padding: "8px 12px",
                  border: "none",
                  cursor: "pointer",
                  background: effectiveSource === "rule" ? "#e0f2fe" : "transparent",
                  color: effectiveSource === "rule" ? "#0369a1" : "#475569",
                  fontWeight: 700,
                  fontSize: 12,
                }}
              >
                Rule-based
              </button>

              <button
                onClick={() => {
                  if (!canGenerateAi) {
                    setAiError("Generate code first (code/CIR required for AI UML).");
                    return;
                  }
                  setSource("ai");
                  void generateAiFor(tab);
                }}
                disabled={!canGenerateAi}
                style={{
                  padding: "8px 12px",
                  border: "none",
                  cursor: !canGenerateAi ? "not-allowed" : "pointer",
                  background: effectiveSource === "ai" ? "#dcfce7" : "transparent",
                  color: effectiveSource === "ai" ? "#166534" : "#475569",
                  fontWeight: 700,
                  fontSize: 12,
                  opacity: !canGenerateAi ? 0.5 : 1,
                }}
                title={!canGenerateAi ? "Generate code first" : "Switch to AI (auto-generates this tab)"}
              >
                AI-based
              </button>
            </div>

            <button
              onClick={onClose}
              style={{
                border: "1px solid #e2e8f0",
                background: "#ffffff",
                cursor: "pointer",
                color: "#475569",
                padding: 8,
                borderRadius: 10,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              aria-label="Close UML viewer"
              title="Close"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Status row */}
        {(aiError || (aiLoading && effectiveSource === "ai" && !aiSvgs[tab])) && (
          <div
            style={{
              padding: "10px 16px",
              background: aiError ? "#fef2f2" : "#f1f5f9",
              borderBottom: "1px solid #e2e8f0",
              color: aiError ? "#991b1b" : "#334155",
              fontSize: 13,
            }}
          >
            {aiError ? aiError : `Generating AI ${tab} diagram...`}
          </div>
        )}

        {/* Tabs */}
        <div
          style={{
            padding: "10px 16px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <TabButton
            label="Class Diagram"
            icon={<Box size={16} />}
            active={tab === "class"}
            disabled={!tabEnabled("class")}
            onClick={() => setTab("class")}
          />
          <TabButton
            label="Package Diagram"
            icon={<Boxes size={16} />}
            active={tab === "package"}
            disabled={!tabEnabled("package")}
            onClick={() => setTab("package")}
          />
          <TabButton
            label="Sequence Diagram"
            icon={<GitBranch size={16} />}
            active={tab === "sequence"}
            disabled={!tabEnabled("sequence")}
            onClick={() => setTab("sequence")}
          />
          <TabButton
            label="Component Diagram"
            icon={<Box size={16} />}
            active={tab === "component"}
            disabled={!tabEnabled("component")}
            onClick={() => setTab("component")}
          />
        </div>

        {/* Content */}
        <div style={{ padding: 16, flex: 1, overflow: "hidden", background: "#f8fafc" }}>
          {activeSvg ? (
            <DiagramCard
              title={`${effectiveSource === "ai" ? "AI" : "Rule"} • ${tab.toUpperCase()} Diagram`}
              svg={activeSvg}
            />
          ) : effectiveSource === "rule" ? (
            <ValidationCard title={`${tab.toUpperCase()} Diagram`} info={vinfo(tab)} />
          ) : (
            <EmptyCard
              title={`${tab.toUpperCase()} Diagram (AI)`}
              message={aiLoading ? "Generating AI diagram..." : "Click AI-based toggle to generate this tab."}
            />
          )}
        </div>

        <style>{`
          .uml-svg svg { width: 100% !important; height: auto !important; }
          .uml-svg svg text, .uml-svg svg a, .uml-svg svg a text { text-decoration: none !important; }
          .uml-svg svg a:link, .uml-svg svg a:visited { fill: inherit !important; color: inherit !important; }
        `}</style>
      </div>
    </div>
  );
}

function TabButton({
  label,
  icon,
  active,
  disabled,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "8px 14px",
        borderRadius: 999,
        border: active ? "1px solid #0ea5e9" : "1px solid #cbd5e1",
        background: active ? "#e0f2fe" : "#ffffff",
        color: active ? "#0369a1" : "#475569",
        fontSize: 13,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
      title={label}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function DiagramCard({ title, svg }: { title: string; svg: string }) {
  return (
    <div
      style={{
        height: "100%",
        background: "#ffffff",
        borderRadius: 10,
        border: "1px solid #e2e8f0",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a", marginBottom: 8 }}>
        {title}
      </div>

      <div
        className="uml-svg"
        style={{
          flex: 1,
          overflow: "auto",
          borderRadius: 8,
          background: "#ffffff",
          border: "1px solid #f1f5f9",
        }}
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  );
}

function EmptyCard({ title, message }: { title: string; message: string }) {
  return (
    <div
      style={{
        height: "100%",
        background: "#ffffff",
        borderRadius: 10,
        border: "1px solid #e2e8f0",
        padding: 16,
        color: "#64748b",
        fontSize: 13,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8, color: "#0f172a" }}>{title}</div>
      {message}
    </div>
  );
}

function ValidationCard({ title, info }: { title: string; info?: { ok: boolean; errors: string[] } }) {
  if (!info) return <EmptyCard title={title} message="No SVG available and no validation info was returned." />;

  return (
    <div
      style={{
        height: "100%",
        background: "#ffffff",
        borderRadius: 10,
        border: "1px solid #e2e8f0",
        padding: 16,
        overflow: "auto",
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 8, color: "#0f172a" }}>{title}</div>

      <div
        style={{
          display: "inline-block",
          padding: "4px 10px",
          borderRadius: 999,
          fontSize: 12,
          fontWeight: 700,
          background: info.ok ? "#dcfce7" : "#fee2e2",
          color: info.ok ? "#166534" : "#991b1b",
          border: `1px solid ${info.ok ? "#86efac" : "#fca5a5"}`,
          marginBottom: 12,
        }}
      >
        {info.ok ? "VALID" : "INVALID"}
      </div>

      {!info.ok && (
        <ul style={{ margin: 0, paddingLeft: 18, color: "#475569", fontSize: 13, lineHeight: 1.6 }}>
          {(info.errors || []).slice(0, 20).map((err, idx) => (
            <li key={idx}>{err}</li>
          ))}
        </ul>
      )}

      {info.ok && (
        <div style={{ marginTop: 12, color: "#166534", fontSize: 13 }}>
          Diagram validated, but SVG is missing (render step may have failed).
        </div>
      )}
    </div>
  );
}

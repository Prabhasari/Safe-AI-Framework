import { useMemo, useState } from "react";
import { Sparkles } from "lucide-react";

/* ---------- Shared Types ---------- */
export type DiagramType = "class" | "package" | "sequence" | "component";

/* ---------- AI UML Types ---------- */
type AiUmlResponse = {
  ok?: boolean;
  diagram_type: DiagramType;
  plantuml: string;
  svg?: string | null;
  error?: string | null;
};

export type AiUmlResult = {
  diagram_type: DiagramType;
  svg: string | null;
  plantuml: string;
};

type Props = {
  code?: string | null;
  cir?: unknown | null;
  umlAiApi: string;
  title?: string;

  /** ✅ NEW: Send AI UML output to parent */
  onResult?: (r: AiUmlResult) => void;
};

export default function AiUmlPanel({
  code,
  cir,
  umlAiApi,
  title = "🤖 AI UML (Experimental – LLM-based diagrams)",
  onResult,
}: Props) {
  const [aiDiagramType, setAiDiagramType] = useState<DiagramType>("class");
  const [aiSvg, setAiSvg] = useState<string | null>(null);
  const [aiPlantuml, setAiPlantuml] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const sourceLabel = useMemo(() => (cir ? "CIR" : "Code"), [cir]);

    const onGenerateAiUml = async () => {
    if (!code && !cir) {
      alert("Please generate code first, then request AI UML.");
      return;
    }

    setAiLoading(true);
    setAiError(null);
    setAiSvg(null);
    setAiPlantuml(null);

    try {
      const payload: {
        diagram_type: DiagramType;
        cir?: unknown | null;
        code?: string | null;
      } = {
        diagram_type: aiDiagramType,
        cir: cir ?? null,
        code: cir ? null : code ?? null,
      };

      console.log("AI UML payload:", payload);

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
      setAiSvg(svg);
      setAiPlantuml(data.plantuml);

      onResult?.({ diagram_type: data.diagram_type, svg, plantuml: data.plantuml });
    } catch (err) {
      console.error(err);
      const msg =
        err instanceof Error
          ? err.message
          : typeof err === "string"
          ? err
          : "Failed to generate AI UML diagram.";
      setAiError(msg);
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div style={{ marginTop: 24 }}>
      <h2 style={{ margin: "0 0 12px 0", fontSize: 18, fontWeight: 600, color: "#1e293b" }}>
        {title}
      </h2>

      <div
        style={{
          background: "#ffffff",
          padding: 20,
          borderRadius: 8,
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
        }}
      >
        <p style={{ marginTop: 0, marginBottom: 12, fontSize: 13, color: "#64748b" }}>
          This uses the <strong>uml-gen-ai</strong> service to generate UML using{" "}
          <strong>CIR-first</strong> (fallback to raw code).
        </p>

        {!code && !cir ? (
          <div
            style={{
              padding: 12,
              background: "#fef9c3",
              borderRadius: 6,
              color: "#854d0e",
              fontSize: 13,
            }}
          >
            Generate code first, then you can request AI UML diagrams.
          </div>
        ) : (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 16 }}>
              <div style={{ fontSize: 13, color: "#475569", marginRight: 8 }}>Diagram type</div>

              <select
                value={aiDiagramType}
                onChange={(e) => setAiDiagramType(e.target.value as DiagramType)}
                style={{
                  padding: "8px 10px",
                  borderRadius: 6,
                  border: "1px solid #cbd5e1",
                  fontSize: 13,
                  color: "#0f172a",
                  background: "white",
                }}
              >
                <option value="class">Class diagram</option>
                <option value="package">Package diagram</option>
                <option value="sequence">Sequence diagram</option>
                <option value="component">Component diagram</option>
              </select>

              <button
                onClick={onGenerateAiUml}
                disabled={aiLoading}
                style={{
                  padding: "8px 16px",
                  borderRadius: 8,
                  border: "none",
                  background: aiLoading ? "#cbd5e1" : "#22c55e",
                  color: "white",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: aiLoading ? "not-allowed" : "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <Sparkles size={16} />
                {aiLoading ? "Generating AI UML..." : "Generate AI UML"}
              </button>

              <span
                style={{
                  fontSize: 12,
                  color: "#64748b",
                  padding: "2px 8px",
                  border: "1px solid #e2e8f0",
                  borderRadius: 999,
                  background: "#f8fafc",
                }}
              >
                Source: {sourceLabel}
              </span>
            </div>

            {aiError && (
              <div style={{ padding: 12, background: "#fef2f2", borderRadius: 6, color: "#991b1b", fontSize: 13, marginBottom: 12 }}>
                {aiError}
              </div>
            )}

            {aiSvg ? (
              <div style={{ marginTop: 8, borderRadius: 8, border: "1px solid #e2e8f0", background: "#f8fafc", padding: 12 }}>
                <div style={{ marginBottom: 8, fontSize: 13, fontWeight: 600, color: "#0f172a" }}>
                  AI-generated {aiDiagramType} diagram
                </div>

                <div
                  className="uml-svg"
                  style={{
                    maxHeight: 480,
                    overflow: "auto",
                    borderRadius: 6,
                    background: "#ffffff",
                    border: "1px solid #f1f5f9",
                  }}
                  dangerouslySetInnerHTML={{ __html: aiSvg }}
                />
              </div>
            ) : !aiLoading && !aiError ? (
              <div style={{ padding: 12, background: "#f1f5f9", borderRadius: 6, color: "#64748b", fontSize: 13 }}>
                No AI UML diagram yet. Choose a type and click <strong>Generate AI UML</strong>.
              </div>
            ) : null}

            {aiPlantuml && (
              <details style={{ marginTop: 12, fontSize: 12 }}>
                <summary style={{ cursor: "pointer", color: "#3b82f6", fontWeight: 600, userSelect: "none" }}>
                  View raw PlantUML generated by AI
                </summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    marginTop: 8,
                    fontSize: 11,
                    lineHeight: 1.6,
                    background: "#f8fafc",
                    padding: 12,
                    borderRadius: 6,
                    border: "1px solid #e2e8f0",
                    color: "#334155",
                    maxHeight: 300,
                    overflow: "auto",
                  }}
                >
                  {aiPlantuml}
                </pre>
              </details>
            )}
          </>
        )}

        <style>{`
          .uml-svg svg { width: 100% !important; height: auto !important; }
        `}</style>
      </div>
    </div>
  );
}

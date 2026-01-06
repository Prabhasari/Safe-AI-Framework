import { useState } from "react";

/* ---------- Types ---------- */
type SemgrepFinding = {
  check_id?: string;
  severity?: string;
  message?: string;
  path?: string;
  start?: { line?: number; col?: number };
  end?: { line?: number; col?: number };
  metadata?: Record<string, unknown>;
};

type SemgrepReport = {
  ok?: boolean;
  exit_code?: number;
  file_count?: number;
  files?: string[];
  languages?: string[];
  packs?: string[];
  findings: SemgrepFinding[];
  errors?: Array<Record<string, unknown>>;
  error?: string;
  stats?: Record<string, unknown>;
};

// UML report type
type UmlReport = {
  ok?: boolean;
  file_count?: number;
  error?: string | null;
  class_svg?: string | null;
  package_svg?: string | null;
};

type Report = {
  policy_version?: string;
  prompt_after_enhancement?: string;
  semgrep?: SemgrepReport;
  security?: {
    injection_patterns_detected?: string[];
    injection_blocked?: boolean;
  };
  uml?: UmlReport;
};

type ApiResult = {
  code: string;
  report: Report;
  decision?: string;
};

/* ---------- Styled Bits ---------- */
const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div style={{ marginTop: 24 }}>
    <h2
      style={{
        margin: "0 0 12px 0",
        fontSize: 18,
        fontWeight: 600,
        color: "#1e293b",
      }}
    >
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
      {children}
    </div>
  </div>
);

const Badge = ({ ok }: { ok: boolean }) => (
  <span
    style={{
      display: "inline-block",
      padding: "4px 12px",
      borderRadius: 16,
      fontSize: 12,
      fontWeight: 600,
      background: ok ? "#dcfce7" : "#fee2e2",
      color: ok ? "#166534" : "#991b1b",
      border: `1px solid ${ok ? "#86efac" : "#fca5a5"}`,
    }}
  >
    {ok ? "✓ PASS" : "✗ FAIL"}
  </span>
);

const sevColor = (sev?: string) => {
  const s = (sev || "").toUpperCase();
  if (s.includes("CRITICAL") || s.includes("HIGH") || s.includes("ERROR")) return "#dc2626";
  if (s.includes("MED") || s.includes("WARN")) return "#f59e0b";
  if (s.includes("LOW") || s.includes("INFO")) return "#3b82f6";
  return "#64748b";
};

/* ---------- App ---------- */
export default function App() {
  const [prompt, setPrompt] = useState("");
  const [out, setOut] = useState<ApiResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [umlOpen, setUmlOpen] = useState(false);
  const [umlTab, setUmlTab] = useState<"class" | "package">("class"); // which diagram is active
  const API = "http://localhost:8000/api/generate";

  const onGenerate = async () => {
    setLoading(true);
    setOut(null);
    setCopied(false);
    setUmlOpen(false);
    try {
      const res = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = (await res.json()) as ApiResult;
      setOut(data);
    } catch (e) {
      console.error(e);
      alert("Request failed — is the backend running on :8000?");
    } finally {
      setLoading(false);
    }
  };

  const copyCode = async () => {
    if (!out?.code) return;
    await navigator.clipboard.writeText(out.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const uml = out?.report?.uml;

  return (
    <div
      style={{
        width: "100vw",
        minHeight: "100vh",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        padding: "40px 20px",
        overflowX: "hidden",
      }}
    >
      <main
        style={{
          width: "100%",
          maxWidth: "100%",
          margin: "0 auto",
          fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, sans-serif",
        }}
      >
        {/* Header */}
        <div
          style={{
            background: "white",
            padding: 32,
            borderRadius: 12,
            boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
            marginBottom: 24,
          }}
        >
          <h1
            style={{
              margin: "0 0 8px 0",
              fontSize: 28,
              fontWeight: 700,
              color: "#1e293b",
            }}
          >
            🔒 Secure-by-Design Code Generator
          </h1>
          <p style={{ margin: 0, color: "#64748b", fontSize: 14 }}>
            OWASP Protected • Multi-Language Support • Automatic SAST Analysis • AI-Powered Security
          </p>
        </div>

        {/* Input Card */}
        <div
          style={{
            background: "white",
            padding: 24,
            borderRadius: 12,
            boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
            marginBottom: 24,
          }}
        >
          <label
            style={{
              display: "block",
              marginBottom: 12,
              fontSize: 14,
              fontWeight: 600,
              color: "#334155",
            }}
          >
            Describe the code you want to generate (any language)
          </label>
          <textarea
            rows={5}
            style={{
              width: "100%",
              padding: 16,
              borderRadius: 8,
              border: "2px solid #e2e8f0",
              fontSize: 14,
              fontFamily: "inherit",
              resize: "vertical",
              outline: "none",
              boxSizing: "border-box",
            }}
            placeholder="e.g., Build a REST API for user authentication with JWT tokens in Python Flask, or Create a React component for a todo list with localStorage"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onFocus={(e) => (e.target.style.borderColor = "#3b82f6")}
            onBlur={(e) => (e.target.style.borderColor = "#e2e8f0")}
          />

          <div style={{ marginTop: 16, display: "flex", gap: 12, flexWrap: "wrap" }}>
            <button
              onClick={onGenerate}
              disabled={loading || !prompt.trim()}
              style={{
                flex: "1 1 220px",
                padding: "14px 24px",
                borderRadius: 8,
                border: "none",
                background: loading || !prompt.trim() ? "#cbd5e1" : "#3b82f6",
                color: "white",
                fontSize: 15,
                fontWeight: 600,
                cursor: loading || !prompt.trim() ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "🔄 Generating..." : "✨ Generate Secure Code"}
            </button>

            {out?.code && (
              <button
                onClick={copyCode}
                style={{
                  padding: "14px 24px",
                  borderRadius: 8,
                  border: "2px solid #3b82f6",
                  background: copied ? "#3b82f6" : "white",
                  color: copied ? "white" : "#3b82f6",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {copied ? "✓ Copied!" : "📋 Copy Code"}
              </button>
            )}
          </div>
        </div>

        {out && (
          <div
            style={{
              background: "white",
              padding: 24,
              borderRadius: 12,
              boxShadow: "0 4px 20px rgba(0,0,0,0.1)",
            }}
          >
            {/* Security Alerts */}
            {out.report?.security?.injection_patterns_detected &&
              out.report.security.injection_patterns_detected.length > 0 && (
                <div
                  style={{
                    marginBottom: 24,
                    padding: 16,
                    background: "#fef2f2",
                    borderRadius: 8,
                    border: "2px solid #fca5a5",
                  }}
                >
                  <div style={{ fontSize: 14, fontWeight: 600, color: "#991b1b", marginBottom: 4 }}>
                    ⚠️ Security Alert: Prompt Injection Detected
                  </div>
                  <div style={{ fontSize: 13, color: "#b91c1c" }}>
                    Blocked patterns: {out.report.security.injection_patterns_detected.join(", ")}
                  </div>
                </div>
              )}

            {/* Generated Code */}
            <Section title="📝 Generated Code">
              <pre
                style={{
                  whiteSpace: "pre-wrap",
                  margin: 0,
                  fontSize: 13,
                  lineHeight: 1.6,
                  background: "#0f172a",
                  color: "#e2e8f0",
                  padding: 20,
                  borderRadius: 6,
                  overflow: "auto",
                  maxHeight: 600,
                }}
              >
                {out.code}
              </pre>
            </Section>


            {/* UML summary + modal trigger */}
            <Section title="📊 UML Diagrams (Get a better understanding of the code)">
              {!uml || uml.error ? (
                <div
                  style={{
                    padding: 12,
                    background: "#fef2f2",
                    borderRadius: 6,
                    color: "#991b1b",
                    fontSize: 13,
                  }}
                >
                  {uml?.error
                    ? `UML generation: ${uml.error}`
                    : "No UML diagrams available for this generation (e.g. non-Java code)."}
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 16,
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ fontSize: 13, color: "#64748b" }}>
                    <div>Files analysed for UML: {uml.file_count ?? 0}</div>
                    <div>
                      Class diagram: {uml.class_svg ? "✅ available" : "—"}
                      {" · "}
                      Package diagram: {uml.package_svg ? "✅ available" : "—"}
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      if (!uml) return;
                      const defaultTab: "class" | "package" =
                        uml.class_svg ? "class" : "package";
                      setUmlTab(defaultTab);
                      setUmlOpen(true);
                    }}
                    style={{
                      padding: "10px 18px",
                      borderRadius: 8,
                      border: "none",
                      background: "#0ea5e9",
                      color: "white",
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                    }}
                  >
                    🧭 Open UML Viewer
                  </button>
                </div>
              )}
            </Section>

            {/* SAST Report */}
            <Section title="🔍 SAST Analysis (Semgrep)">
              {out.report?.semgrep?.error && (
                <div
                  style={{
                    color: "#dc2626",
                    padding: 12,
                    background: "#fef2f2",
                    borderRadius: 6,
                    fontSize: 14,
                  }}
                >
                  ⚠️ Semgrep error: {out.report.semgrep.error}
                </div>
              )}

              {out.report?.semgrep && !out.report.semgrep.error && (
                <>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 16,
                      marginBottom: 16,
                      flexWrap: "wrap",
                      padding: 12,
                      background: "#f8fafc",
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ fontSize: 13, color: "#475569" }}>
                      <strong>Packs:</strong>{" "}
                      {(out.report.semgrep.packs || []).join(", ") || "p/owasp-top-ten"}
                    </div>
                    <div style={{ fontSize: 13, color: "#475569" }}>
                      <strong>Languages:</strong>{" "}
                      {(out.report.semgrep.languages || []).join(", ") || "n/a"}
                    </div>
                    <div style={{ fontSize: 13, color: "#475569" }}>
                      <strong>Files:</strong> {out.report.semgrep.file_count ?? 0}
                    </div>
                    <Badge ok={Boolean(out.report.semgrep.findings?.length === 0)} />
                    <div style={{ fontSize: 13, color: "#64748b" }}>
                      {(out.report.semgrep.findings?.length ?? 0)} finding
                      {(out.report.semgrep.findings?.length ?? 0) === 1 ? "" : "s"}
                    </div>
                  </div>

                  {out.report.semgrep.findings && out.report.semgrep.findings.length > 0 ? (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                        <thead>
                          <tr style={{ background: "#f8fafc" }}>
                            <th
                              style={{
                                borderBottom: "2px solid #e2e8f0",
                                padding: 12,
                                textAlign: "left",
                                fontWeight: 600,
                              }}
                            >
                              Severity
                            </th>
                            <th
                              style={{
                                borderBottom: "2px solid #e2e8f0",
                                padding: 12,
                                textAlign: "left",
                                fontWeight: 600,
                              }}
                            >
                              Rule
                            </th>
                            <th
                              style={{
                                borderBottom: "2px solid #e2e8f0",
                                padding: 12,
                                textAlign: "left",
                                fontWeight: 600,
                              }}
                            >
                              Message
                            </th>
                            <th
                              style={{
                                borderBottom: "2px solid #e2e8f0",
                                padding: 12,
                                textAlign: "left",
                                fontWeight: 600,
                              }}
                            >
                              Location
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {out.report.semgrep.findings.map((f, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #f1f5f9" }}>
                              <td style={{ padding: 12, color: sevColor(f.severity), fontWeight: 600 }}>
                                {f.severity ?? "INFO"}
                              </td>
                              <td style={{ padding: 12 }}>
                                <code
                                  style={{
                                    fontSize: 11,
                                    background: "#f1f5f9",
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                  }}
                                >
                                  {f.check_id}
                                </code>
                              </td>
                              <td style={{ padding: 12, color: "#475569" }}>{f.message}</td>
                              <td style={{ padding: 12, color: "#64748b", fontSize: 12 }}>
                                {f.path}
                                {f.start?.line ? `:${f.start.line}` : ""}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div
                      style={{
                        padding: 16,
                        background: "#f0fdf4",
                        borderRadius: 6,
                        color: "#166534",
                        fontSize: 14,
                      }}
                    >
                      ✓ No security issues detected by Semgrep
                    </div>
                  )}
                </>
              )}
            </Section>

            {/* Security Report */}
            <Section title="📋 Security Report">
              <div style={{ marginBottom: 12, fontSize: 12, color: "#64748b" }}>
                Policy: {out.report.policy_version ?? "N/A"}
              </div>
              <details style={{ cursor: "pointer" }}>
                <summary
                  style={{
                    fontWeight: 600,
                    padding: "8px 0",
                    color: "#3b82f6",
                    userSelect: "none",
                  }}
                >
                  View Enhanced Prompt Details
                </summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    margin: "12px 0 0 0",
                    fontSize: 11,
                    lineHeight: 1.6,
                    background: "#f8fafc",
                    padding: 16,
                    borderRadius: 6,
                    overflow: "auto",
                    maxHeight: 400,
                    color: "#334155",
                  }}
                >
                  {out.report.prompt_after_enhancement}
                </pre>
              </details>
            </Section>
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            marginTop: 40,
            padding: 20,
            textAlign: "center",
            color: "rgba(255,255,255,0.92)",
            fontSize: 13,
          }}
        >
          Protected by OWASP LLM01 • Multi-Language Support • Powered by Gemini AI
        </div>
      </main>


      {/* UML MODAL with diagram type selector */}
      {umlOpen && uml && !uml.error && (
        <div
          onClick={() => setUmlOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15,23,42,0.55)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 16,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "100%",
              maxWidth: 1100,
              maxHeight: "90vh",
              background: "#ffffff",
              borderRadius: 12,
              boxShadow: "0 20px 50px rgba(15,23,42,0.45)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
          >
            {/* Modal header */}
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
              <div>
                <div style={{ fontWeight: 700, fontSize: 16, color: "#0f172a" }}>UML Viewer</div>
                <div style={{ fontSize: 12, color: "#64748b" }}>
                  View generated diagrams
                </div>
              </div>
              <button
                onClick={() => setUmlOpen(false)}
                style={{
                  border: "none",
                  background: "transparent",
                  cursor: "pointer",
                  fontSize: 18,
                  color: "#475569",
                  padding: 4,
                }}
                aria-label="Close UML viewer"
              >
                ✕
              </button>
            </div>

            {/* Diagram type tabs */}
            <div
              style={{
                padding: "8px 16px 4px 16px",
                borderBottom: "1px solid #e2e8f0",
                display: "flex",
                gap: 8,
              }}
            >
              <button
                onClick={() => uml.class_svg && setUmlTab("class")}
                disabled={!uml.class_svg}
                style={{
                  padding: "6px 14px",
                  borderRadius: 999,
                  border: umlTab === "class" ? "1px solid #0ea5e9" : "1px solid #cbd5e1",
                  background: umlTab === "class" ? "#e0f2fe" : "#f8fafc",
                  color: umlTab === "class" ? "#0369a1" : "#475569",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: uml.class_svg ? "pointer" : "not-allowed",
                  opacity: uml.class_svg ? 1 : 0.4,
                }}
              >
                Class Diagram
              </button>
              <button
                onClick={() => uml.package_svg && setUmlTab("package")}
                disabled={!uml.package_svg}
                style={{
                  padding: "6px 14px",
                  borderRadius: 999,
                  border: umlTab === "package" ? "1px solid #0ea5e9" : "1px solid #cbd5e1",
                  background: umlTab === "package" ? "#e0f2fe" : "#f8fafc",
                  color: umlTab === "package" ? "#0369a1" : "#475569",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: uml.package_svg ? "pointer" : "not-allowed",
                  opacity: uml.package_svg ? 1 : 0.4,
                }}
              >
                Package Diagram
              </button>
            </div>

            {/* Modal content: show only selected diagram */}
            <div
              style={{
                padding: 16,
                flex: 1,
                overflow: "auto",
                background: "#f8fafc",
              }}
            >
              {umlTab === "class" && uml.class_svg && (
                <div
                  style={{
                    background: "#ffffff",
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                    padding: 10,
                    minHeight: 300,
                  }}
                >
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#0f172a",
                      marginBottom: 6,
                    }}
                  >
                    Class Diagram
                  </div>
                  <div
                    style={{
                      overflow: "auto",
                      maxHeight: "70vh",
                      borderRadius: 6,
                      background: "#ffffff",
                    }}
                    dangerouslySetInnerHTML={{ __html: uml.class_svg }}
                  />
                </div>
              )}

              {umlTab === "package" && uml.package_svg && (
                <div
                  style={{
                    background: "#ffffff",
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                    padding: 10,
                    minHeight: 300,
                  }}
                >
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#0f172a",
                      marginBottom: 6,
                    }}
                  >
                    Package Diagram
                  </div>
                  <div
                    style={{
                      overflow: "auto",
                      maxHeight: "70vh",
                      borderRadius: 6,
                      background: "#ffffff",
                    }}
                    dangerouslySetInnerHTML={{ __html: uml.package_svg }}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <style>{`
        html, body, #root { height: 100%; width: 100%; margin: 0; padding: 0; }
        #root { max-width: none !important; padding: 0 !important; }
        * { box-sizing: border-box; }
      `}</style>
    </div>
  );
}
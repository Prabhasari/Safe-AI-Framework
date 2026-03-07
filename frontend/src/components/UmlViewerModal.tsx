import React, { useEffect, useMemo, useRef, useState } from "react";
import { X, Box, Boxes, GitBranch, Eye, Download, Activity, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
export type DiagramType = "class" | "package" | "sequence" | "component" | "activity";

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
  activity_svg?: string | null;
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

function downloadSvg(svgString: string, filename: string) {
  const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadPng(svgString: string, filename: string, containerEl: HTMLElement | null) {
  const parser  = new DOMParser();
  const svgDoc  = parser.parseFromString(svgString, "image/svg+xml");
  const svgEl   = svgDoc.documentElement as unknown as SVGSVGElement;

  let width  = 0;
  let height = 0;

  const wAttr = svgEl.getAttribute("width");
  const hAttr = svgEl.getAttribute("height");
  if (wAttr && hAttr) {
    width  = parseFloat(wAttr);
    height = parseFloat(hAttr);
  }

  if ((!width || !height) && svgEl.getAttribute("viewBox")) {
    const vb = svgEl.getAttribute("viewBox")!.split(/[\s,]+/);
    width  = parseFloat(vb[2]);
    height = parseFloat(vb[3]);
  }

  if ((!width || !height) && containerEl) {
    const rect = containerEl.getBoundingClientRect();
    width  = rect.width  || 800;
    height = rect.height || 600;
  }

  if (!width || !height) { width = 800; height = 600; }

  const scale   = 2;
  const canvas  = document.createElement("canvas");
  canvas.width  = width  * scale;
  canvas.height = height * scale;
  const ctx     = canvas.getContext("2d")!;
  ctx.scale(scale, scale);

  const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const url     = URL.createObjectURL(svgBlob);
  const img     = new Image();

  img.onload = () => {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.drawImage(img, 0, 0, width, height);
    URL.revokeObjectURL(url);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const a    = document.createElement("a");
      a.href     = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    }, "image/png");
  };

  img.onerror = () => {
    URL.revokeObjectURL(url);
    downloadSvg(svgString, filename.replace(".png", ".svg"));
  };

  img.src = url;
}

// ─── Zoomable SVG wrapper ─────────────────────────────────────────────────────
function ZoomableDiagram({
  svg,
  title,
  containerRef,
}: {
  svg: string;
  title?: string;
  containerRef?: React.RefObject<HTMLDivElement | null>;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan]   = useState({ x: 0, y: 0 });
  const dragging        = useRef(false);
  const lastPos         = useRef({ x: 0, y: 0 });
  const wrapperRef      = useRef<HTMLDivElement>(null);

  const MIN_ZOOM = 0.2;
  const MAX_ZOOM = 5;
  const STEP     = 0.2;

  const zoomIn  = () => setZoom((z) => Math.min(+(z + STEP).toFixed(2), MAX_ZOOM));
  const zoomOut = () => setZoom((z) => Math.max(+(z - STEP).toFixed(2), MIN_ZOOM));
  const reset   = () => { setZoom(1); setPan({ x: 0, y: 0 }); };

  // Wheel zoom
  const onWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? STEP : -STEP;
    setZoom((z) => Math.min(Math.max(+(z + delta).toFixed(2), MIN_ZOOM), MAX_ZOOM));
  };

  // Drag to pan
  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragging.current = true;
    lastPos.current  = { x: e.clientX, y: e.clientY };
    e.currentTarget.setAttribute("data-dragging", "true");
  };

  const onMouseMove = (e: React.MouseEvent) => {
    if (!dragging.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
  };

  const stopDrag = (e: React.MouseEvent) => {
    dragging.current = false;
    e.currentTarget.removeAttribute("data-dragging");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 8 }}>

      {/* ── Title + Zoom controls on the same row ── */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        minHeight: 36,
      }}>
        {/* Left: title */}
        {title && (
          <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>
            {title}
          </div>
        )}

        {/* Right: zoom controls */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "6px 10px",
          background: "#f8fafc",
          borderRadius: 8,
          border: "1px solid #e2e8f0",
          marginLeft: "auto",
        }}>
          <button
            onClick={zoomOut}
            disabled={zoom <= MIN_ZOOM}
            title="Zoom out"
            style={zoomBtnStyle(zoom <= MIN_ZOOM)}
          >
            <ZoomOut size={15} />
          </button>

          <span style={{ fontSize: 12, fontWeight: 700, color: "#475569", minWidth: 44, textAlign: "center" }}>
            {Math.round(zoom * 100)}%
          </span>

          <button
            onClick={zoomIn}
            disabled={zoom >= MAX_ZOOM}
            title="Zoom in"
            style={zoomBtnStyle(zoom >= MAX_ZOOM)}
          >
            <ZoomIn size={15} />
          </button>

          <div style={{ width: 1, height: 18, background: "#e2e8f0", margin: "0 2px" }} />

          <button onClick={reset} title="Reset zoom & pan" style={zoomBtnStyle(false)}>
            <RotateCcw size={14} />
          </button>
        </div>
      </div>

      {/* Pan / zoom canvas */}
      <div
        ref={wrapperRef}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
        style={{
          flex: 1,
          overflow: "hidden",
          borderRadius: 8,
          background: "#ffffff",
          border: "1px solid #f1f5f9",
          // eslint-disable-next-line react-hooks/refs
          cursor: dragging.current ? "grabbing" : "grab",
          userSelect: "none",
        }}
      >
        <div
          ref={containerRef as React.RefObject<HTMLDivElement>}
          className="uml-svg"
          style={{
            transformOrigin: "top left",
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            // eslint-disable-next-line react-hooks/refs
            transition: dragging.current ? "none" : "transform 0.05s ease",
            display: "inline-block",
            minWidth: "100%",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>

      <div style={{ fontSize: 11, color: "#94a3b8", textAlign: "center" }}>
        Scroll to zoom · drag to pan · click Reset to fit
      </div>
    </div>
  );
}

function zoomBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 28,
    height: 28,
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    background: disabled ? "#f1f5f9" : "#ffffff",
    color: disabled ? "#cbd5e1" : "#475569",
    cursor: disabled ? "not-allowed" : "pointer",
    padding: 0,
  };
}

// ─── Main UML Viewer Modal ────────────────────────────────────────────────────
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
  code: string | null;
  cir: unknown | null;
  umlAiApi: string;
  aiStore: AiUmlStore;
  setAiStore: React.Dispatch<React.SetStateAction<AiUmlStore>>;
}) {

  const [source, setSource] = useState<UmlSource>("rule");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const inflightRef = useRef<Partial<Record<DiagramType, boolean>>>({});
  const svgContainerRef = useRef<HTMLDivElement>(null);

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
        activity: uml?.activity_svg  ?? null,
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
        activity: aiStore.activity?.svg  ?? null,
      }) as Record<DiagramType, string | null>,
    [aiStore]
  );

  const hasAnyAi = useMemo(
    () => Boolean(aiSvgs.class || aiSvgs.package || aiSvgs.sequence || aiSvgs.component || aiSvgs.activity),
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

  const handleDownload = (format: "svg" | "png") => {
    if (!activeSvg) return;
    const sourcePart = effectiveSource === "ai" ? "ai" : "rule";
    const base       = `uml_${sourcePart}_${tab}`;
    if (format === "svg") {
      downloadSvg(activeSvg, `${base}.svg`);
    } else {
      downloadPng(activeSvg, `${base}.png`, svgContainerRef.current);
    }
  };

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
        {/* ── Header ── */}
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
                Scroll to zoom · drag to pan
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
                title={!canGenerateAi ? "Generate code first" : "Switch to AI"}
              >
                AI-based
              </button>
            </div>

            {/* Download button */}
            {activeSvg && (
              <DownloadMenu onDownload={handleDownload} />
            )}

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

        {/* ── Status row ── */}
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

        {/* ── Tabs ── */}
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
          <TabButton
            label="Activity Diagram"
            icon={<Activity size={16} />}
            active={tab === "activity"}
            disabled={!tabEnabled("activity")}
            onClick={() => setTab("activity")}
          />
        </div>

        {/* ── Content ── */}
        <div style={{ padding: 16, flex: 1, overflow: "hidden", background: "#f8fafc", display: "flex", flexDirection: "column" }}>
          {activeSvg ? (
            <DiagramCard
              title={`${effectiveSource === "ai" ? "AI" : "Rule"} • ${tab.toUpperCase()} Diagram`}
              svg={activeSvg}
              containerRef={svgContainerRef}
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

// ─── Download dropdown menu ───────────────────────────────────────────────────

function DownloadMenu({ onDownload }: { onDownload: (fmt: "svg" | "png") => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        title="Download diagram"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          padding: "8px 12px",
          border: "1px solid #e2e8f0",
          borderRadius: 10,
          background: open ? "#f0fdf4" : "#ffffff",
          color: open ? "#166534" : "#475569",
          fontWeight: 600,
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        <Download size={15} />
        Download
        <span style={{ fontSize: 10, marginLeft: 2 }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: 10,
            boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
            minWidth: 160,
            zIndex: 50,
            overflow: "hidden",
          }}
        >
          <button
            onClick={() => { onDownload("svg"); setOpen(false); }}
            style={menuItemStyle}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#f0f9ff")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            <span style={{ fontSize: 16 }}>🖼</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: "#0f172a" }}>SVG</div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>Vector · scales perfectly</div>
            </div>
          </button>

          <div style={{ height: 1, background: "#f1f5f9", margin: "0 10px" }} />

          <button
            onClick={() => { onDownload("png"); setOpen(false); }}
            style={menuItemStyle}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#f0f9ff")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
          >
            <span style={{ fontSize: 16 }}>📷</span>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, color: "#0f172a" }}>PNG</div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>Raster · 2× retina</div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

const menuItemStyle: React.CSSProperties = {
  width: "100%",
  display: "flex",
  alignItems: "center",
  gap: 10,
  padding: "10px 14px",
  border: "none",
  background: "transparent",
  cursor: "pointer",
  textAlign: "left",
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function TabButton({
  label, icon, active, disabled, onClick,
}: {
  label: string; icon: React.ReactNode; active: boolean; disabled: boolean; onClick: () => void;
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

function DiagramCard({
  title, svg, containerRef,
}: {
  title: string; svg: string; containerRef?: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      style={{
        flex: 1,
        background: "#ffffff",
        borderRadius: 10,
        border: "1px solid #e2e8f0",
        padding: 12,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Title and zoom controls are rendered together inside ZoomableDiagram */}
      <ZoomableDiagram svg={svg} title={title} containerRef={containerRef} />
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
/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-empty */
/* eslint-disable @typescript-eslint/no-explicit-any */
// SAFE-AI-FRAMEWORK/frontend/src/App.tsx
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import Editor from "@monaco-editor/react";
import { Routes, Route, Link, useNavigate } from "react-router-dom";
import PluginStudioPage from "./PluginStudioPage";
import { startPlugin, runPlugin, stopPlugin } from "../api/pluginClient";


const API = import.meta.env.VITE_API_URL ?? "http://localhost:8012";

/* ----------------------------- Types ------------------------------ */
type Status = {
  jar_present: boolean;
  project_present: boolean;
  running: boolean;
  pid?: number | null;
  jar_path?: string | null;
  meta?: Record<string, any> | null;
  app_url?: string | null;
};

type TreeItem = { name: string; path: string; type: "file" | "dir" };

type ContainersMap = Record<
  string,
  { id: string; name?: string; image?: string; ports?: string[]; workdir?: string }
>;

/* ----------------------------- Styled bits ------------------------ */
const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({
  children,
  style,
}) => (
  <div
    style={{
      background: "#ffffff",
      padding: 24,
      borderRadius: 12,
      border: "1px solid #e2e8f0",
      boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
      color: "#0f172a",
      ...style,
    }}
  >
    {children}
  </div>
);

const Section: React.FC<{ title: string; children: React.ReactNode; style?: React.CSSProperties }> = ({
  title,
  children,
  style,
}) => (
  <div style={{ marginTop: 24, ...style }}>
    <h2
      style={{
        margin: "0 0 12px 0",
        fontSize: 18,
        fontWeight: 700,
        color: "#1e293b",
      }}
    >
      {title}
    </h2>
    <Card>{children}</Card>
  </div>
);

const Badge = ({ text, ok }: { text: string; ok: boolean }) => (
  <span
    style={{
      display: "inline-block",
      padding: "4px 12px",
      borderRadius: 16,
      fontSize: 12,
      fontWeight: 700,
      background: ok ? "#dcfce7" : "#fee2e2",
      color: ok ? "#166534" : "#991b1b",
      border: `1px solid ${ok ? "#86efac" : "#fca5a5"}`,
    }}
  >
    {text}
  </span>
);

/* ----------------------------- Modal ------------------------------ */
const Modal: React.FC<{
  open: boolean;
  title?: string;
  onClose: () => void;
  width?: number | string;
  children: React.ReactNode;
}> = ({ open, title, onClose, width = 720, children }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(2, 6, 23, 0.55)",
        display: "grid",
        placeItems: "center",
        padding: 16,
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width,
          maxWidth: "95vw",
          maxHeight: "90vh",
          background: "#ffffff",
          borderRadius: 12,
          border: "1px solid #e2e8f0",
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <div style={{ fontWeight: 800, fontSize: 16, color: "#0f172a" }}>
            {title || "Dialog"}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              marginLeft: "auto",
              border: "none",
              background: "transparent",
              cursor: "pointer",
              fontSize: 22,
              lineHeight: 1,
              color: "#334155",
            }}
            title="Close"
          >
            ×
          </button>
        </div>
        <div style={{ padding: 16, overflow: "auto" }}>{children}</div>
      </div>
    </div>
  );
};

/* ----------------------------- Helpers ---------------------------- */
/** Parse "-p" style mappings like "3000:3000" or "127.0.0.1:3000:3000" and return the host port. */
function getHostPort(mapping: string): string | null {
  const m = (mapping || "").trim();
  const arrow = m.match(/:(\d+)->\d+\/tcp$/);
  if (arrow) return arrow[1];

  const parts = m.split(":");
  if (parts.length === 2) return parts[0].trim();
  if (parts.length === 3) return parts[1].trim();
  if (/^\d+$/.test(m)) return m;
  return null;
}

/* ----------------------------- Main Shell ------------------------- */
function Dashboard() {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);

  // Folder upload
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [folderFiles, setFolderFiles] = useState<FileList | null>(null);

  // Explorer + Editor
  const [cwd, setCwd] = useState<string>("");
  const [items, setItems] = useState<TreeItem[]>([]);
  const [openPath, setOpenPath] = useState<string>("");
  const [editorValue, setEditorValue] = useState<string>("");
  const [dirty, setDirty] = useState(false);

  // Docker controls
  const [nodeCandidates, setNodeCandidates] = useState<string[]>([]);
  const [dockerFrontSubdir, setDockerFrontSubdir] = useState<string>("");
  const [dockerBackSubdir, setDockerBackSubdir] = useState<string>("");
  const [dockerFrontPort, setDockerFrontPort] = useState<string>("3000");
  const [dockerBackPort, setDockerBackPort] = useState<string>("8088");
  const [containers, setContainers] = useState<ContainersMap>({});

  // Live URLs
  const [frontUrl, setFrontUrl] = useState<string>("");
  const [backUrl, setBackUrl] = useState<string>("");
  const [showPreview, setShowPreview] = useState<boolean>(true);

  // Plugin modal
  const [showPluginModal, setShowPluginModal] = useState(false);
  const navigate = useNavigate();

  const [selectedPlugin, setSelectedPlugin] = useState<string>("");
const [pluginBaseUrl, setPluginBaseUrl] = useState<string>("");
const [pluginResult, setPluginResult] = useState<string>("");

async function onStartPlugin() {
  if (!selectedPlugin) return alert("Select a plugin slug first");
  const res = await startPlugin({ slug: selectedPlugin, reuse: true });
  setPluginBaseUrl(res.base_url);
  alert(`Started: ${res.base_url}`);
}

// async function onRunPlugin() {
//   if (!selectedPlugin) return alert("Select a plugin slug first");
//   const res = await runPlugin({ slug: selectedPlugin, reuse: true, input: { test: true } });
//   setPluginResult(JSON.stringify(res.result, null, 2));
// }

async function onStopPlugin() {
  if (!selectedPlugin) return alert("Select a plugin slug first");
  const res = await stopPlugin({ slug: selectedPlugin });
  alert(res.stopped ? "Stopped" : "Not running");
  setPluginBaseUrl("");
}


  useEffect(() => {
    const root = document.getElementById("root");
    if (root) root.style.height = "100vh";
  }, []);

  async function refresh() {
    const { data } = await axios.get<Status>(`${API}/core/status`);
    setStatus(data);
  }
  useEffect(() => {
    refresh();
  }, []);

  // Upload folder
  async function uploadFolder() {
    if (!folderFiles || folderFiles.length === 0) {
      alert("Please choose a folder first.");
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      for (const f of Array.from(folderFiles)) {
        form.append("files", f, (f as any).webkitRelativePath || f.name);
      }
      form.append("root", "core_project");

      await axios.post(`${API}/core/upload-folder`, form, {
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      });

      if (folderInputRef.current) folderInputRef.current.value = "";
      setFolderFiles(null);

      await refresh();
      await loadTree("");
      await loadNodeCandidates();
      await dockerList();
      alert("Folder uploaded successfully!");
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? err.message ?? "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  // File explorer
  async function loadTree(dir: string) {
    const { data } = await axios.get(`${API}/core/tree`, { params: { dir } });
    setCwd(data.cwd);
    setItems(data.items);
  }
  useEffect(() => {
    if (status?.project_present) {
      loadTree("").catch(() => {});
      loadNodeCandidates().catch(() => {});
      dockerList().catch(() => {});
    } else {
      setNodeCandidates([]);
      setContainers({});
      setDockerFrontSubdir("");
      setDockerBackSubdir("");
      setFrontUrl("");
      setBackUrl("");
    }
  }, [status?.project_present]);

  async function openFile(path: string) {
    const { data } = await axios.get(`${API}/core/file`, { params: { path } });
    setOpenPath(path);
    setEditorValue(data.content);
    setDirty(false);
  }
  async function saveFile() {
    if (!openPath) return;
    await axios.post(`${API}/core/save`, editorValue, {
      params: { path: openPath },
      headers: { "Content-Type": "text/plain" },
    });
    setDirty(false);
  }

  // Node candidates → prefill docker fields
  async function loadNodeCandidates() {
    try {
      const { data } = await axios.get(`${API}/core/node-candidates`);
      const cands: string[] = data?.candidates || [];
      setNodeCandidates(cands);

      const guessFront = cands.find((c) => /front|web|ui|app/i.test(c)) || cands[0] || "";
      const guessBack = cands.find((c) => /back|api|server/i.test(c)) || cands[1] || "";
      if (!dockerFrontSubdir) setDockerFrontSubdir(guessFront || "");
      if (!dockerBackSubdir) setDockerBackSubdir(guessBack || "");
    } catch {}
  }

  function computeUrlsFromContainers(conts: ContainersMap, frontGuess: string, backGuess: string) {
    let front: string | null = null;
    let back: string | null = null;

    const tryPick = (key: string, defaults: number[]): string | null => {
      const rec = conts[key];
      if (!rec || !Array.isArray(rec.ports)) return null;
      for (const d of defaults) {
        const hit = rec.ports.find((p) => getHostPort(p) === String(d));
        if (hit) return `http://localhost:${getHostPort(hit)}`;
      }
      const first = rec.ports[0];
      if (first) {
        const host = getHostPort(first);
        return host ? `http://localhost:${host}` : null;
      }
      return null;
    };

    if (frontGuess) front = tryPick(frontGuess, [3000, 5173]);
    if (backGuess) back = tryPick(backGuess, [8088, 3001]);

    const scanAll = (prefer: number[]): string | null => {
      for (const [, rec] of Object.entries(conts)) {
        if (!rec.ports) continue;
        for (const pref of prefer) {
          const hit = rec.ports.find((p) => getHostPort(p) === String(pref));
          if (hit) return `http://localhost:${getHostPort(hit)}`;
        }
      }
      for (const [, rec] of Object.entries(conts)) {
        if (rec.ports && rec.ports[0]) {
          const host = getHostPort(rec.ports[0]);
          if (host) return `http://localhost:${host}`;
        }
      }
      return null;
    };

    if (!front) front = scanAll([3000, 5173]);
    if (!back) back = scanAll([8088, 3001]);

    setFrontUrl(front || "");
    setBackUrl(back || "");
  }

  // Docker helpers
  async function dockerStartSingleButton() {
    const apps: any[] = [];

    const looksLikeFront = (s: string) => /front|web|ui|app/i.test(s);
    const looksLikeBack = (s: string) => /back|api|server/i.test(s);

    const add = (subdir?: string, hostPortStr?: string) => {
      if (!subdir) return;

      let containerPort = 3000; // default for CRA
      if (looksLikeBack(subdir)) containerPort = 8088;
      if (looksLikeFront(subdir)) containerPort = 3000;

      const app: any = { subdir, image: "node:18-alpine" };
      const env: Record<string, string> = { HOST: "0.0.0.0", PORT: String(containerPort) };
      app.env = env;

      if (hostPortStr && /^\d+$/.test(hostPortStr)) {
        app.ports = [`${hostPortStr}:${containerPort}`]; // host:container
      } else {
        app.ports = [`${containerPort}:${containerPort}`];
      }

      apps.push(app);
    };

    add(dockerFrontSubdir, dockerFrontPort);
    add(dockerBackSubdir, dockerBackPort);

    if (!apps.length) {
      alert("No subdirs selected. Please upload a project or fill the subdir fields.");
      return;
    }

    setBusy(true);
    try {
      await axios.post(`${API}/core/docker/start-both`, { apps });
      await dockerList();
      alert("Started selected subdirs in Docker.");
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Docker start failed");
    } finally {
      setBusy(false);
    }
  }

  async function dockerList() {
    try {
      const { data } = await axios.get(`${API}/core/docker/containers`);
      const map = (data?.containers || {}) as ContainersMap;
      setContainers(map);
      computeUrlsFromContainers(map, dockerFrontSubdir, dockerBackSubdir);
    } catch {
      setContainers({});
      setFrontUrl("");
      setBackUrl("");
    }
  }

  async function dockerStop(subdir: string) {
    if (!subdir) return;
    setBusy(true);
    try {
      await axios.post(`${API}/core/docker/stop`, null, { params: { subdir } });
      await dockerList();
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Docker stop failed");
    } finally {
      setBusy(false);
    }
  }

  async function dockerStopAll() {
    if (!confirm("Stop and remove ALL containers started by this tool?")) return;
    setBusy(true);
    try {
      await axios.post(`${API}/core/docker/stop-all`);
      await dockerList();
      alert("All containers stopped.");
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Docker stop-all failed");
    } finally {
      setBusy(false);
    }
  }

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
          maxWidth: 1200,
          margin: "0 auto",
          fontFamily:
            'system-ui, -apple-system, "Segoe UI", Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
        }}
      >
        {/* Header */}
        <Card style={{ marginBottom: 24, padding: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <h1
                style={{
                  margin: "0 0 8px 0",
                  fontSize: 28,
                  fontWeight: 800,
                  color: "#1e293b",
                }}
              >
                Core System Uploader & Runner
              </h1>
              {/* <p style={{ margin: 0, color: "#64748b", fontSize: 14 }}>
                Upload your MERN project, run frontend & backend in Docker, and preview instantly.
              </p> */}
              {/* <div style={{ marginTop: 12, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <Badge text={status?.project_present ? "Project Loaded" : "No Project"} ok={!!status?.project_present} />
                <Badge text={status?.running ? "Processes Active" : "Idle"} ok={!!status?.running} />
              </div> */}
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button
                onClick={() => setShowPluginModal(true)}
                style={{
                  padding: "10px 14px",
                  borderRadius: 8,
                  border: "none",
                  background: "#3b82f6",
                  color: "white",
                  fontWeight: 800,
                  cursor: "pointer",
                }}
              >
                + Add Plugin
              </button>
              <button
                onClick={() => navigate("/secure-generator")}
                style={{
                  padding: "10px 14px",
                  borderRadius: 8,
                  border: "1px solid #e2e8f0",
                  background: "#ffffff",
                  color: "#0f172a",
                  fontWeight: 800,
                  cursor: "pointer",
                }}
              >
                Open Plugin Studio
              </button>
            </div>
          </div>
        </Card>

        {/* Upload */}
        <Section title="1) Upload project folder">
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <input
              ref={folderInputRef}
              type="file"
              multiple
              onChange={(e) => setFolderFiles(e.currentTarget.files)}
              disabled={busy}
              style={{
                padding: 10,
                border: "2px solid #e2e8f0",
                borderRadius: 8,
                background: "#fff",
              }}
            />
            <span style={{ opacity: 0.8 }}>
              {folderFiles ? `${folderFiles.length} files selected` : "no folder selected"}
            </span>
            <button
              onClick={uploadFolder}
              disabled={!folderFiles || folderFiles.length === 0 || busy}
              style={{
                padding: "12px 18px",
                borderRadius: 8,
                border: "none",
                background: !folderFiles || folderFiles.length === 0 || busy ? "#cbd5e1" : "#3b82f6",
                color: "white",
                fontWeight: 700,
                cursor: !folderFiles || folderFiles.length === 0 || busy ? "not-allowed" : "pointer",
              }}
            >
              Upload Folder
            </button>
            <button
              onClick={dockerStopAll}
              disabled={busy}
              style={{
                padding: "12px 18px",
                borderRadius: 8,
                border: "2px solid #ef4444",
                background: "white",
                color: "#ef4444",
                fontWeight: 700,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Stop ALL Containers
            </button>
          </div>
        </Section>

        {/* Run */}
        <Section title="2) Run (Docker)">
          <div style={{ marginBottom: 10, color: "#475569" }}>
            Detected subdirs are prefilled. Edit if needed, then press <b>Start</b>.
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "max-content 320px max-content 120px",
              gap: 10,
              alignItems: "center",
            }}
          >
            <label>Frontend subdir:</label>
            <input
              type="text"
              placeholder="e.g. Project/frontend"
              value={dockerFrontSubdir}
              onChange={(e) => setDockerFrontSubdir(e.target.value)}
              style={{ padding: 10, border: "2px solid #e2e8f0", borderRadius: 8, outline: "none" }}
            />
            <label>Port:</label>
            <input
              type="text"
              placeholder="3000"
              value={dockerFrontPort}
              onChange={(e) => setDockerFrontPort(e.target.value)}
              style={{ padding: 10, border: "2px solid #e2e8f0", borderRadius: 8, outline: "none" }}
            />
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "max-content 320px max-content 120px",
              gap: 10,
              alignItems: "center",
              marginTop: 10,
            }}
          >
            <label>Backend subdir:</label>
            <input
              type="text"
              placeholder="e.g. Project/backend"
              value={dockerBackSubdir}
              onChange={(e) => setDockerBackSubdir(e.target.value)}
              style={{ padding: 10, border: "2px solid #e2e8f0", borderRadius: 8, outline: "none" }}
            />
            <label>Port:</label>
            <input
              type="text"
              placeholder="8088"
              value={dockerBackPort}
              onChange={(e) => setDockerBackPort(e.target.value)}
              style={{ padding: 10, border: "2px solid #e2e8f0", borderRadius: 8, outline: "none" }}
            />
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 14, flexWrap: "wrap" }}>
            <button
              onClick={dockerStartSingleButton}
              disabled={busy || !status?.project_present}
              style={{
                padding: "12px 18px",
                borderRadius: 8,
                border: "none",
                background: busy || !status?.project_present ? "#cbd5e1" : "#10b981",
                color: "white",
                fontWeight: 800,
                cursor: busy || !status?.project_present ? "not-allowed" : "pointer",
              }}
            >
              Start
            </button>
            <button
              onClick={dockerList}
              disabled={busy}
              style={{
                padding: "12px 18px",
                borderRadius: 8,
                border: "2px solid #3b82f6",
                background: "white",
                color: "#3b82f6",
                fontWeight: 800,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              Refresh Containers
            </button>
          </div>

          {/* Live URLs */}
          <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px dashed #e2e8f0" }}>
            <div style={{ fontWeight: 700, marginBottom: 6, color: "#1e293b" }}>Live URLs</div>
            {!frontUrl && !backUrl ? (
              <div style={{ opacity: 0.7 }}>No published ports detected yet. Start the apps, then “Refresh Containers”.</div>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
                {frontUrl && (
                  <li>
                    <b>Frontend:</b>{" "}
                    <a href={frontUrl} target="_blank" rel="noreferrer">
                      {frontUrl}
                    </a>{" "}
                    <button
                      onClick={() => setShowPreview((s) => !s)}
                      style={{
                        marginLeft: 8,
                        padding: "6px 10px",
                        borderRadius: 8,
                        border: "1px solid #e2e8f0",
                        background: "#f8fafc",
                        cursor: "pointer",
                      }}
                    >
                      {showPreview ? "Hide preview" : "Show preview"}
                    </button>
                  </li>
                )}
                {backUrl && (
                  <li>
                    <b>Backend:</b>{" "}
                    <a href={backUrl} target="_blank" rel="noreferrer">
                      {backUrl}
                    </a>
                  </li>
                )}
              </ul>
            )}
          </div>

          {/* Optional inline preview (Frontend) */}
          {showPreview && frontUrl && (
            <div
              style={{
                marginTop: 10,
                height: 420,
                border: "1px solid #e2e8f0",
                borderRadius: 12,
                overflow: "hidden",
                background: "#fff",
              }}
            >
              <div style={{ padding: 8, borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 10 }}>
                <strong>Preview</strong> <span style={{ opacity: 0.7 }}>{frontUrl}</span>
              </div>
              <iframe src={frontUrl} title="app" style={{ width: "100%", height: "100%", border: "none" }} />
            </div>
          )}

          {/* Containers list */}
          <div style={{ marginTop: 16, paddingTop: 12, borderTop: "1px dashed #e2e8f0" }}>
            <div style={{ fontWeight: 700, marginBottom: 6, color: "#1e293b" }}>Active containers</div>
            {Object.keys(containers).length === 0 ? (
              <div style={{ opacity: 0.7 }}>None</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: "#f8fafc" }}>
                      <th style={{ textAlign: "left", padding: 10, borderBottom: "2px solid #e2e8f0" }}>Subdir</th>
                      <th style={{ textAlign: "left", padding: 10, borderBottom: "2px solid #e2e8f0" }}>Container</th>
                      <th style={{ textAlign: "left", padding: 10, borderBottom: "2px solid #e2e8f0" }}>Ports</th>
                      <th style={{ textAlign: "right", padding: 10, borderBottom: "2px solid #e2e8f0" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(containers).map(([subdir, rec]) => (
                      <tr key={subdir} style={{ borderBottom: "1px solid #f1f5f9" }}>
                        <td style={{ padding: 10 }}>
                          <code style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: 6, fontSize: 12 }}>
                            {subdir}
                          </code>
                        </td>
                        <td style={{ padding: 10, color: "#334155" }}>{rec.name || rec.id}</td>
                        <td style={{ padding: 10, color: "#475569" }}>
                          {Array.isArray(rec.ports) && rec.ports.length > 0 ? rec.ports.join(", ") : "—"}
                        </td>
                        <td style={{ padding: 10, textAlign: "right" }}>
                          <button
                            onClick={() => dockerStop(subdir)}
                            disabled={busy}
                            style={{
                              padding: "8px 12px",
                              borderRadius: 8,
                              border: "2px solid #ef4444",
                              background: "white",
                              color: "#ef4444",
                              fontWeight: 700,
                              cursor: busy ? "not-allowed" : "pointer",
                            }}
                          >
                            Stop
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Section>

        {/* Modal with embedded Plugin Studio (compact) */}
        <Modal
          open={showPluginModal}
          title="Add Plugin"
          onClose={() => setShowPluginModal(false)}
          width={820}
        >
          <PluginStudioPage apiBase={API} compact />
        </Modal>

        {/*plugin runner part*/}
        <Card style={{ marginTop: 16 }}>
  <h3 style={{ marginTop: 0, color: "#1e293b" }}>Plugin Runner</h3>

  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
    <input
      value={selectedPlugin}
      onChange={(e) => setSelectedPlugin(e.target.value)}
      placeholder="plugin slug e.g. about-us"
      style={{ padding: 10, border: "2px solid #e2e8f0", borderRadius: 8, minWidth: 240 }}
    />

    <button onClick={onStartPlugin} style={{ padding: "10px 14px", borderRadius: 8 }}>
      Start Plugin
    </button>

    {/* <button onClick={onRunPlugin} style={{ padding: "10px 14px", borderRadius: 8 }}>
      Run Plugin
    </button> */}

    <button onClick={onStopPlugin} style={{ padding: "10px 14px", borderRadius: 8 }}>
      Stop Plugin
    </button>
  </div>

  {pluginBaseUrl && (
    <div style={{ marginTop: 12, color: "#334155" }}>
      <b>Runner URL:</b> {pluginBaseUrl}
    </div>
  )}

  {pluginResult && (
    <pre style={{ marginTop: 12, background: "#0f172a", color: "#e2e8f0", padding: 12, borderRadius: 8 }}>
      {pluginResult}
    </pre>
  )}
</Card>


        {/* Explorer + Editor */}
        <Section title="Explorer & Editor" style={{ marginBottom: 40 }}>
          <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 12, height: "70vh" }}>
            {/* Explorer */}
            <Card style={{ overflow: "auto" }}>
              <div style={{ fontWeight: 700, marginBottom: 6, color: "#334155" }}>
                Explorer {cwd ? `: /${cwd}` : ""}
              </div>
              {(items.length > 0 || status?.project_present) ? (
                <ul style={{ listStyle: "none", paddingLeft: 0, margin: 0 }}>
                  {cwd !== "" && (
                    <li>
                      <button
                        onClick={() => loadTree(cwd.split("/").slice(0, -1).join("/"))}
                        style={{
                          background: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: 6,
                          padding: "6px 10px",
                          cursor: "pointer",
                          color: "#0f172a",
                        }}
                      >
                        ⬆️ Up
                      </button>
                    </li>
                  )}
                  {items.map((it) => (
                    <li key={it.path} style={{ margin: "4px 0", display: "flex", gap: 6, alignItems: "center" }}>
                      {it.type === "dir" ? (
                        <button
                          onClick={() => loadTree(it.path)}
                          style={{
                            background: "transparent",
                            border: "none",
                            padding: 0,
                            color: "#0ea5e9",
                            cursor: "pointer",
                          }}
                        >
                          📁 {it.name}
                        </button>
                      ) : (
                        <button
                          onClick={() => openFile(it.path)}
                          style={{
                            background: "transparent",
                            border: "none",
                            padding: 0,
                            color: "#0ea5e9",
                            cursor: "pointer",
                          }}
                        >
                          📄 {it.name}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <div style={{ opacity: 0.6 }}>Upload a project to browse files</div>
              )}
            </Card>

            {/* Editor */}
            <div style={{ border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", background: "#fff" }}>
              <div
                style={{
                  padding: 10,
                  borderBottom: "1px solid #e2e8f0",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <strong style={{ color: "#1e293b" }}>{openPath || "No file open"}</strong>
                {dirty && <span style={{ color: "#d97706", fontWeight: 700 }}>(unsaved)</span>}
                <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                  <button
                    onClick={saveFile}
                    disabled={!openPath || !dirty}
                    style={{
                      padding: "8px 12px",
                      borderRadius: 8,
                      border: "none",
                      background: !openPath || !dirty ? "#cbd5e1" : "#3b82f6",
                      color: "#0f172a",
                      fontWeight: 700,
                      cursor: !openPath || !dirty ? "not-allowed" : "pointer",
                    }}
                  >
                    Save
                  </button>
                </div>
              </div>
              <Editor
                height="100%"
                language={guessLang(openPath)}
                value={editorValue}
                onChange={(v) => {
                  setEditorValue(v ?? "");
                  setDirty(true);
                }}
                options={{ fontSize: 14, minimap: { enabled: false }, readOnly: false }}
              />
            </div>
          </div>
        </Section>
        
      </main>

      <style>{`
        html, body, #root { height: 100%; width: 100%; margin: 0; padding: 0; }
        #root { max-width: none !important; padding: 0 !important; }
        * { box-sizing: border-box; }
        a { text-decoration: none; }
        a:hover { text-decoration: underline; }
      `}</style>
    </div>
  );
}

/* ----------------------------- Routes ----------------------------- */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/plugins" element={<PluginStudioPage apiBase={API} />} />
    </Routes>
  );
}

/* ---------------------------- Helpers ----------------------------- */
function guessLang(path: string) {
  if (!path) return "plaintext";
  const ext = path.split(".").pop()?.toLowerCase();
  if (["java"].includes(ext || "")) return "java";
  if (["js", "cjs", "mjs"].includes(ext || "")) return "javascript";
  if (["ts", "tsx"].includes(ext || "")) return "typescript";
  if (["jsx"].includes(ext || "")) return "javascript";
  if (["json"].includes(ext || "")) return "json";
  if (["html", "htm"].includes(ext || "")) return "html";
  if (["css", "scss"].includes(ext || "")) return "css";
  if (["md"].includes(ext || "")) return "markdown";
  if (["xml"].includes(ext || "")) return "xml";
  return "plaintext";
}

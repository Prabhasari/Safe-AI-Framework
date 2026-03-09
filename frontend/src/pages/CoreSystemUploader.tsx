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
import { Loader2, Play, Square } from "lucide-react";
import { FaPlay, FaStop } from "react-icons/fa";


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
          background: "#1a1328",
          borderRadius: 12,
          border: "1px solid #0f0b1a",
          boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          color: "white",
        }}
      >
        <div
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid #2e1065",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <div style={{ fontWeight: 800, fontSize: 16, color: "white" }}>
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
              color: "#e2e8f0",
            }}
            title="Close"
          >
            ×
          </button>
        </div>
        <div style={{ padding: 16, overflow: "auto", background: "#1a1328" }}>{children}</div>
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
  const [cwd, setCwd] = useState("");
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
  const [coreStarting, setCoreStarting] = useState<boolean>(false);
  const readyPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // const [showPreview, setShowPreview] = useState<boolean>(false);

  // Plugin modal
  const [showPluginModal, setShowPluginModal] = useState(false);
  const navigate = useNavigate();

  const [selectedPlugin, setSelectedPlugin] = useState<string>("");
  const [runningPlugins, setRunningPlugins] = useState<
    { name: string; url: string }[]
  >([]);

  async function refreshRunningPlugins() {
    try {
      const { data } = await axios.get(`${API}/core/plugins/running`);
      const list: { name: string; url: string }[] = (data.running ?? []).map(
        (entry: { slug: string; base_url: string }) => ({
          name: entry.slug,
          url: entry.base_url,
        })
      );
      setRunningPlugins(list);
    } catch {
      // silently ignore — not critical
    }
  }
// const [pluginBaseUrl, setPluginBaseUrl] = useState<string>("");
// const [pluginResult, setPluginResult] = useState<string>("");

// async function onStartPlugin() {
//   if (!selectedPlugin) return alert("Select a plugin slug first");
//   const res = await startPlugin({ slug: selectedPlugin, reuse: true });
//   setPluginBaseUrl(res.base_url);
//   alert(`Started: ${res.base_url}`);
// }
  async function onStartPlugin() {
    if (!selectedPlugin) return alert("Select a plugin slug first");

    try {
      const res = await startPlugin({ slug: selectedPlugin, reuse: true });

      const url = res.base_url;

      setRunningPlugins((prev) => {
        // prevent duplicates
        if (prev.some((p) => p.name === selectedPlugin)) return prev;

        return [...prev, { name: selectedPlugin, url }];
      });

      setSelectedPlugin("");
      await refreshRunningPlugins();
    } catch (err: any) {
      alert(err?.message ?? "Failed to start plugin");
    }
  }
// async function onRunPlugin() {
//   if (!selectedPlugin) return alert("Select a plugin slug first");
//   const res = await runPlugin({ slug: selectedPlugin, reuse: true, input: { test: true } });
//   setPluginResult(JSON.stringify(res.result, null, 2));
// }
// async function onRunPlugin() {
//   if (!selectedPlugin) return alert("Select a plugin slug first");
//   const res = await runPlugin({ slug: selectedPlugin, reuse: true, input: { test: true } });
//   setPluginResult(JSON.stringify(res.result, null, 2));
// }

// async function onStopPlugin() {
//   if (!selectedPlugin) return alert("Select a plugin slug first");
//   const res = await stopPlugin({ slug: selectedPlugin });
//   alert(res.stopped ? "Stopped" : "Not running");
//   setPluginBaseUrl("");
// }

async function onStopPlugin(name?: string) {
  const pluginName = name || selectedPlugin;

  if (!pluginName) {
    alert("Select a plugin slug first");
    return;
  }

  try {
    await stopPlugin({ slug: pluginName });

    // Remove from running list immediately, then confirm with backend
    setRunningPlugins((prev) =>
      prev.filter((p) => p.name !== pluginName)
    );
    await refreshRunningPlugins();

    // If stopped via input, clear input
    if (!name) {
      setSelectedPlugin("");
    }
  } catch (err: any) {
    alert(err?.message ?? "Failed to stop plugin");
  }
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
    // Fire all initialization requests in parallel instead of waiting for
    // status first and then triggering tree/candidates/docker as a second
    // round-trip. Tree and candidates silently handle 404 if no project exists.
    Promise.all([
      refresh(),
      refreshRunningPlugins(),
      loadTree("").catch(() => {}),
      loadNodeCandidates().catch(() => {}),
      dockerList().catch(() => {}),
    ]);

    // Cleanup readiness polling on unmount
    return () => {
      if (readyPollRef.current) { clearInterval(readyPollRef.current); readyPollRef.current = null; }
    };
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

    // Stop any previous polling timer
    if (readyPollRef.current) { clearInterval(readyPollRef.current); readyPollRef.current = null; }

    setBusy(true);
    setCoreStarting(true);
    try {
      await axios.post(`${API}/core/docker/start-both`, { apps });
      await dockerList(); // record port mappings immediately
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Docker start failed");
      setBusy(false);
      setCoreStarting(false);
      return;
    }
    setBusy(false);

    // Start fast frontend-driven readiness polling (every 800 ms).
    // The backend /core/docker/ready endpoint is a single instant probe
    // that returns {ready: true/false} without blocking.
    const portToCheck = dockerFrontPort || "3000";
    let elapsed = 0;
    const INTERVAL = 800;
    const MAX_MS = 120_000; // give up after 2 min

    readyPollRef.current = setInterval(async () => {
      elapsed += INTERVAL;
      try {
        const { data } = await axios.get(`${API}/core/docker/ready`, {
          params: { port: portToCheck },
          timeout: 2_000,
        });
        if (data?.ready) {
          // Service is up — stop polling and refresh URLs
          if (readyPollRef.current) { clearInterval(readyPollRef.current); readyPollRef.current = null; }
          await dockerList();
          setCoreStarting(false);
        }
      } catch {
        // network glitch — just retry on next tick
      }
      if (elapsed >= MAX_MS && readyPollRef.current) {
        clearInterval(readyPollRef.current);
        readyPollRef.current = null;
        setCoreStarting(false);
      }
    }, INTERVAL);
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
    if (readyPollRef.current) { clearInterval(readyPollRef.current); readyPollRef.current = null; }
    setBusy(true);
    setCoreStarting(false);
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

  // Create folder function
  async function createNewFolder() {
    const name = prompt("Enter folder name:");
    if (!name) return;

    const fullPath = cwd ? `${cwd}/${name}` : name;

    try {
      await axios.post(`${API}/core/create-folder`, {
        path: fullPath,
      });

      await loadTree(cwd);
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Failed to create folder");
    }
  }

  // create file function
  async function createNewFile() {
    const name = prompt("Enter file name:");
    if (!name) return;

    const fullPath = cwd ? `${cwd}/${name}` : name;

    try {
      await axios.post(`${API}/core/create-file`, {
        path: fullPath,
      });

      await loadTree(cwd);
    } catch (err: any) {
      alert(err?.response?.data?.detail ?? "Failed to create file");
    }
  }

  return (
  <div
    style={{
      height: "100vh",
      width: "100vw",
      background: "#0f0b1a",
      color: "#e2e8f0",
      display: "flex",
      flexDirection: "column",
      fontFamily: "Inter, sans-serif",
    }}
  >
    {/* ================= TOP NAVBAR ================= */}
    <div
      style={{
        height: 60,
        background: "#1a1328",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        justifyContent: "space-between",
      }}
    >
      <div style={{ fontWeight: 700, fontSize: 18 }}>
        Core System Uploader & Runner
      </div>

      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>

        {/* frontend port number get part */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>

          <span style={{ fontSize: 12, opacity: 0.7 }}>
            Frontend Port:
          </span>

          <input
            type="number"
            value={dockerFrontPort}
            onChange={(e) => setDockerFrontPort(e.target.value)}
            style={{
              width: 80,
              padding: "4px 8px",
              borderRadius: 6,
              border: "1px solid #4c1d95",
              background: "#140d22",
              color: "white",
              outline: "none",
              fontSize: 13,
            }}
          />

        </div>
        {/* Start Core */}
        <button
          onClick={dockerStartSingleButton}
          style={playBtn}
        >
          <FaPlay size={20} color="white" />
        </button>

        <button
          onClick={dockerStopAll}
          title="Stop Core"
          style={stopBtn}
        >
          <FaStop size={20} color="white" />

          {/* <Square size={18} color="white" /> */}
        </button>

        {/* <button
          onClick={dockerStopAll}
          style={navBtnDanger}
        >
          Stop All Containers
        </button> */}
        {/* Core-system startup status / ready link */}
        {coreStarting && (
          <span style={{ fontSize: 12, color: "#a78bfa", padding: "0 4px" }}>
            Starting Core System…
          </span>
        )}
        {frontUrl && !coreStarting && (
          <a
            href={frontUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ ...navBtn, textDecoration: "none", background: "#166534", border: "#166534", color: "#86efac" }}
          >
            Open Core System ↗
          </a>
        )}

        <button
          onClick={() => navigate("/PluginRegistryPage")}
          style={navBtn}
        >
          Plugin Registry Page
        </button>

        <button
          onClick={() => navigate("/secure-generator")}
          style={navBtn}
        >
          Open Code Generator
        </button>

      </div>
    </div>

    {/* ================= MAIN BODY ================= */}
    <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

      {/* ===== LEFT EXPLORER ===== */}
      <div
        style={{
          width: 250,
          background: "#1a1328",
          borderRight: "1px solid #2d1f45",
          padding: 16,
          overflowY: "auto",
        }}
      >
        <div style={{ display: "flex", alignItems: "center",justifyContent: "space-between",marginBottom: 10, }}>
          <div style={{ fontSize: 12, opacity: 0.6 }}>
            EXPLORER
          </div>
          <div style={{ display: "flex", gap: 6}}>
            <button
              onClick={createNewFolder}
              style={smallBtn}
            >
              📁+
            </button>

            <button
              onClick={createNewFile}
              style={smallBtn}
            >
              📄+
            </button>
          </div>
        </div>
        {cwd !== "" && (
          <div
            onClick={() => {
              const parent = cwd.split("/").slice(0, -1).join("/");
              loadTree(parent);
            }}
            style={{
              marginBottom: 12,
              padding: "6px 8px",
              borderRadius: 6,
              background: "#1f1535",
              
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            ⬅ Back
          </div>
        )}

        {items.map((it) => (
          <div key={it.path} style={{ marginBottom: 6 }}>
            {it.type === "dir" ? (
              <div
                style={{ cursor: "pointer", color: "#ffffff" }}
                onClick={() => loadTree(it.path)}
              >
                📁 {it.name}
              </div>
            ) : (
              <div
                style={{ cursor: "pointer" }}
                onClick={() => openFile(it.path)}
              >
                📄 {it.name}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ===== CENTER EDITOR ===== */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <div
          style={{
            background: "#181022",
            padding: "8px 14px",
            borderBottom: "1px solid #2d1f45",
            display: "flex",
            justifyContent: "space-between",
          }}
        >
          <div>{openPath || "No file open"}</div>
          <button onClick={saveFile} style={navBtnOutline}>
            Save Changes
          </button>
        </div>

        <Editor
          height="100%"
          theme="vs-dark"
          language={guessLang(openPath)}
          value={editorValue}
          onChange={(v) => {
            setEditorValue(v ?? "");
            setDirty(true);
          }}
        />
      </div>

      {/* ===== RIGHT PANEL ===== */}
      <div
        style={{
          width: 300,
          background: "#1a1328",
          borderLeft: "1px solid #2d1f45",
          padding: 16,
          overflowY: "auto",
        }}
      >
        {/* Upload */}
        <div style={cardStyle}>
          <div style={{ marginBottom: 12, fontWeight: 600 }}>
            Upload Core System
          </div>

          {/* Drag & Select Folder Box */}
          <div
            onClick={() => folderInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                setFolderFiles(e.dataTransfer.files);
              }
            }}
            style={{
              border: "2px dashed #7c3aed",
              borderRadius: 14,
              padding: 30,
              textAlign: "center",
              cursor: "pointer",
              background: "#0f0b1a",
              transition: "all 0.2s ease",
            }}
          >
            <div style={{ fontSize: 36, marginBottom: 10 }}>📂</div>

            <div style={{ fontWeight: 600 }}>
              Click to select project folder
            </div>

            <div style={{ fontSize: 12, opacity: 0.6, marginTop: 6 }}>
              Entire project directory supported
            </div>
          </div>

          {/* Hidden Folder Input */}
          <input
            type="file"
            multiple
            ref={folderInputRef}
            onChange={(e) => {
              if (e.target.files && e.target.files.length > 0) {
                setFolderFiles(e.target.files);
              }
            }}
            style={{ display: "none" }}
            {...({ webkitdirectory: "true" } as any)}

          />

          {/* File Count */}
          {folderFiles && (
            <div style={{ marginTop: 10, fontSize: 12, color: "#a78bfa" }}>
              📦 {folderFiles.length} files selected
            </div>
          )}

          {/* Upload Button */}
          <button
            onClick={uploadFolder}
            disabled={!folderFiles || busy}
            style={{
              marginTop: 14,
              width: "100%",
              padding: "10px",
              borderRadius: 8,
              border: "none",
              background: "#4F0C87",
              color: "white",
              fontWeight: 600,
              cursor: !folderFiles || busy ? "not-allowed" : "pointer",
              opacity: !folderFiles || busy ? 0.5 : 1,
            }}
          >
            Upload Core System
          </button>
        </div>
        {/* add new plugin part */}
        <div style={cardStyle}>
          <button
            onClick={() => setShowPluginModal(true)}
            disabled={!status?.project_present || busy}
            style={{
              marginTop: 14,
              width: "100%",
              padding: "10px",
              borderRadius: 8,
              border: "none",
              background: "#4F0C87",
              color: "white",
              fontWeight: 600,
            }}
          >
            + Add AI Plugin
          </button>

        </div>

        {/* Plugin Runner */}
        <div style={cardStyle}>
          <div style={{ marginBottom: 10, fontWeight: 600 }}>
            Plugin Runner
          </div>

          <div style={{display: "flex", gap:10}}>

          <input
            value={selectedPlugin}
            onChange={(e) => setSelectedPlugin(e.target.value)}
            placeholder="e.g. auth-service"
            style={inputDark}
          />

          <div style={{ display: "flex", gap: 8}}>
            <button onClick={onStartPlugin} style={playBtn}>
              <FaPlay size={20} color="white" />
            </button>
            {/* <button onClick={() => onStopPlugin()} style={navBtnOutline}>
            Stop
          </button> */}
          </div>
          </div>

          {runningPlugins.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: 14, opacity: 0.6, marginBottom: 6 }}>
              Running Plugins
            </div>

            {runningPlugins.map((plugin) => (
              <div
                key={plugin.name}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "6px 8px",
                  borderRadius: 6,
                  background: "#1f1535",
                  marginBottom: 6,
                  fontSize: 12,
                }}
              >
                <div>
                  <div style={{ fontWeight: 500, fontSize: 14 }}>
                    {plugin.name}
                  </div>
                  {/* <div style={{ opacity: 0.6 }}>
                    {plugin.url}
                  </div> */}
                </div>

                <button
                  onClick={() => onStopPlugin(plugin.name)}
                  style={stopBtn}
                >
                  <FaStop size={20} color="white" />
                </button>
              </div>
            ))}
          </div>
        )}
        </div>
      </div>
    </div>

    {/* Plugin Studio Modal */}
    <Modal
      open={showPluginModal}
      title="Add AI Plugin"
      onClose={() => setShowPluginModal(false)}
      width={900}
    >
      <PluginStudioPage apiBase={API} compact />
    </Modal>

    {/* ================= BOTTOM LOGS ================= */}
    <div
      style={{
        height: 120,
        background: "#0c0a14",
        borderTop: "1px solid #2d1f45",
        padding: 12,
        fontSize: 12,
        overflowY: "auto",
      }}
    >
      <div style={{ opacity: 0.6 }}>SYSTEM LOGS</div>
    </div>

    {/* ================= FOOTER ================= */}
    <div
      style={{
        height: 28,
        background: "#1a1328",
        fontSize: 12,
        display: "flex",
        alignItems: "center",
        padding: "0 12px",
      }}
    >
      main* | UTF-8 | Docker
    </div>
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


// Css Parts
const navBtn = {
  minWidth: 38,
  minHeight: 38,
  padding: "6px 12px",
  borderRadius: 6,
  border: "#4F0C87",
  background: "#4F0C87",
  color: "white",
  cursor: "pointer",
};

const navBtnOutline = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid #4F0C87",
  background: "#4F0C87",
  color: "#ffffff",
  cursor: "pointer",
};

const navBtnDanger = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid #D30027",
  background: "#D30027",
  color: "#ffffff",
  cursor: "pointer",
};

const inputDark = {
  width: "100%",
  minHeight: 38,
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid #2d1f45",
  background: "#0f0b1a",
  color: "white",
  outline: "none",
  fontSize: 16,
  boxSizing: "border-box" as const,  // 👈 IMPORTANT
};

const cardStyle = {
  background: "#140d22",
  padding: 14,
  borderRadius: 10,
  marginBottom: 16,
};

const smallBtn = {
  padding: "4px 8px",
  fontSize: 12,
  borderRadius: 6,
  border: "none",
  background: "#2d1f45",
  color: "#c084fc",
  cursor: "pointer",
};

const playBtn = {
  minWidth: 38,
  minHeight: 38,
  padding: 8,
  borderRadius: 8,
  border: "none",
  background: "#50B848",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
};

const stopBtn ={
  minWidth: 38,
  minHeight: 38,
  padding: 8,
  borderRadius: 8,
  border: "none",
  background: "#D30027",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
};


<style>{`
  html, body, #root { height: 100%; }

  .spin {
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
`}</style>


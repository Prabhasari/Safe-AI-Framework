/* eslint-disable @typescript-eslint/no-unused-vars */
/* eslint-disable no-empty */
/* eslint-disable @typescript-eslint/no-explicit-any */
// SAFE-AI-FRAMEWORK/frontend/src/App.tsx
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import Editor from "@monaco-editor/react";

const API = "http://localhost:8000";

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

/* ----------------------------- Helpers ---------------------------- */
/** Parse "-p" style mappings like "3000:3000" or "127.0.0.1:3000:3000" and return the host port. */
function getHostPort(mapping: string): string | null {
  const arrow = mapping.match(/:(\d+)->\d+\/tcp$/);
  if (arrow) return arrow[1];

  const parts = mapping.split(":");
  if (parts.length === 2) return parts[0];     // "3000:3000"
  if (parts.length === 3) return parts[1];     // "127.0.0.1:3000:3000"
  const onlyNum = mapping.match(/^\d+$/);
  if (onlyNum) return mapping;
  return null;
}

/* ------------------------- Plugin Studio -------------------------- */
function PluginStudio() {
  const [busy, setBusy] = useState(false);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const defaultEntry = ``;
  const [entryCode, setEntryCode] = useState(defaultEntry);
  const [plugins, setPlugins] = useState<string[]>([]);

  async function refreshList() {
    try {
      const { data } = await axios.get(`${API}/core/tree`, { params: { dir: "ai_plugins" } });
      const names = (data.items || [])
        .filter((x: any) => x.type === "dir")
        .map((x: any) => x.name);
      setPlugins(names);
    } catch {
      setPlugins([]);
    }
  }
  useEffect(() => { refreshList(); }, []);

  async function savePlugin() {
    if (!slug.trim()) { alert("Please enter a plugin slug"); return; }
    setBusy(true);
    try {
      const manifest = {
        name: slug.trim(),
        title: title.trim() || slug.trim(),
        version: "1.0.0",
        runtime: "browser",
        entry: "entry.js",
        permissions: []
      };
      await axios.post(
        `${API}/core/plugin/new`,
        JSON.stringify(manifest, null, 2),
        { params: { path: `${slug}/manifest.json` }, headers: { "Content-Type": "text/plain" } }
      );

      await axios.post(
        `${API}/core/plugin/new`,
        entryCode,
        { params: { path: `${slug}/entry.js` }, headers: { "Content-Type": "text/plain" } }
      );

      await refreshList();
      alert("Plugin saved!");
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Failed to save plugin");
    } finally {
      setBusy(false);
    }
  }

  function loadExisting(name: string) {
    setSlug(name);
    setTitle(name.replace(/[-_]/g, " "));
  }

  return (
    <section style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12 }}>
      <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 12, overflow: "auto" }}>
        <h3 style={{marginTop:0}}>Plugin Studio</h3>

        <label style={{ display: "block", fontWeight: 600, marginTop: 8 }}>Plugin Slug</label>
        <input
          value={slug}
          onChange={(e)=>setSlug(e.target.value)}
          placeholder="about-us"
          style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
        />

        <label style={{ display: "block", fontWeight: 600, marginTop: 8 }}>Title</label>
        <input
          value={title}
          onChange={(e)=>setTitle(e.target.value)}
          placeholder="About Us"
          style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
        />

        <label style={{ display: "block", fontWeight: 600, marginTop: 8 }}>entry.js</label>
        <textarea
          value={entryCode}
          onChange={(e)=>setEntryCode(e.target.value)}
          spellCheck={false}
          style={{ width: "100%", height: 260, padding: 8, borderRadius: 8, border: "1px solid #ddd", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 13 }}
        />

        <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
          <button onClick={savePlugin} disabled={busy}>Save Plugin</button>
          <button onClick={refreshList} disabled={busy}>Reload List</button>
        </div>

        <div style={{ marginTop: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Existing Plugins</div>
          <ul style={{ margin: 0, paddingLeft: 16 }}>
            {plugins.map((p) => (
              <li key={p}>
                <button onClick={()=>loadExisting(p)} style={{ background: "transparent", border: "none", padding: 0, color: "#0ea5e9", cursor: "pointer" }}>
                  {p}
                </button>
              </li>
            ))}
            {plugins.length === 0 && <li style={{opacity:.6}}>None yet</li>}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ----------------------------- Main App --------------------------- */
export default function App() {
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
  const [dockerFrontPort, setDockerFrontPort] = useState<string>("3000"); // MERN default
  const [dockerBackPort, setDockerBackPort] = useState<string>("8088");   // your backend default
  const [containers, setContainers] = useState<ContainersMap>({});

  // Live URLs derived from container port mappings
  const [frontUrl, setFrontUrl] = useState<string>("");
  const [backUrl, setBackUrl]   = useState<string>("");
  const [showPreview, setShowPreview] = useState<boolean>(true);

  // Fill page height
  useEffect(() => {
    const root = document.getElementById("root");
    if (root) root.style.height = "100vh";
  }, []);

  // Enable folder picking
  useEffect(() => {
    const el = folderInputRef.current;
    if (!el) return;
    (el as any).webkitdirectory = true;
    (el as any).directory = true;
    (el as any).mozdirectory = true;
  }, []);

  async function refresh() {
    const { data } = await axios.get<Status>(`${API}/core/status`);
    setStatus(data);
  }
  useEffect(() => { refresh(); }, []);

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
        onUploadProgress: (ev) => {
          if (ev.total) {
            const pct = Math.round((ev.loaded / ev.total) * 100);
            console.log(`Uploading… ${pct}%`);
          } else {
            console.log(`Uploading… ${ev.loaded} bytes`);
          }
        },
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

      const guessFront = cands.find(c => /front|web|ui|app/i.test(c)) || cands[0] || "";
      const guessBack  = cands.find(c => /back|api|server/i.test(c)) || (cands[1] || "");
      if (!dockerFrontSubdir) setDockerFrontSubdir(guessFront || "");
      if (!dockerBackSubdir) setDockerBackSubdir(guessBack || "");
    } catch {}
  }

  /* ------------- Compute URLs from containers (published ports) -------------- */
  function computeUrlsFromContainers(conts: ContainersMap, frontGuess: string, backGuess: string) {
    let front: string | null = null;
    let back:  string | null = null;

    const tryPick = (key: string, defaults: number[]): string | null => {
      const rec = conts[key];
      if (!rec || !Array.isArray(rec.ports)) return null;
      for (const d of defaults) {
        const hit = rec.ports.find(p => getHostPort(p) === String(d));
        if (hit) return `http://localhost:${getHostPort(hit)}`;
      }
      const first = rec.ports[0];
      if (first) {
        const host = getHostPort(first);
        return host ? `http://localhost:${host}` : null;
      }
      return null;
    };

    if (frontGuess) front = tryPick(frontGuess, [3000, 5173]); // prefer 3000 for CRA
    if (backGuess)  back  = tryPick(backGuess,  [8088, 3001]); // prefer 8088 for your API

    const scanAll = (prefer: number[]): string | null => {
      for (const [, rec] of Object.entries(conts)) {
        if (!rec.ports) continue;
        for (const pref of prefer) {
          const hit = rec.ports.find(p => getHostPort(p) === String(pref));
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
    if (!back)  back  = scanAll([8088, 3001]);

    setFrontUrl(front || "");
    setBackUrl(back || "");
  }

  /* -------------------------- Docker helpers ---------------------- */
  async function dockerStartSingleButton() {
  const apps: any[] = [];

  // Heuristics to decide container ports:
  const looksLikeFront = (s: string) => /front|web|ui|app/i.test(s);
  const looksLikeBack  = (s: string) => /back|api|server/i.test(s);

  const add = (subdir?: string, hostPortStr?: string) => {
    if (!subdir) return;

    // decide internal (container) port
    let containerPort = 3000;  // default for CRA
    if (looksLikeBack(subdir)) containerPort = 8088; // your API default
    if (looksLikeFront(subdir)) containerPort = 3000;

    const app: any = { subdir, image: "node:18-alpine" };
    const env: Record<string, string> = { HOST: "0.0.0.0", PORT: String(containerPort) };
    app.env = env;

    // Map host port (from the input) to the container port
    if (hostPortStr && /^\d+$/.test(hostPortStr)) {
      app.ports = [`${hostPortStr}:${containerPort}`]; // <-- host:container
    } else {
      // if you leave blank, Docker won’t publish; UI won’t have a URL to open
      app.ports = [`${containerPort}:${containerPort}`];
    }

    apps.push(app);
  };

  add(dockerFrontSubdir, dockerFrontPort); // e.g. host 5000 -> container 3000
  add(dockerBackSubdir,  dockerBackPort);  // e.g. host 9090 -> container 8088

  if (!apps.length) {
    alert("No subdirs selected. Please upload a project or fill the subdir fields.");
    return;
  }

  setBusy(true);
  try {
    await axios.post(`${API}/core/docker/start-both`, { apps });
    await dockerList(); // recompute URLs
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

  /* ------------------------------ UI ------------------------------ */
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", fontFamily: "Inter, ui-sans-serif, system-ui", padding: 12, gap: 12 }}>
      {/* Upload */}
      <section style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <h3 style={{margin:0}}>1) Upload project folder</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            ref={folderInputRef}
            type="file"
            multiple
            onChange={(e) => setFolderFiles(e.currentTarget.files)}
            disabled={busy}
          />
          <span style={{ opacity: 0.7 }}>
            {folderFiles ? `${folderFiles.length} files selected` : "no folder selected"}
          </span>
          <button onClick={uploadFolder} disabled={!folderFiles || folderFiles.length === 0 || busy}>Upload Folder</button>
          <button onClick={dockerStopAll} disabled={busy}>Stop ALL Containers</button>
        </div>
      </section>

      {/* Run (Docker only, single Start) */}
      <section style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <h3 style={{margin:0}}>2) Run (Docker)</h3>

        <div style={{ marginTop: 6, opacity: .8 }}>
          Detected subdirs are prefilled. Edit if needed, then press <b>Start</b>.
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "max-content 320px max-content 120px", gap: 8, alignItems: "center", marginTop: 10 }}>
          <label>Frontend subdir:</label>
          <input
            type="text"
            placeholder="e.g. Project/frontend"
            value={dockerFrontSubdir}
            onChange={(e)=>setDockerFrontSubdir(e.target.value)}
          />
          <label>Port:</label>
          <input
            type="text"
            placeholder="3000"
            value={dockerFrontPort}
            onChange={(e)=>setDockerFrontPort(e.target.value)}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "max-content 320px max-content 120px", gap: 8, alignItems: "center", marginTop: 8 }}>
          <label>Backend subdir:</label>
          <input
            type="text"
            placeholder="e.g. Project/backend"
            value={dockerBackSubdir}
            onChange={(e)=>setDockerBackSubdir(e.target.value)}
          />
          <label>Port:</label>
          <input
            type="text"
            placeholder="8088"
            value={dockerBackPort}
            onChange={(e)=>setDockerBackPort(e.target.value)}
          />
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
          <button onClick={dockerStartSingleButton} disabled={busy || !status?.project_present}>Start</button>
          <button onClick={dockerList} disabled={busy}>Refresh Containers</button>
        </div>

        {/* Live URLs */}
        <div style={{ marginTop: 12, borderTop: "1px dashed #ddd", paddingTop: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Live URLs</div>
          {!frontUrl && !backUrl ? (
            <div style={{ opacity: .6 }}>No published ports detected yet. Start the apps, then “Refresh Containers”.</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6 }}>
              {frontUrl && (
                <li>
                  <b>Frontend:</b> <a href={frontUrl} target="_blank" rel="noreferrer">{frontUrl}</a>{" "}
                  <button onClick={() => setShowPreview(s => !s)} style={{ marginLeft: 8 }}>
                    {showPreview ? "Hide preview" : "Show preview"}
                  </button>
                </li>
              )}
              {backUrl && (
                <li>
                  <b>Backend:</b> <a href={backUrl} target="_blank" rel="noreferrer">{backUrl}</a>
                </li>
              )}
            </ul>
          )}
        </div>

        {/* Optional inline preview (Frontend) */}
        {showPreview && frontUrl && (
          <div style={{ marginTop: 8, height: 420, border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
            <div style={{ padding: 8, borderBottom: "1px solid #eee" }}>
              <strong>Preview</strong> <span style={{ opacity: .7 }}>{frontUrl}</span>
            </div>
            <iframe src={frontUrl} title="app" style={{ width: "100%", height: "100%", border: "none" }} />
          </div>
        )}

        {/* Containers list */}
        <div style={{ marginTop: 12, borderTop: "1px dashed #ddd", paddingTop: 8 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Active containers</div>
          {Object.keys(containers).length === 0 ? (
            <div style={{ opacity: .6 }}>None</div>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {Object.entries(containers).map(([subdir, rec]) => (
                <li key={subdir} style={{ display: "flex", gap: 8, alignItems: "center", margin: "4px 0" }}>
                  <code style={{ background:"#f5f5f5", padding:"2px 6px", borderRadius:6 }}>{subdir}</code>
                  <span style={{ opacity:.8 }}>→ {rec.name || rec.id}</span>
                  {Array.isArray(rec.ports) && rec.ports.length > 0 && (
                    <span style={{ opacity:.7 }}>(ports: {rec.ports.join(", ")})</span>
                  )}
                  <button style={{ marginLeft: "auto" }} onClick={() => dockerStop(subdir)} disabled={busy}>Stop</button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Plugin Studio (create/update) */}
      <PluginStudio />

      {/* Explorer + Editor */}
      <section style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 12, height: "70vh" }}>
        {/* Explorer */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, padding: 8, overflow: "auto" }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Explorer {cwd ? `: /${cwd}` : ""}</div>
          {(items.length > 0 || status?.project_present) ? (
            <ul style={{ listStyle: "none", paddingLeft: 0, margin: 0 }}>
              {cwd !== "" && (
                <li>
                  <button onClick={() => loadTree(cwd.split("/").slice(0, -1).join("/"))}>⬆️ Up</button>
                </li>
              )}
              {items.map((it) => (
                <li key={it.path} style={{ margin: "4px 0", display: "flex", gap: 6, alignItems: "center" }}>
                  {it.type === "dir"
                    ? <button onClick={() => loadTree(it.path)}>📁 {it.name}</button>
                    : <button onClick={() => openFile(it.path)}>📄 {it.name}</button>}
                </li>
              ))}
            </ul>
          ) : (
            <div style={{ opacity: 0.6 }}>Upload a project to browse files</div>
          )}
        </div>

        {/* Editor */}
        <div style={{ border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
          <div style={{ padding: 8, borderBottom: "1px solid #eee", display: "flex", alignItems: "center", gap: 8 }}>
            <strong>{openPath || "No file open"}</strong>
            {dirty && <span style={{ color: "#d97706" }}>(unsaved)</span>}
            <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button onClick={saveFile} disabled={!openPath || !dirty}>Save</button>
            </div>
          </div>
          <Editor
            height="100%"
            language={guessLang(openPath)}
            value={editorValue}
            onChange={(v) => { setEditorValue(v ?? ""); setDirty(true); }}
            options={{ fontSize: 14, minimap: { enabled: false }, readOnly: false }}
          />
        </div>
      </section>
    </div>
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

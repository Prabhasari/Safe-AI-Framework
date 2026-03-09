/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import axios from "axios";
import Editor from "@monaco-editor/react";
import { Trash2 } from "lucide-react";

const API_DEFAULT = import.meta.env.VITE_CORE_URL;

/* ---- small shared UI bits ---- */
const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div
    style={{
      background: "#1a1328",
      color: "white",
      border: "1px solid #2e1065",
      padding: 24,
      borderRadius: 12,
      boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
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

/**
 * PluginStudioPage
 * - Can be used as a full page (/plugins)
 * - Or embedded inside a modal in App.tsx
 */
export default function PluginStudioPage({
  apiBase = API_DEFAULT,
  compact = false, // if true, removes the outer page chrome (useful inside a modal)
}: {
  apiBase?: string;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [entryCode, setEntryCode] = useState("");
  const [plugins, setPlugins] = useState<string[]>([]);

  async function refreshList() {
    try {
      const { data } = await axios.get(`${apiBase}/core/tree`, { params: { dir: "ai_plugins" } });
      const names = (data.items || [])
        .filter((x: any) => x.type === "dir")
        .map((x: any) => x.name);
      setPlugins(names);
    } catch {
      setPlugins([]);
    }
  }

  useEffect(() => {
    refreshList();
  }, []);

  async function savePlugin() {
    if (!slug.trim()) {
      alert("Please enter a plugin slug");
      return;
    }
    setBusy(true);
    try {
      const manifest = {
        name: slug.trim(),
        title: title.trim() || slug.trim(),
        version: "1.0.0",
        runtime: "browser",
        entry: "entry.js",
        permissions: [],
      };
      await axios.post(
        `${apiBase}/core/plugin/new`,
        JSON.stringify(manifest, null, 2),
        { params: { path: `${slug}/manifest.json` }, headers: { "Content-Type": "text/plain" } }
      );

      await axios.post(
        `${apiBase}/core/plugin/new`,
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

  async function deletePlugin(name: string) {
    if (!window.confirm(`Are you sure you want to delete the plugin "${name}"? This cannot be undone.`)) {
      return;
    }
    setDeleting(name);
    try {
      await axios.delete(`${apiBase}/core/plugins/${encodeURIComponent(name)}`);
      await refreshList();
    } catch (e: any) {
      alert(e?.response?.data?.detail ?? e.message ?? "Failed to delete plugin");
    } finally {
      setDeleting(null);
    }
  }

  // function loadExisting(name: string) {
  //   setSlug(name);
  //   setTitle(name.replace(/[-_]/g, " "));
  // }

  const body = (
  <div
    style={{
      display: "flex",
      gap: 24,
      width: "100%",
      color: "white",
    }}
  >
    {/* LEFT SIDE */}
    <div style={{ flex: 2 }}>

      {/* Plugin Slug + Title */}
      <div style={{ display: "flex", gap: 30 }}>
        <div style={{ flex: 1 }}>
          <label style={{ fontWeight: 600 }}>PLUGIN SLUG</label>
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="e.g. about-us"
            style={{
              width: "100%",
              padding: 10,
              borderRadius: 6,
              border: "1px solid #2e1065",
              background: "#0f172a",
              color: "white",
              marginTop: 6,
            }}
          />
          <div style={{ fontSize: 12, opacity: 0.6 }}>
            Lowercase, no spaces, used for system identification.
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <label style={{ fontWeight: 600 }}>PLUGIN TITLE</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. About us page"
            style={{
              width: "100%",
              padding: 10,
              borderRadius: 6,
              border: "1px solid #2e1065",
              background: "#0f172a",
              color: "white",
              marginTop: 6,
            }}
          />
          <div style={{ fontSize: 12, opacity: 0.6 }}>
            The human-readable name of your plugin.
          </div>
        </div>
      </div>

      {/* Code Editor */}
      <div style={{ marginTop: 18 }}>
        <label style={{ fontWeight: 600 }}>entry.js</label>

        <Editor
          height="260px"
          language="javascript"
          theme="vs-dark"
          value={entryCode}
          onChange={(v) => setEntryCode(v || "")}
        />
      </div>

      {/* Buttons */}
      <div style={{ display: "flex", gap: 12, marginTop: 18 }}>
        <button
          onClick={savePlugin}
          disabled={busy}
          style={{
            ...navBtn,
            opacity: busy ? 0.6 : 1,
          }}
        >
          Save Plugin
        </button>

      </div>
    </div>

    {/* RIGHT SIDE */}
    <div
      style={{
        flex: 1,
        borderLeft: "1px solid #1e1b4b",
        paddingLeft: 20,
        color: "white"
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 12 }}>
        EXISTING PLUGINS
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {plugins.map((p) => (
          <div
            key={p}
            style={{
              padding: 14,
              borderRadius: 10,
              background: "#0f172a",
              border: "1px solid #1e293b",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  background: "#22c55e",
                  borderRadius: "50%",
                }}
              />
              {p}
            </div>

            <button
              onClick={() => deletePlugin(p)}
              disabled={deleting === p || busy}
              title={`Delete plugin "${p}"`}
              style={{
                background: "transparent",
                border: "1px solid #D30027",
                borderRadius: 6,
                padding: "5px 7px",
                cursor: deleting === p ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                opacity: deleting === p ? 0.5 : 1,
                color: "#D30027",
                transition: "border-color 0.15s, background 0.15s",
              }}
              onMouseEnter={(e) => {
                if (deleting !== p) {
                  (e.currentTarget as HTMLButtonElement).style.background = "#450a0a";
                  (e.currentTarget as HTMLButtonElement).style.borderColor = "#f87171";
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                (e.currentTarget as HTMLButtonElement).style.borderColor = "#D30027";
              }}
            >
              <Trash2 size={14} />
            </button>
            
          </div>
        ))}

        {plugins.length === 0 && (
          <div style={{ opacity: 0.6 }}>No plugins yet</div>
        )}
      </div>
    </div>
  </div>
);

  if (compact) {
    // When embedded in a modal, render just the form
    return body;
  }

  // Full page wrapper
  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto",  background: "#1a1328", minHeight: "100vh", }}>
      <Section title="Plugin Studio">{body}</Section>
    </div>
  );
}

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

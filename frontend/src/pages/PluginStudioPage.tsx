/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from "react";
import axios from "axios";

const API_DEFAULT = "http://localhost:8000";

/* ---- small shared UI bits ---- */
const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
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

  function loadExisting(name: string) {
    setSlug(name);
    setTitle(name.replace(/[-_]/g, " "));
  }

  const body = (
    <>
      <label style={{ display: "block", fontWeight: 600, marginTop: 8, color: "#334155" }}>Plugin Slug</label>
      <input
        value={slug}
        onChange={(e) => setSlug(e.target.value)}
        placeholder="about-us"
        style={{
          width: "100%",
          padding: 10,
          borderRadius: 8,
          border: "2px solid #e2e8f0",
          outline: "none",
        }}
        onFocus={(e) => (e.currentTarget.style.borderColor = "#3b82f6")}
        onBlur={(e) => (e.currentTarget.style.borderColor = "#e2e8f0")}
      />

      <label style={{ display: "block", fontWeight: 600, marginTop: 12, color: "#334155" }}>Title</label>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="About Us"
        style={{
          width: "100%",
          padding: 10,
          borderRadius: 8,
          border: "2px solid #e2e8f0",
          outline: "none",
        }}
        onFocus={(e) => (e.currentTarget.style.borderColor = "#3b82f6")}
        onBlur={(e) => (e.currentTarget.style.borderColor = "#e2e8f0")}
      />

      <label style={{ display: "block", fontWeight: 600, marginTop: 12, color: "#334155" }}>entry.js</label>
      <textarea
        value={entryCode}
        onChange={(e) => setEntryCode(e.target.value)}
        spellCheck={false}
        style={{
          width: "100%",
          height: 260,
          padding: 12,
          borderRadius: 8,
          border: "2px solid #e2e8f0",
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          fontSize: 13,
          outline: "none",
        }}
        onFocus={(e) => (e.currentTarget.style.borderColor = "#3b82f6")}
        onBlur={(e) => (e.currentTarget.style.borderColor = "#e2e8f0")}
      />

      <div style={{ display: "flex", gap: 12, marginTop: 14, flexWrap: "wrap" }}>
        <button
          onClick={savePlugin}
          disabled={busy}
          style={{
            padding: "12px 20px",
            borderRadius: 8,
            border: "none",
            background: busy ? "#cbd5e1" : "#3b82f6",
            color: "white",
            fontSize: 14,
            fontWeight: 700,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          Save Plugin
        </button>
        <button
          onClick={refreshList}
          disabled={busy}
          style={{
            padding: "12px 20px",
            borderRadius: 8,
            border: "2px solid #3b82f6",
            background: "white",
            color: "#3b82f6",
            fontSize: 14,
            fontWeight: 700,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          Reload List
        </button>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 6, color: "#334155" }}>Existing Plugins</div>
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {plugins.map((p) => (
            <li key={p}>
              <button
                onClick={() => loadExisting(p)}
                style={{
                  background: "transparent",
                  border: "none",
                  padding: 0,
                  color: "#0ea5e9",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
              >
                {p}
              </button>
            </li>
          ))}
          {plugins.length === 0 && <li style={{ opacity: 0.6 }}>None yet</li>}
        </ul>
      </div>
    </>
  );

  if (compact) {
    // When embedded in a modal, render just the form
    return body;
  }

  // Full page wrapper
  return (
    <div style={{ padding: 20, maxWidth: 900, margin: "0 auto" }}>
      <Section title="Plugin Studio">{body}</Section>
    </div>
  );
}

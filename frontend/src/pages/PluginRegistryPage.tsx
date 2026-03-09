// SAFE-AI-FRAMEWORK/frontend/src/PluginRegistryPage.tsx

import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8012";

type Plugin = {
  id: string;
  role: string;
  intent: string;
  trustScore: number;
  status: "active" | "restricted" | "blocked" | "revoked";
  anomalyFlag?: boolean;
  lastActive: string;
  reqRate: string;
};



export default function PluginRegistryPage() {
  const navigate = useNavigate();
  const [view, setView] = useState<"card" | "table">("card");
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [search, setSearch] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    async function fetchPlugins() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${API}/registry/plugins`);
        if (!res.ok) throw new Error(`Server responded ${res.status}`);
        const data: any[] = await res.json();
        if (cancelled) return;

        setPlugins(
          data.map((d) => ({
            id: d.id,
            role: d.role,
            intent: d.intent,
            trustScore: d.trustScore,
            status: d.status,
            anomalyFlag: d.anomalyFlag,
            lastActive: d.lastActive,
            reqRate: d.reqRate,
          }))
        );
      } catch (err: any) {
        if (!cancelled) setError(err.message ?? "Failed to load plugins");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchPlugins();
    const interval = setInterval(fetchPlugins, 5000); // auto-refresh every 5s
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const filteredPlugins = plugins.filter((p) => {
    // Search by plugin id first (case-insensitive)
    if (search && !p.id.toLowerCase().includes(search.toLowerCase())) return false;

    if (!filter) return true;
    // 'ALL PLUGINS' card should show everything when selected
    if (filter === "ALL PLUGINS") return true;
    if (filter === "ACTIVE") return p.status === "active";
    if (filter === "RESTRICTED") return p.status === "restricted";
    if (filter === "BLOCKED") return p.status === "blocked";
    if (filter === "REVOKED") return p.status === "revoked";
    return true;
  });

  return (
    <div style={page}>
      <div style={container}>
        {/* HEADER */}
        <div style={header}>
          <div>
            <div style={titleRow}>
              <h1 style={title}>Plugin Registry & Trust Monitor</h1>
            </div>
            <div style={subtitle}>
              Real-time Zero Trust Observability for Active AI Plugins
            </div>
          </div>

          <div style={rightControls}>
            <div style={searchWrapper}>
              <svg
                viewBox="0 0 24 24"
                width={16}
                height={16}
                style={searchIcon}
                aria-hidden
              >
                <path
                  fill="currentColor"
                  d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zM10 14a4 4 0 110-8 4 4 0 010 8z"
                />
              </svg>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search plugin id"
                style={searchInputWithIcon}
              />
            </div>
            <div style={viewSwitch}>
              <button
                style={view === "card" ? activeTab : tab}
                onClick={() => setView("card")}
              >
                Card View
              </button>
              <button
                style={view === "table" ? activeTab : tab}
                onClick={() => setView("table")}
              >
                Table View
              </button>
            </div>
            <button style={ navBtn } onClick={() => navigate("/")}>Core Uploader & Runner</button>
          </div>
        </div>

        {/* METRICS */}
        <div style={metricsGrid}>
          {(() => {
            const total = plugins.length;
            const avg = total
              ? (plugins.reduce((s, p) => s + p.trustScore, 0) / total).toFixed(1)
              : "0.0";
            const active = plugins.filter((p) => p.status === "active").length;
            const restricted = plugins.filter((p) => p.status === "restricted").length;
            const blocked = plugins.filter((p) => p.status === "blocked").length;
            const revoked = plugins.filter((p) => p.status === "revoked").length;

            const entries: [string, string | number][] = [
              ["ALL PLUGINS", total],
              ["AVG TRUST SCORE", avg],
              ["ACTIVE", active],
              ["RESTRICTED", restricted],
              ["BLOCKED", blocked],
              ["REVOKED", revoked],
            ];

            const colors = ["", "", "#50B848", "#f59e0b", "#D30027", "#D30027"];
            const isFilterable = (i: number) => i === 0 || (i >= 2 && i <= 5);

            return entries.map(([label, value], i) => {
              const active = filter === label;
              const clickHandler = () => {
                if (!isFilterable(i)) return;
                setFilter(active ? null : label);
              };

              return (
                <div
                  key={i}
                  onClick={clickHandler}
                  style={{
                    ...metricCard,
                    cursor: isFilterable(i) ? "pointer" : "default",
                    border: active ? "1px solid #7c3aed" : metricCard.border,
                    background: active ? "#24143a" : metricCard.background,
                  }}
                >
                  <div style={metricLabel}>{label}</div>
                  <div style={{ ...metricValue, color: colors[i] }}>{value}</div>
                </div>
              );
            });
          })()}
        </div>

        {/* LOADING / ERROR */}
        {loading && plugins.length === 0 && (
          <div style={centeredMsg}>Loading plugins…</div>
        )}
        {error && (
          <div style={{ ...centeredMsg, color: "#D30027" }}>
            ⚠ {error}
          </div>
        )}

        {/* CARD VIEW */}
        {view === "card" && (
          <div style={cardGrid}>
            {filteredPlugins.map((p) => <PluginCard key={p.id} plugin={p} />)}
          </div>
        )}

        {/* TABLE VIEW */}
        {view === "table" && (
          <div style={tableWrapper}>
            <table style={table}>
              <thead>
                <tr>
                  <th style={th}>PLUGIN ID</th>
                  <th style={th}>STATUS</th>
                  <th style={th}>TRUST SCORE</th>
                  <th style={th}>ROLE</th>
                  <th style={th}>INTENT</th>
                  <th style={th}>REQ RATE</th>
                  <th style={th}>LAST ACTIVE</th>
                </tr>
              </thead>
              <tbody>
                {filteredPlugins.map((p) => (
                  <tr key={p.id} style={tr}>
                    <td style={tdId}>{p.id}</td>

                    <td style={td}>
                      <StatusBadge status={p.status} />
                    </td>

                    <td style={td}>
                      <div style={{ minWidth: 140 }}>
                        <div style={tableTrustBg}>
                          <div
                            style={{
                              ...tableTrustFill,
                              width: `${p.trustScore}%`,
                              background:
                                p.trustScore >= 70
                                  ? "#50B848"
                                  : p.trustScore >= 40
                                  ? "#f59e0b"
                                  : "#D30027",
                            }}
                          />
                        </div>
                        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>
                          {p.trustScore}/100
                        </div>
                      </div>
                    </td>

                    <td style={td}>{p.role}</td>
                    <td style={td}>{p.intent}</td>
                    <td style={td}>{p.reqRate}</td>
                    <td style={td}>{p.lastActive}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* FOOTER STATUS BAR */}
      <div style={footer}>
        <div style={{ color: "#50B848" }}>● REGISTRY ONLINE</div>
        <div style={{ opacity: 0.6 }}>ZERO TRUST ENFORCED</div>
        <div style={{ opacity: 0.6 }}>SCAN FREQUENCY: 5s</div>
        <div style={{ color: "#a855f7" }}>v4.2.0-SECURE</div>
      </div>
    </div>
  );
}

/* ================= COMPONENTS ================= */

function PluginCard({ plugin }: { plugin: Plugin }) {
  const color =
    plugin.trustScore >= 70
      ? "#50B848"
      : plugin.trustScore >= 40
      ? "#f59e0b"
      : "#D30027";

  return (
    <div style={pluginCard}>
      <div style={cardTop}>
        <div style={pluginId}>{plugin.id}</div>
        <StatusBadge status={plugin.status} />
      </div>

      <div style={metaRow}>
        <div>
          <div style={metaLabel}>Role:</div>
          <div>{plugin.role}</div>
        </div>
        <div>
          <div style={metaLabel}>Declared Intent:</div>
          <div>{plugin.intent}</div>
        </div>
      </div>

      <div style={{ marginTop: 20 }}>
        <div style={metaLabel}>TRUST SCORE</div>
        <div style={trustBarBg}>
          <div
            style={{
              ...trustBarFill,
              width: `${plugin.trustScore}%`,
              background: color,
              boxShadow: `0 0 12px ${color}`,
            }}
          />
        </div>
        <div style={{ marginTop: 6, fontSize: 12, opacity: 0.6 }}>
          {plugin.trustScore}/100
        </div>
      </div>

      <div style={bottomRow}>
        <div />
        <div style={{ opacity: 0.6, textAlign: "right" }}>
          {plugin.reqRate} · Last active: {plugin.lastActive}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, { bg: string; color: string }> = {
    active: { bg: "#22c55e33", color: "#50B848" },
    restricted: { bg: "#f59e0b33", color: "#f59e0b" },
    revoked: { bg: "#D3002725", color: "#D30027" },
    blocked: { bg: "#D3002725", color: "#D30027" },
  };
  const s = styles[status] ?? styles.blocked;

  return (
    <div
      style={{
        padding: "4px 10px",
        borderRadius: 20,
        fontSize: 11,
        fontWeight: 600,
        background: s.bg,
        color: s.color,
      }}
    >
      {status.toUpperCase()}
    </div>
  );
}

/* ================= STYLES ================= */

const page: React.CSSProperties = {
  minHeight: "100vh",
  width: "100vw", // FULL WIDTH FIX
  background: "linear-gradient(180deg, #140d2a, #0c0818)",
  color: "white",
  fontFamily: "Inter, sans-serif",
  display: "flex",
  flexDirection: "column",
  overflowX: "hidden",
};

const container: React.CSSProperties = {
  width: "100%",
  padding: "50px 80px",
  boxSizing: "border-box",
  flex: 1,
};

const header: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  flexWrap: "wrap",
  marginBottom: 40,
};

const titleRow = {
  display: "flex",
  alignItems: "center",
  gap: 12,
};

const title = {
  margin: 0,
  fontSize: 26,
  fontWeight: 700,
};

const subtitle = {
  marginTop: 8,
  opacity: 0.6,
  fontSize: 14,
};

const viewSwitch = {
  display: "inline-flex",
  gap: 6,
  alignItems: "center",
  background: "#0f0820",
  padding: 0,
  height: 32,
  borderRadius: 8,
  border: "1px solid #1e1530",
  verticalAlign: "middle",
};

const rightControls: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
};

const tab = {
  padding: "0 14px",
  height: "100%",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: 6,
  border: "1px solid transparent",
  background: "transparent",
  color: "white",
  cursor: "pointer",
  outline: "none",
  boxShadow: "none",
  transition: "all 120ms ease",
  minWidth: 88,
};

const activeTab = {
  ...tab,
  background: "#4F0C87",
  border: "1px solid rgba(79,12,135,0.2)",
  color: "#fff",
  boxShadow: "inset 0 -2px 0 rgba(0,0,0,0.12)",
};

const searchInput: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 8,
  border: "1px solid #2d1f55",
  background: "#0f0820",
  color: "white",
  outline: "none",
  width: 500,
  marginRight: 8,
};

const searchWrapper: React.CSSProperties = {
  position: "relative",
  display: "inline-flex",
  alignItems: "center",
  marginRight: 8,
};

const searchIcon: React.CSSProperties = {
  position: "absolute",
  left: 8,
  color: "#9ca3af",
  pointerEvents: "none",
};

const searchInputWithIcon: React.CSSProperties = {
  padding: "6px 10px 6px 32px",
  borderRadius: 8,
  border: "1px solid #2d1f55",
  background: "#0f0820",
  color: "white",
  outline: "none",
  width: 220,
};

const metricsGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(6, minmax(120px, 1fr))",
  gap: 16,
  marginBottom: 30,
  alignItems: "stretch",
};

const metricCard: React.CSSProperties = {
  background: "#1a1335",
  padding: 18,
  borderRadius: 12,
  border: "1px solid #2d1f55",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  textAlign: "center",
};

const metricLabel = {
  fontSize: 11,
  opacity: 0.6,
  letterSpacing: 1,
};

const metricValue = {
  marginTop: 8,
  fontSize: 22,
  fontWeight: 700,
};

const cardGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))",
  gap: 35,
};

const pluginCard: React.CSSProperties = {
  background: "#1a1335",
  padding: 28,
  borderRadius: 24,
  border: "1px solid #2d1f55",
};

const cardTop = {
  display: "flex",
  justifyContent: "space-between",
};

const pluginId = {
  fontSize: 18,
  fontWeight: 600,
};

const metaRow = {
  display: "flex",
  justifyContent: "space-between",
  marginTop: 18,
  fontSize: 14,
  opacity: 0.8,
};

const metaLabel = {
  fontSize: 11,
  opacity: 0.5,
  marginBottom: 4,
};

const trustBarBg = {
  height: 6,
  borderRadius: 6,
  background: "#2d1f55",
  marginTop: 8,
};

const trustBarFill = {
  height: "100%",
  borderRadius: 6,
};

const bottomRow = {
  marginTop: 24,
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  fontSize: 13,
};


const footer = {
  height: 45,
  background: "#0f0b1f",
  display: "flex",
  justifyContent: "space-around",
  alignItems: "center",
  fontSize: 12,
};

const centeredMsg: React.CSSProperties = {
  textAlign: "center",
  padding: "40px 0",
  fontSize: 16,
  opacity: 0.7,
};



const tableWrapper: React.CSSProperties = {
  marginTop: 10,
  background: "#1a1335",
  borderRadius: 24,
  border: "1px solid #2d1f55",
  padding: 30,
  overflowX: "auto",
};

const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  minWidth: 900,
  textAlign: "center",
};

const th: React.CSSProperties = {
  textAlign: "center",
  padding: "14px 16px",
  fontSize: 12,
  letterSpacing: 1,
  opacity: 0.6,
};

const td: React.CSSProperties = {
  padding: "18px 16px",
  borderTop: "1px solid #2d1f55",
  fontSize: 14,
  textAlign: "center",
};

const tdId: React.CSSProperties = {
  ...td,
  fontWeight: 600,
  textAlign: "center",
};

const tr: React.CSSProperties = {
  transition: "background 0.2s ease",
};

const tableTrustBg: React.CSSProperties = {
  height: 6,
  borderRadius: 6,
  background: "#2d1f55",
};

const tableTrustFill: React.CSSProperties = {
  height: "100%",
  borderRadius: 6,
  transition: "width 0.3s ease",
};

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
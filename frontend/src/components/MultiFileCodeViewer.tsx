// frontend/src/components/MultiFileCodeViewer.tsx

import { useState, useCallback } from "react";
import {
  Copy, Check, FileCode, ChevronRight,
  FolderOpen, Plug, CheckCircle2, X, Terminal,
  Package, Code2, FileText, Layers,
} from "lucide-react";

/* ══════════════════════════════════════════════════════════════════════════
   Types
══════════════════════════════════════════════════════════════════════════ */

export type ParsedFile = {
  path:    string;
  content: string;
};

type FileIconMeta = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Icon:  React.ComponentType<any>;
  color: string;
};

export type MultiFileCodeViewerProps = {
  code:      string;
  decision?: string;
};

/* ══════════════════════════════════════════════════════════════════════════
   Language → filename mapping
   Used when the LLM returns a single fenced block with no FILE: separators.
   The fence tag (e.g. ```python) tells us what filename to use.
══════════════════════════════════════════════════════════════════════════ */

const LANG_TO_FILENAME: Record<string, string> = {
  python:     "main.py",
  py:         "main.py",
  javascript: "main.js",
  js:         "main.js",
  typescript: "main.ts",
  ts:         "main.ts",
  java:       "Main.java",
  kotlin:     "Main.kt",
  kt:         "Main.kt",
  go:         "main.go",
  golang:     "main.go",
  rust:       "main.rs",
  rs:         "main.rs",
  php:        "main.php",
  ruby:       "main.rb",
  rb:         "main.rb",
  csharp:     "Main.cs",
  cs:         "Main.cs",
  cpp:        "main.cpp",
  c:          "main.c",
  scala:      "Main.scala",
  swift:      "main.swift",
  bash:       "main.sh",
  sh:         "main.sh",
  sql:        "query.sql",
  html:       "index.html",
  css:        "styles.css",
};

/**
 * Given a fence language tag (e.g. "python", "java", "txt", ""),
 * return the best single-file fallback filename.
 *
 * Also handles the case where Gemini hits MAX_TOKENS and wraps a partial
 * response in ```txt, but the inner content still starts with its own
 * ```python fence — we scan the inner content for a nested fence tag too.
 */
function guessFallbackFilename(fenceLang: string, innerContent: string): string {
  // 1. Direct match on the outer fence tag
  const direct = LANG_TO_FILENAME[fenceLang.toLowerCase()];
  if (direct) return direct;

  // 2. If outer fence is "txt" or empty (partial generation wrapped by
  //    _ensure_single_fence), scan the inner content for a nested fence
  //    opening like ```python or ```java at the very start.
  const nestedFenceMatch = innerContent.match(/^```([a-zA-Z0-9_+\-]+)/m);
  if (nestedFenceMatch) {
    const nestedLang = nestedFenceMatch[1].toLowerCase();
    const nested     = LANG_TO_FILENAME[nestedLang];
    if (nested) return nested;
  }

  // 3. Heuristic: scan the first 30 lines of content for language signals
  const preview = innerContent.split("\n").slice(0, 30).join("\n").toLowerCase();

  if (preview.includes("def ") || preview.includes("import os") ||
      preview.includes("import sys") || preview.includes("#!/usr/bin/env python") ||
      preview.includes("from flask") || preview.includes("from django") ||
      preview.includes("print(") || preview.includes("bcrypt") && preview.includes("def ")) {
    return "main.py";
  }
  if (preview.includes("public class") || preview.includes("public static void main") ||
      preview.includes("import java.")) {
    return "Main.java";
  }
  if (preview.includes("function ") || preview.includes("const ") ||
      preview.includes("require(") || preview.includes("console.log(")) {
    return "main.js";
  }
  if (preview.includes("interface ") || preview.includes(": string") ||
      preview.includes(": number") || preview.includes("readonly ")) {
    return "main.ts";
  }
  if (preview.includes("func main()") || preview.includes("package main")) {
    return "main.go";
  }
  if (preview.includes("<?php")) {
    return "main.php";
  }
  if (preview.includes("fn main()") || preview.includes("use std::")) {
    return "main.rs";
  }
  if (preview.includes("def initialize") || preview.includes("require_relative") ||
      preview.includes("puts ") || preview.includes("end\n")) {
    return "main.rb";
  }
  if (preview.includes("using system") || preview.includes("namespace ") ||
      preview.includes("static void main")) {
    return "Main.cs";
  }

  // 4. Final fallback — unknown language
  return "main.txt";
}

/* ══════════════════════════════════════════════════════════════════════════
   Utility: parse === FILE: ... === blob
══════════════════════════════════════════════════════════════════════════ */

export function parseMultiFileBlob(blob: string): ParsedFile[] {
  if (!blob) return [];

  // Extract fence lang tag and inner content
  const fenceMatch = blob.match(/^```([a-zA-Z0-9_+\-]*)\s*\n([\s\S]*?)\n```$/m);
  const fenceLang  = fenceMatch ? (fenceMatch[1] ?? "").trim().toLowerCase() : "";
  const inner      = fenceMatch ? fenceMatch[2] : blob;

  const FILE_SEP = /^===\s*FILE:\s*(.+?)\s*===\s*$/m;
  const lines    = inner.split("\n");
  const files: ParsedFile[] = [];

  let currentPath: string | null = null;
  let buf: string[] = [];

  const flush = () => {
    if (currentPath !== null) {
      files.push({ path: currentPath, content: buf.join("\n").trim() });
    }
    buf = [];
  };

  for (const line of lines) {
    const m = FILE_SEP.exec(line);
    if (m) { flush(); currentPath = m[1].trim().replace(/\\/g, "/"); }
    else   { buf.push(line); }
  }
  flush();

  // Single-file fallback: no FILE: separators found
  if (files.length === 0 && inner.trim()) {
    // FIX: was hardcoded to "Main.java" — now detects language from fence tag
    // or inner content so Python/JS/Go etc. all get the right filename.
    const filename = guessFallbackFilename(fenceLang, inner);
    files.push({ path: filename, content: inner.trim() });
  }

  return files;
}

/* ══════════════════════════════════════════════════════════════════════════
   File icon helper
══════════════════════════════════════════════════════════════════════════ */

function fileIconMeta(path: string): FileIconMeta {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, FileIconMeta> = {
    java:       { Icon: FileCode, color: "#f97316" },
    xml:        { Icon: FileText, color: "#60a5fa" },
    yml:        { Icon: FileText, color: "#a78bfa" },
    yaml:       { Icon: FileText, color: "#a78bfa" },
    sql:        { Icon: Terminal, color: "#34d399" },
    json:       { Icon: Layers,   color: "#fbbf24" },
    py:         { Icon: FileCode, color: "#60a5fa" },
    js:         { Icon: FileCode, color: "#fbbf24" },
    ts:         { Icon: FileCode, color: "#60a5fa" },
    go:         { Icon: FileCode, color: "#34d399" },
    md:         { Icon: FileText, color: "#94a3b8" },
    properties: { Icon: FileText, color: "#e879f9" },
    gradle:     { Icon: Package,  color: "#f97316" },
    php:        { Icon: FileCode, color: "#a78bfa" },
    rb:         { Icon: FileCode, color: "#ef4444" },
    rs:         { Icon: FileCode, color: "#f97316" },
    cs:         { Icon: FileCode, color: "#60a5fa" },
    cpp:        { Icon: FileCode, color: "#f97316" },
    c:          { Icon: FileCode, color: "#60a5fa" },
    sh:         { Icon: Terminal, color: "#34d399" },
    html:       { Icon: FileCode, color: "#f97316" },
    css:        { Icon: FileCode, color: "#60a5fa" },
    swift:      { Icon: FileCode, color: "#f97316" },
    kt:         { Icon: FileCode, color: "#a78bfa" },
    scala:      { Icon: FileCode, color: "#ef4444" },
    txt:        { Icon: FileText, color: "#94a3b8" },
  };
  return map[ext] ?? { Icon: Code2, color: "#94a3b8" };
}

/* ══════════════════════════════════════════════════════════════════════════
   Folder tree builder
══════════════════════════════════════════════════════════════════════════ */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildTree(files: ParsedFile[]): Record<string, any> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const root: any = {};
  for (const f of files) {
    const parts = f.path.split("/");
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let node: any = root;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!node[parts[i]]) node[parts[i]] = { __dir: true, __children: {} };
      node = node[parts[i]].__children;
    }
    node[parts[parts.length - 1]] = { __file: true, __fullPath: f.path };
  }
  return root;
}

/* ══════════════════════════════════════════════════════════════════════════
   TreeNode component
══════════════════════════════════════════════════════════════════════════ */

function TreeNode({
  name, node, depth, selectedPath, onSelect,
}: {
  name:         string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  node:         any;
  depth:        number;
  selectedPath: string | null;
  onSelect:     (p: string) => void;
}) {
  const [open, setOpen] = useState(true);

  if (node.__file) {
    const { Icon, color } = fileIconMeta(name);
    const active          = selectedPath === node.__fullPath;
    return (
      <div
        onClick={() => onSelect(node.__fullPath)}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: `4px 10px 4px ${14 + depth * 14}px`,
          cursor: "pointer", borderRadius: 6,
          background:  active ? "rgba(139,92,246,0.18)" : "transparent",
          borderLeft:  active ? "2px solid #8b5cf6"     : "2px solid transparent",
          transition:  "background .15s",
          marginBottom: 1,
        }}
      >
        <Icon size={12} color={active ? "#c4b5fd" : color} />
        <span style={{
          fontSize: 11, color: active ? "#e2e8f0" : "#94a3b8",
          fontWeight: active ? 600 : 400,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          maxWidth: 160,
        }}>
          {name}
        </span>
      </div>
    );
  }

  if (node.__dir) {
    return (
      <div>
        <div
          onClick={() => setOpen(!open)}
          style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: `4px 10px 4px ${10 + depth * 14}px`,
            cursor: "pointer", color: "#64748b", fontSize: 11, fontWeight: 600,
          }}
        >
          <ChevronRight
            size={11}
            style={{ transform: open ? "rotate(90deg)" : "none", transition: "transform .15s" }}
          />
          <FolderOpen size={12} color="#60a5fa" />
          <span style={{ color: "#7dd3fc" }}>{name}</span>
        </div>
        {open && Object.entries(node.__children).map(([k, v]) => (
          <TreeNode
            key={k} name={k} node={v}
            depth={depth + 1} selectedPath={selectedPath} onSelect={onSelect}
          />
        ))}
      </div>
    );
  }

  // Root level
  return (
    <div>
      {Object.entries(node).map(([k, v]) => (
        <TreeNode
          key={k} name={k} node={v}
          depth={depth} selectedPath={selectedPath} onSelect={onSelect}
        />
      ))}
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Connect to Core System Modal
══════════════════════════════════════════════════════════════════════════ */

function ConnectModal({ files, onClose }: { files: ParsedFile[]; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const [step, setStep]     = useState(0);

  const allContent = files
    .map(f => `// ========== FILE: ${f.path} ==========\n${f.content}`)
    .join("\n\n");

  const handleCopyAll = async () => {
    await navigator.clipboard.writeText(allContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const steps = [
    { label: "Copy all files",      desc: "Click 'Copy All Files' to copy the complete file structure to clipboard." },
    { label: "Open core system",    desc: "Navigate to your core system project in your IDE or file explorer."       },
    { label: "Paste & place files", desc: "Create each file at its specified path and paste the contents."           },
    { label: "Verify integration",  desc: "Run your build tool and verify there are no conflicts with existing code." },
  ];

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 9999,
      background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#13111e", border: "1px solid #2d2a3d",
        borderRadius: 16, width: 520, maxHeight: "80vh",
        display: "flex", flexDirection: "column",
        boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
      }}>
        {/* Header */}
        <div style={{
          padding: "20px 24px 16px", borderBottom: "1px solid #2d2a3d",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: "linear-gradient(135deg,#7c3aed,#4f46e5)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Plug size={18} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#e2e8f0" }}>
                Connect to Core System
              </div>
              <div style={{ fontSize: 11, color: "#64748b", marginTop: 1 }}>
                {files.length} file{files.length !== 1 ? "s" : ""} ready to transfer
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 30, height: 30, borderRadius: 8, border: "1px solid #2d2a3d",
              background: "transparent", color: "#64748b", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", padding: 0,
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: "16px 24px", overflowY: "auto", flex: 1 }}>
          <div style={{
            fontSize: 11, color: "#64748b", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 12,
          }}>
            Integration Guide
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
            {steps.map((s, i) => (
              <div
                key={i}
                onClick={() => setStep(i)}
                style={{
                  display: "flex", alignItems: "flex-start", gap: 12,
                  padding: "10px 14px", borderRadius: 8, cursor: "pointer",
                  background: step === i ? "rgba(124,58,237,0.12)" : "#0f0d1a",
                  border: `1px solid ${step === i ? "rgba(124,58,237,0.4)" : "#1e1b2e"}`,
                  transition: "all .15s",
                }}
              >
                <div style={{
                  width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                  background: step >= i ? "rgba(124,58,237,0.3)" : "#1e1b2e",
                  border: `1px solid ${step >= i ? "#7c3aed" : "#2d2a3d"}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 700,
                  color: step >= i ? "#a78bfa" : "#475569",
                }}>
                  {step > i ? <CheckCircle2 size={12} color="#a78bfa" /> : i + 1}
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: step === i ? "#c4b5fd" : "#94a3b8" }}>
                    {s.label}
                  </div>
                  <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>{s.desc}</div>
                </div>
              </div>
            ))}
          </div>

          <div style={{
            fontSize: 11, color: "#64748b", fontWeight: 600,
            textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8,
          }}>
            Files to Transfer
          </div>
          <div style={{
            background: "#080611", borderRadius: 8, border: "1px solid #1e1b2e",
            maxHeight: 180, overflowY: "auto", padding: "8px 0",
          }}>
            {files.map((f, i) => {
              const { Icon, color } = fileIconMeta(f.path);
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 12px" }}>
                  <Icon size={11} color={color} />
                  <span style={{ fontSize: 10, color: "#64748b", fontFamily: "monospace", flex: 1 }}>
                    {f.path}
                  </span>
                  <span style={{ marginLeft: "auto", fontSize: 9, color: "#334155" }}>
                    {f.content.split("\n").length} lines
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Actions */}
        <div style={{ padding: "16px 24px", borderTop: "1px solid #1e1b2e", display: "flex", gap: 10 }}>
          <button
            onClick={handleCopyAll}
            style={{
              flex: 1, padding: "12px", borderRadius: 10, border: "none",
              background: copied
                ? "linear-gradient(135deg,#059669,#047857)"
                : "linear-gradient(135deg,#7c3aed,#4f46e5)",
              color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
              transition: "background .2s",
            }}
          >
            {copied ? <><Check size={16} /> Copied!</> : <><Copy size={16} /> Copy All Files</>}
          </button>
          <button
            onClick={onClose}
            style={{
              padding: "12px 18px", borderRadius: 10, border: "1px solid #2d2a3d",
              background: "transparent", color: "#94a3b8", fontSize: 13, fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   Syntax highlighter (lightweight, no deps)
══════════════════════════════════════════════════════════════════════════ */

function highlightLine(line: string, ext: string): string {
  const safe = line
    .replace(/&/g,  "&amp;")
    .replace(/</g,  "&lt;")
    .replace(/>/g,  "&gt;");

  if (["xml", "html"].includes(ext)) {
    return safe
      .replace(/(&lt;\/?)([\w:]+)/g,
        '<span style="color:#7dd3fc">$1$2</span>')
      .replace(/([\w-]+=)(&quot;.*?&quot;)/g,
        '<span style="color:#a78bfa">$1</span><span style="color:#86efac">$2</span>');
  }

  if (["java", "py", "js", "ts", "go", "php", "rb", "rs", "cs", "kt", "swift", "scala"].includes(ext)) {
    return safe
      .replace(/(\/\/.*|#.*)/g,
        '<span style="color:#475569;font-style:italic">$1</span>')
      .replace(/(&quot;.*?&quot;|&#x27;.*?&#x27;)/g,
        '<span style="color:#86efac">$1</span>')
      .replace(
        /\b(public|private|protected|class|interface|extends|implements|import|package|static|void|return|new|if|else|for|while|try|catch|final|abstract|def|fun|var|let|const|func|struct|enum|case|switch|break|continue|throws|throw|this|super|null|true|false|async|await|fn|pub|use|mod|impl|match|self|mut|ref|type|where|yield|from|with|as|in|is|not|and|or|pass|lambda|del|raise|except|finally|elif|global|nonlocal|print|echo|require|include|namespace|using)\b/g,
        '<span style="color:#c084fc;font-weight:600">$1</span>',
      )
      .replace(/\b([A-Z][A-Za-z0-9]*)\b/g,
        '<span style="color:#67e8f9">$1</span>');
  }

  return safe;
}

/* ══════════════════════════════════════════════════════════════════════════
   CodePane — renders one file with line numbers + copy button
══════════════════════════════════════════════════════════════════════════ */

function CodePane({ file }: { file: ParsedFile }) {
  const [copied, setCopied] = useState(false);
  const ext   = file.path.split(".").pop()?.toLowerCase() ?? "";
  const lines = file.content.split("\n");
  const { Icon, color } = fileIconMeta(file.path);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(file.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* File header bar */}
      <div style={{
        padding: "10px 16px", background: "#1a1130",
        borderBottom: "1px solid #2d2060",
        display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
      }}>
        <Icon size={14} color={color} />
        <span style={{ fontSize: 12, color: "#94a3b8", fontFamily: "monospace", flex: 1 }}>
          {file.path}
        </span>
        <span style={{ fontSize: 10, color: "#334155", marginRight: 8 }}>
          {lines.length} lines · {file.content.length} chars
        </span>
        <button
          onClick={handleCopy}
          style={{
            padding: "4px 10px", borderRadius: 6, border: "1px solid #3d2060",
            background: copied ? "rgba(16,185,129,0.15)" : "transparent",
            color:      copied ? "#10b981"                : "#64748b",
            fontSize: 11, fontWeight: 600, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 5, transition: "all .15s",
          }}
        >
          {copied ? <><Check size={11} /> Copied</> : <><Copy size={11} /> Copy</>}
        </button>
      </div>

      {/* Code body with line numbers */}
      <div style={{ flex: 1, overflow: "auto", background: "#110c1e" }}>
        <table style={{
          borderCollapse: "collapse", width: "100%",
          fontFamily: "'Fira Code','Cascadia Code',monospace", fontSize: 12,
        }}>
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} style={{ lineHeight: "1.7" }}>
                <td style={{
                  width: 48, textAlign: "right", paddingRight: 16, paddingLeft: 10,
                  color: "#4a3060", userSelect: "none", verticalAlign: "top",
                  borderRight: "1px solid #2d1f45", fontSize: 11,
                  position: "sticky", left: 0, background: "#110c1e",
                }}>
                  {i + 1}
                </td>
                <td style={{ paddingLeft: 16, paddingRight: 16, whiteSpace: "pre", color: "#94a3b8" }}>
                  <span dangerouslySetInnerHTML={{ __html: highlightLine(line, ext) }} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════════════════════════
   MultiFileCodeViewer — default export
══════════════════════════════════════════════════════════════════════════ */

export default function MultiFileCodeViewer({ code, decision }: MultiFileCodeViewerProps) {
  const files = parseMultiFileBlob(code);
  const [selectedPath, setSelectedPath] = useState<string | null>(files[0]?.path ?? null);
  const [connectOpen, setConnectOpen]   = useState(false);
  const [allCopied, setAllCopied]       = useState(false);

  const selectedFile = files.find(f => f.path === selectedPath);
  const tree         = buildTree(files);

  const copyAll = useCallback(async () => {
    const all = files
      .map(f => `// ===== FILE: ${f.path} =====\n${f.content}`)
      .join("\n\n");
    await navigator.clipboard.writeText(all);
    setAllCopied(true);
    setTimeout(() => setAllCopied(false), 2500);
  }, [files]);

  if (!files.length) {
    return (
      <div style={{ padding: 32, textAlign: "center", color: "#475569", fontSize: 13 }}>
        No code generated yet.
      </div>
    );
  }

  return (
    <>
      <div style={{
        background: "#150f24", borderRadius: 12,
        border: "1px solid #3d2060", overflow: "hidden",
        display: "flex", flexDirection: "column", height: 600,
      }}>
        {/* Top toolbar */}
        <div style={{
          padding: "10px 16px", background: "#1a1130",
          borderBottom: "1px solid #2d2060",
          display: "flex", alignItems: "center", gap: 8, flexShrink: 0,
        }}>
          <span style={{
            fontSize: 11, fontWeight: 600, color: "#9a7ab5",
            display: "flex", alignItems: "center", gap: 6, flex: 1,
          }}>
            <Code2 size={13} color="#c084fc" />
            {files.length} file{files.length !== 1 ? "s" : ""} generated
          </span>

          <button
            onClick={copyAll}
            style={{
              padding: "5px 12px", borderRadius: 7,
              border: "1px solid #3d2060",
              background: allCopied ? "rgba(16,185,129,0.12)" : "transparent",
              color:      allCopied ? "#10b981" : "#9a7ab5",
              fontSize: 11, fontWeight: 600, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 5, transition: "all .15s",
            }}
          >
            {allCopied ? <><Check size={11} /> Copied!</> : <><Copy size={11} /> Copy All</>}
          </button>

          <button
            onClick={() => setConnectOpen(true)}
            style={{
              padding: "6px 14px", borderRadius: 8,
              border: "1px solid #4F0C87",
              background: "rgba(79,12,135,0.3)",
              color: "#c084fc", fontSize: 11, fontWeight: 700,
              cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
              transition: "background .15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "rgba(79,12,135,0.55)")}
            onMouseLeave={e => (e.currentTarget.style.background = "rgba(79,12,135,0.3)")}
          >
            <Plug size={12} />
            Connect to Core System
          </button>
        </div>

        {/* Sidebar + code pane */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {/* File tree sidebar */}
          <div style={{
            width: 220, borderRight: "1px solid #2d2060",
            background: "#1a1130", overflowY: "auto", flexShrink: 0, paddingTop: 8,
          }}>
            <div style={{
              padding: "4px 12px 8px", fontSize: 9, color: "#6b4d8a",
              fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em",
            }}>
              Project Files
            </div>
            <TreeNode
              name="root"
              node={tree}
              depth={0}
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
            />
          </div>

          {/* Code pane */}
          <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            {selectedFile ? (
              <CodePane file={selectedFile} />
            ) : (
              <div style={{ padding: 32, textAlign: "center", color: "#334155", fontSize: 13 }}>
                Select a file from the tree
              </div>
            )}
          </div>
        </div>
      </div>

      {connectOpen && (
        <ConnectModal files={files} onClose={() => setConnectOpen(false)} />
      )}
    </>
  );
}
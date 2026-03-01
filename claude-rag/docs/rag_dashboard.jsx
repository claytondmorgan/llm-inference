import { useState, useEffect, useCallback, useRef } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, PieChart, Pie } from "recharts";

const POLL_INTERVAL = 3000;
const STATS_URL = "http://localhost:9473/stats";

// Color palette — warm terminal aesthetic
const C = {
  bg: "#0c0c0f",
  surface: "#141419",
  border: "#1e1e28",
  borderHover: "#2a2a3a",
  text: "#c8c8d4",
  textDim: "#6b6b80",
  textBright: "#eeeefc",
  accent: "#5eead4",
  accentDim: "#2dd4bf22",
  write: "#f472b6",
  writeDim: "#f472b622",
  read: "#60a5fa",
  readDim: "#60a5fa22",
  warn: "#fbbf24",
  error: "#ef4444",
  success: "#34d399",
  purple: "#a78bfa",
  purpleDim: "#a78bfa22",
};

// Simulated data generator for demo mode
function generateMockData(prevData) {
  const now = Date.now();
  const ts = new Date(now).toLocaleTimeString("en", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const baseWrite = prevData?.write?.hooks_total || 47;
  const baseRead = prevData?.read?.searches_total || 23;
  const sessionActive = Math.random() > 0.3;

  return {
    timestamp: now,
    ts_label: ts,
    system: {
      status: sessionActive ? "active" : "idle",
      session_id: sessionActive ? "a3f8c9e1" : null,
      uptime_minutes: Math.floor((now - 1708900000000) / 60000) % 999,
      db_connected: true,
      mcp_connected: true,
      enrichment_worker: true,
      queue_depth: Math.max(0, Math.floor(Math.random() * 8) - 2),
    },
    write: {
      hooks_total: baseWrite + (sessionActive ? Math.floor(Math.random() * 3) : 0),
      hooks_read: baseWrite - 12 + (sessionActive ? Math.floor(Math.random() * 2) : 0),
      hooks_bash: 8 + Math.floor(Math.random() * 2),
      hooks_grep: 4 + Math.floor(Math.random()),
      hooks_prompt: 11 + Math.floor(Math.random()),
      chunks_total: 342 + Math.floor(Math.random() * 5),
      chunks_raw: 178 + Math.floor(Math.random() * 3),
      chunks_summary: 89 + Math.floor(Math.random() * 2),
      chunks_signature: 52 + Math.floor(Math.random()),
      chunks_decision: 23,
      dedup_hits: 14 + Math.floor(Math.random() * 2),
      avg_hook_latency_ms: 45 + Math.floor(Math.random() * 30),
      avg_enrich_latency_ms: 1200 + Math.floor(Math.random() * 800),
      files_indexed: 23,
      files_total: 47,
    },
    read: {
      searches_total: baseRead + (sessionActive ? Math.floor(Math.random() * 2) : 0),
      avg_relevance: 0.72 + Math.random() * 0.15,
      avg_results_returned: 4.2 + Math.random() * 1.5,
      avg_token_budget_used_pct: 68 + Math.floor(Math.random() * 20),
      rag_first_pct: 87 + Math.floor(Math.random() * 10),
      fallback_rate_pct: 8 + Math.floor(Math.random() * 5),
      avg_search_latency_ms: 120 + Math.floor(Math.random() * 80),
    },
    benchmark: {
      has_data: true,
      rag_on_avg_tokens: 12400 + Math.floor(Math.random() * 1000),
      rag_off_avg_tokens: 24800 + Math.floor(Math.random() * 1000),
      rag_on_avg_reads: 1.8 + Math.random() * 0.5,
      rag_off_avg_reads: 5.2 + Math.random() * 0.8,
      token_savings_pct: 48 + Math.floor(Math.random() * 8),
      read_savings_pct: 62 + Math.floor(Math.random() * 10),
    },
  };
}

// ─── Components ──────────────────────────────────────────────────────────────

function StatusDot({ ok, label }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{
        width: 7, height: 7, borderRadius: "50%",
        background: ok ? C.success : C.error,
        boxShadow: ok ? `0 0 6px ${C.success}88` : `0 0 6px ${C.error}88`,
      }} />
      <span style={{ fontSize: 11, color: ok ? C.textDim : C.error, fontFamily: "monospace" }}>{label}</span>
    </div>
  );
}

function MetricCard({ label, value, unit, color, sub, small }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8,
      padding: small ? "10px 12px" : "14px 16px", flex: 1, minWidth: small ? 100 : 140,
    }}>
      <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 4, fontFamily: "monospace" }}>
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{ fontSize: small ? 22 : 28, fontWeight: 700, color: color || C.textBright, fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>
          {typeof value === "number" ? value.toLocaleString() : value}
        </span>
        {unit && <span style={{ fontSize: 11, color: C.textDim }}>{unit}</span>}
      </div>
      {sub && <div style={{ fontSize: 10, color: C.textDim, marginTop: 4, fontFamily: "monospace" }}>{sub}</div>}
    </div>
  );
}

function SectionHeader({ icon, title, color }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, marginTop: 20 }}>
      <span style={{ fontSize: 14 }}>{icon}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: color || C.textBright, letterSpacing: 0.5, textTransform: "uppercase", fontFamily: "monospace" }}>{title}</span>
      <div style={{ flex: 1, height: 1, background: C.border, marginLeft: 8 }} />
    </div>
  );
}

function MiniBar({ value, max, color, height = 6 }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div style={{ width: "100%", height, background: `${color}15`, borderRadius: height / 2, overflow: "hidden" }}>
      <div style={{
        width: `${pct}%`, height: "100%", background: color, borderRadius: height / 2,
        transition: "width 0.6s ease",
      }} />
    </div>
  );
}

function LayerBreakdown({ data }) {
  if (!data) return null;
  const layers = [
    { name: "Raw", count: data.chunks_raw || 0, color: C.textDim },
    { name: "Summary", count: data.chunks_summary || 0, color: C.accent },
    { name: "Signature", count: data.chunks_signature || 0, color: C.purple },
    { name: "Decision", count: data.chunks_decision || 0, color: C.warn },
  ];
  const total = layers.reduce((s, l) => s + l.count, 0) || 1;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 16px" }}>
      <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 10, fontFamily: "monospace" }}>
        Chunk Layers
      </div>
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 10 }}>
        {layers.map((l, i) => (
          <div key={i} style={{ width: `${(l.count / total) * 100}%`, background: l.color, minWidth: l.count > 0 ? 4 : 0 }} />
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px" }}>
        {layers.map((l, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: l.color }} />
            <span style={{ fontSize: 11, color: C.textDim, fontFamily: "monospace" }}>{l.name}</span>
            <span style={{ fontSize: 11, color: C.text, fontFamily: "monospace", fontWeight: 600 }}>{l.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BenchmarkComparison({ data }) {
  if (!data?.has_data) {
    return (
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: 20, textAlign: "center" }}>
        <div style={{ color: C.textDim, fontSize: 12, fontFamily: "monospace" }}>
          No benchmark data yet. Run:<br />
          <code style={{ color: C.accent }}>python rag_benchmark.py --run-all</code>
        </div>
      </div>
    );
  }

  const barData = [
    { metric: "Tokens", rag_off: data.rag_off_avg_tokens, rag_on: data.rag_on_avg_tokens },
  ];
  const readData = [
    { metric: "Reads", rag_off: data.rag_off_avg_reads, rag_on: data.rag_on_avg_reads },
  ];

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      <div style={{ flex: 1, minWidth: 200, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 16px" }}>
        <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 8, fontFamily: "monospace" }}>
          Avg Tokens / Task
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: C.error, fontFamily: "monospace", marginBottom: 2 }}>RAG OFF</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.error, fontFamily: "monospace" }}>{data.rag_off_avg_tokens?.toLocaleString()}</div>
            <MiniBar value={data.rag_off_avg_tokens} max={data.rag_off_avg_tokens} color={C.error} />
          </div>
          <div style={{ fontSize: 20, color: C.textDim }}>→</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: C.success, fontFamily: "monospace", marginBottom: 2 }}>RAG ON</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.success, fontFamily: "monospace" }}>{data.rag_on_avg_tokens?.toLocaleString()}</div>
            <MiniBar value={data.rag_on_avg_tokens} max={data.rag_off_avg_tokens} color={C.success} />
          </div>
        </div>
        <div style={{ textAlign: "center", marginTop: 8 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: C.accent, fontFamily: "monospace" }}>-{data.token_savings_pct}%</span>
          <span style={{ fontSize: 11, color: C.textDim, marginLeft: 6 }}>tokens saved</span>
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 200, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 16px" }}>
        <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 8, fontFamily: "monospace" }}>
          Avg File Reads / Task
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: C.error, fontFamily: "monospace", marginBottom: 2 }}>RAG OFF</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.error, fontFamily: "monospace" }}>{data.rag_off_avg_reads?.toFixed(1)}</div>
            <MiniBar value={data.rag_off_avg_reads} max={data.rag_off_avg_reads} color={C.error} />
          </div>
          <div style={{ fontSize: 20, color: C.textDim }}>→</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: C.success, fontFamily: "monospace", marginBottom: 2 }}>RAG ON</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: C.success, fontFamily: "monospace" }}>{data.rag_on_avg_reads?.toFixed(1)}</div>
            <MiniBar value={data.rag_on_avg_reads} max={data.rag_off_avg_reads} color={C.success} />
          </div>
        </div>
        <div style={{ textAlign: "center", marginTop: 8 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: C.accent, fontFamily: "monospace" }}>-{data.read_savings_pct}%</span>
          <span style={{ fontSize: 11, color: C.textDim, marginLeft: 6 }}>fewer reads</span>
        </div>
      </div>
    </div>
  );
}

// ─── Main Dashboard ──────────────────────────────────────────────────────────

export default function RAGDashboard() {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [mode, setMode] = useState("demo"); // "demo" or "live"
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchStats = useCallback(async () => {
    if (mode === "demo") {
      const newData = generateMockData(data);
      setData(newData);
      setHistory(prev => [...prev.slice(-60), {
        ts: newData.ts_label,
        write_hooks: newData.write.hooks_total,
        read_searches: newData.read.searches_total,
        queue: newData.system.queue_depth,
        latency: newData.write.avg_hook_latency_ms,
        relevance: Math.round(newData.read.avg_relevance * 100),
      }]);
      setError(null);
    } else {
      try {
        const res = await fetch(STATS_URL);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const newData = await res.json();
        setData(newData);
        setHistory(prev => [...prev.slice(-60), {
          ts: new Date().toLocaleTimeString("en", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          write_hooks: newData.write?.hooks_total || 0,
          read_searches: newData.read?.searches_total || 0,
          queue: newData.system?.queue_depth || 0,
          latency: newData.write?.avg_hook_latency_ms || 0,
          relevance: Math.round((newData.read?.avg_relevance || 0) * 100),
        }]);
        setError(null);
      } catch (e) {
        setError(`Cannot reach ${STATS_URL} — ${e.message}`);
      }
    }
  }, [mode, data]);

  useEffect(() => {
    fetchStats();
    intervalRef.current = setInterval(fetchStats, POLL_INTERVAL);
    return () => clearInterval(intervalRef.current);
  }, [mode]);

  if (!data) return <div style={{ background: C.bg, color: C.text, height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "monospace" }}>Loading...</div>;

  const sys = data.system;
  const w = data.write;
  const r = data.read;
  const bench = data.benchmark;

  return (
    <div style={{
      background: C.bg, color: C.text, minHeight: "100vh", fontFamily: "'Inter', -apple-system, sans-serif",
      padding: "16px 20px", maxWidth: 960, margin: "0 auto",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 10, height: 10, borderRadius: "50%",
            background: sys.status === "active" ? C.accent : C.textDim,
            boxShadow: sys.status === "active" ? `0 0 12px ${C.accent}66` : "none",
            animation: sys.status === "active" ? "pulse 2s ease-in-out infinite" : "none",
          }} />
          <span style={{ fontSize: 16, fontWeight: 700, color: C.textBright, fontFamily: "'JetBrains Mono', monospace", letterSpacing: -0.5 }}>
            RAG MONITOR
          </span>
          <span style={{ fontSize: 11, color: C.textDim, fontFamily: "monospace", background: C.surface, padding: "2px 8px", borderRadius: 4 }}>
            {sys.status === "active" ? `session ${sys.session_id}` : "idle"}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <StatusDot ok={sys.db_connected} label="DB" />
            <StatusDot ok={sys.mcp_connected} label="MCP" />
            <StatusDot ok={sys.enrichment_worker} label="ENRICH" />
          </div>
          <button
            onClick={() => setMode(m => m === "demo" ? "live" : "demo")}
            style={{
              background: mode === "live" ? C.accentDim : C.surface,
              border: `1px solid ${mode === "live" ? C.accent : C.border}`,
              color: mode === "live" ? C.accent : C.textDim,
              borderRadius: 4, padding: "3px 10px", fontSize: 10, cursor: "pointer",
              fontFamily: "monospace", textTransform: "uppercase", letterSpacing: 1,
            }}
          >
            {mode === "demo" ? "demo" : "live"}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ background: `${C.error}11`, border: `1px solid ${C.error}33`, borderRadius: 6, padding: "8px 12px", marginBottom: 12, fontSize: 11, color: C.error, fontFamily: "monospace" }}>
          {error}
        </div>
      )}

      {/* Write Side */}
      <SectionHeader icon="✏️" title="Write Pipeline — Ingestion" color={C.write} />
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
        <MetricCard label="Hooks Fired" value={w.hooks_total} color={C.write} sub={`Read: ${w.hooks_read} · Bash: ${w.hooks_bash} · Grep: ${w.hooks_grep} · Prompt: ${w.hooks_prompt}`} />
        <MetricCard label="Chunks" value={w.chunks_total} color={C.accent} sub={`${w.files_indexed}/${w.files_total} files indexed`} />
        <MetricCard label="Dedup Hits" value={w.dedup_hits} color={C.success} sub="redundant reads skipped" />
        <MetricCard label="Hook Latency" value={w.avg_hook_latency_ms} unit="ms" color={w.avg_hook_latency_ms < 100 ? C.success : C.warn} sub={`enrich: ${w.avg_enrich_latency_ms}ms`} />
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
        <LayerBreakdown data={w} />
        <div style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 6, fontFamily: "monospace" }}>
            Ingestion Queue
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{
              fontSize: 28, fontWeight: 700, fontFamily: "monospace",
              color: sys.queue_depth > 20 ? C.error : sys.queue_depth > 5 ? C.warn : C.success,
            }}>
              {sys.queue_depth}
            </span>
            <span style={{ fontSize: 11, color: C.textDim }}>pending</span>
          </div>
          <MiniBar value={sys.queue_depth} max={50} color={sys.queue_depth > 20 ? C.error : sys.queue_depth > 5 ? C.warn : C.success} height={8} />
          <div style={{ fontSize: 10, color: C.textDim, marginTop: 6, fontFamily: "monospace" }}>
            {sys.queue_depth === 0 ? "✓ queue empty" : sys.queue_depth > 20 ? "⚠ backlog building" : "processing normally"}
          </div>
        </div>
      </div>

      {/* Read Side */}
      <SectionHeader icon="🔍" title="Read Pipeline — Retrieval" color={C.read} />
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
        <MetricCard label="RAG Searches" value={r.searches_total} color={C.read} sub={`avg ${r.avg_results_returned?.toFixed(1)} results`} />
        <MetricCard label="Relevance" value={`${Math.round(r.avg_relevance * 100)}%`} color={r.avg_relevance > 0.7 ? C.success : C.warn} sub="avg top-3 score" />
        <MetricCard label="RAG-First" value={`${r.rag_first_pct}%`} color={r.rag_first_pct > 80 ? C.success : C.warn} sub="sessions using RAG before Read" />
        <MetricCard label="Fallback" value={`${r.fallback_rate_pct}%`} color={r.fallback_rate_pct < 15 ? C.success : C.warn} sub="fell back to direct read" />
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
        <div style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 16px" }}>
          <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 8, fontFamily: "monospace" }}>
            Token Budget Usage
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: C.read, fontFamily: "monospace" }}>{r.avg_token_budget_used_pct}%</span>
            <span style={{ fontSize: 11, color: C.textDim }}>of budget consumed</span>
          </div>
          <MiniBar value={r.avg_token_budget_used_pct} max={100} color={C.read} height={10} />
          <div style={{ fontSize: 10, color: C.textDim, marginTop: 6, fontFamily: "monospace" }}>
            Search: {r.avg_search_latency_ms}ms avg
          </div>
        </div>
        <div style={{ flex: 2, background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: "14px 8px 6px 0px" }}>
          <div style={{ fontSize: 10, color: C.textDim, textTransform: "uppercase", letterSpacing: 1.2, marginBottom: 4, fontFamily: "monospace", paddingLeft: 16 }}>
            Activity Timeline
          </div>
          <ResponsiveContainer width="100%" height={90}>
            <LineChart data={history.slice(-30)}>
              <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
              <XAxis dataKey="ts" tick={{ fontSize: 9, fill: C.textDim }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 9, fill: C.textDim }} width={28} />
              <Tooltip
                contentStyle={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 6, fontSize: 11, fontFamily: "monospace" }}
                labelStyle={{ color: C.textDim }}
              />
              <Line type="monotone" dataKey="write_hooks" stroke={C.write} dot={false} strokeWidth={2} name="Hooks" />
              <Line type="monotone" dataKey="read_searches" stroke={C.read} dot={false} strokeWidth={2} name="Searches" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Benchmark */}
      <SectionHeader icon="⚡" title="Benchmark — RAG ON vs OFF" color={C.purple} />
      <BenchmarkComparison data={bench} />

      {/* Footer */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 20, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
        <span style={{ fontSize: 10, color: C.textDim, fontFamily: "monospace" }}>
          claude-rag · polling every {POLL_INTERVAL / 1000}s · {mode} mode
        </span>
        <span style={{ fontSize: 10, color: C.textDim, fontFamily: "monospace" }}>
          {new Date().toLocaleString()}
        </span>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
      `}</style>
    </div>
  );
}

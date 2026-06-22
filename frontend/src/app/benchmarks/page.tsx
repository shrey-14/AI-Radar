"use client";
import { useState, useEffect } from "react";
import { api, Benchmark } from "@/lib/api";
import { BenchmarkCard, FilterBar, SortBar, ControlPanel, ResultMeta, EmptyState, CardSkeleton, AnimatedNumber } from "@/components/ui";

const PER_PAGE = 10;

function Paginator({ page, total, onChange }: { page: number; total: number; onChange: (p: number) => void }) {
  const pages = Math.ceil(total / PER_PAGE);
  if (pages <= 1) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 32, padding: "16px 0", borderTop: "1px solid var(--border)" }}>
      <button onClick={() => onChange(page - 1)} disabled={page === 1} className="fpill"
        style={{ opacity: page === 1 ? 0.35 : 1, cursor: page === 1 ? "not-allowed" : "pointer" }}>
        ← Prev
      </button>
      <span className="mono" style={{ fontSize: 11, color: "var(--text-mut)" }}>
        Page <span style={{ color: "var(--iris)" }}>{page}</span> of {pages}
        <span style={{ color: "var(--text-dim)", marginLeft: 12 }}>· {total} results</span>
      </span>
      <button onClick={() => onChange(page + 1)} disabled={page === pages} className="fpill"
        style={{ opacity: page === pages ? 0.35 : 1, cursor: page === pages ? "not-allowed" : "pointer" }}>
        Next →
      </button>
    </div>
  );
}

export default function BenchmarksPage() {
  const [all,    setAll]    = useState<Benchmark[]>([]);
  const [loading,setLoading]= useState(true);
  const [total,  setTotal]  = useState(0);
  const [board,  setBoard]  = useState("");
  const [sort,   setSort]   = useState("score");
  const [page,   setPage]   = useState(1);

  useEffect(() => {
    setLoading(true);
    api.benchmarks("limit=100&sort_by=fetched_at")
      .then((r) => { setAll(r.data); setTotal(r.pagination.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setPage(1); }, [board, sort]);

  let rows = all.filter((b) => !board || b.source === board);
  rows = [...rows].sort((a, b) => {
    if (sort === "speed") return (b.speed_tps ?? 0) - (a.speed_tps ?? 0);
    if (sort === "cost")  return (a.input_cost_per_1m ?? 999) - (b.input_cost_per_1m ?? 999);
    const av = a.average_score ?? a.elo_score ?? a.intelligence_score ?? 0;
    const bv = b.average_score ?? b.elo_score ?? b.intelligence_score ?? 0;
    return bv - av;
  });

  const totalFiltered = rows.length;
  const slice = rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  return (
    <div className="shell" style={{ paddingTop: 40, paddingBottom: 80 }}>
      <div style={{ marginBottom: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--amber)", fontWeight: 600, letterSpacing: "0.1em" }}>§04</span>
          <span className="eyebrow">Open LLM Leaderboard · LMSYS Arena · Artificial Analysis</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, borderBottom: "1px solid var(--border)", paddingBottom: 20 }}>
          <h1 className="serif" style={{ fontSize: "clamp(40px,7vw,72px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 0.95, color: "var(--text)" }}>Benchmarks</h1>
          <div style={{ textAlign: "right" }}>
            <div className="mono" style={{ fontSize: 30, fontWeight: 700, color: "var(--amber)" }}><AnimatedNumber value={total} /></div>
            <div className="kicker">records indexed</div>
          </div>
        </div>
      </div>

      <ControlPanel>
        <FilterBar label="Board" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={board} onChange={setBoard} filters={[
          { label: "All", value: "" }, { label: "Open LLM", value: "open_llm_leaderboard" },
          { label: "LMSYS Arena", value: "lmsys_arena" }, { label: "Artificial Analysis", value: "artificial_analysis" },
        ]} />
        <SortBar value={sort} onChange={setSort} labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} options={[
          { label: "Score", value: "score" }, { label: "Speed", value: "speed" }, { label: "Cost ↑", value: "cost" },
        ]} />
      </ControlPanel>

      {loading ? (
        <div className="grid-3">{[...Array(6)].map((_, i) => <CardSkeleton key={i} />)}</div>
      ) : totalFiltered === 0 ? (
        <EmptyState />
      ) : (
        <>
          <ResultMeta n={totalFiltered} />
          <div className="grid-3">{slice.map((b, i) => <BenchmarkCard key={b.id} bench={b} i={i} />)}</div>
          <Paginator page={page} total={totalFiltered} onChange={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </>
      )}
    </div>
  );
}
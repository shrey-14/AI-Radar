"use client";
import { useState, useEffect } from "react";
import { api, Paper } from "@/lib/api";
import { PaperCard, FilterBar, SortBar, ControlPanel, ResultMeta, EmptyState, CardSkeleton, AnimatedNumber } from "@/components/ui";

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

export default function PapersPage() {
  const [all,    setAll]    = useState<Paper[]>([]);
  const [loading,setLoading]= useState(true);
  const [total,  setTotal]  = useState(0);
  const [source, setSource] = useState("");
  const [cat,    setCat]    = useState("");
  const [sort,   setSort]   = useState("fetched");
  const [page,   setPage]   = useState(1);

  useEffect(() => {
    setLoading(true);
    api.papers("limit=100&sort_by=fetched_at")
      .then((r) => { setAll(r.data); setTotal(r.pagination.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setPage(1); }, [source, cat, sort]);

  let rows = all.filter((p) => (!source || p.source === source) && (!cat || p.primary_category === cat));
  rows = [...rows].sort((a, b) =>
    sort === "relevance" ? ((b.relevance_score ?? 0) - (a.relevance_score ?? 0)) :
    sort === "upvotes"   ? ((b.upvotes ?? 0) - (a.upvotes ?? 0)) :
    (b.published_date ?? "").localeCompare(a.published_date ?? "")
  );

  const totalFiltered = rows.length;
  const slice = rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  return (
    <div className="shell" style={{ paddingTop: 40, paddingBottom: 80 }}>
      <div style={{ marginBottom: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--iris)", fontWeight: 600, letterSpacing: "0.1em" }}>§01</span>
          <span className="eyebrow">arXiv · HuggingFace Daily · OpenReview</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, borderBottom: "1px solid var(--border)", paddingBottom: 20 }}>
          <h1 className="serif" style={{ fontSize: "clamp(40px,7vw,72px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 0.95, color: "var(--text)" }}>Research Papers</h1>
          <div style={{ textAlign: "right" }}>
            <div className="mono" style={{ fontSize: 30, fontWeight: 700, color: "var(--iris)" }}><AnimatedNumber value={total} /></div>
            <div className="kicker">records indexed</div>
          </div>
        </div>
      </div>

      <ControlPanel>
        <FilterBar label="Source" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={source} onChange={setSource} filters={[
          { label: "All", value: "" }, { label: "arXiv", value: "arxiv" },
          { label: "HF Daily", value: "hf_daily_papers" }, { label: "OpenReview", value: "openreview" },
        ]} />
        <FilterBar label="Field" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={cat} onChange={setCat} filters={[
          { label: "All", value: "" }, { label: "cs.AI", value: "cs.AI" }, { label: "cs.LG", value: "cs.LG" },
          { label: "cs.CL", value: "cs.CL" }, { label: "cs.CV", value: "cs.CV" }, { label: "stat.ML", value: "stat.ML" },
        ]} />
        <SortBar value={sort} onChange={setSort} labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} options={[
          { label: "Fetched", value: "fetched" }, { label: "Relevance", value: "relevance" }, { label: "Upvotes", value: "upvotes" },
        ]} />
      </ControlPanel>

      {loading ? (
        <div className="grid-2">{[...Array(4)].map((_, i) => <CardSkeleton key={i} />)}</div>
      ) : totalFiltered === 0 ? (
        <EmptyState />
      ) : (
        <>
          <ResultMeta n={totalFiltered} />
          <div className="grid-2">{slice.map((p, i) => <PaperCard key={p.id} paper={p} i={i} />)}</div>
          <Paginator page={page} total={totalFiltered} onChange={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </>
      )}
    </div>
  );
}
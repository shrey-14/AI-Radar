"use client";
import { useState, useEffect } from "react";
import { api, NewsArticle } from "@/lib/api";
import { NewsCard, FilterBar, SortBar, ControlPanel, ResultMeta, EmptyState, CardSkeleton, AnimatedNumber } from "@/components/ui";

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

export default function NewsPage() {
  const [all,    setAll]    = useState<NewsArticle[]>([]);
  const [loading,setLoading]= useState(true);
  const [total,  setTotal]  = useState(0);
  const [source, setSource] = useState("");
  const [cat,    setCat]    = useState("");
  const [sort,   setSort]   = useState("fetched");
  const [page,   setPage]   = useState(1);

  useEffect(() => {
    setLoading(true);
    api.news("limit=100&sort_by=fetched_at")
      .then((r) => { setAll(r.data); setTotal(r.pagination.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setPage(1); }, [source, cat, sort]);

  let rows = all.filter((a) => (!source || a.source === source) && (!cat || a.category === cat));
  rows = [...rows].sort((a, b) =>
    sort === "significance" ? ((b.significance_score ?? 0) - (a.significance_score ?? 0)) :
    (b.published_date ?? "").localeCompare(a.published_date ?? "")
  );

  const totalFiltered = rows.length;
  const slice = rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  return (
    <div className="shell" style={{ paddingTop: 40, paddingBottom: 80 }}>
      <div style={{ marginBottom: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--azure)", fontWeight: 600, letterSpacing: "0.1em" }}>§02</span>
          <span className="eyebrow">Anthropic · OpenAI · DeepMind · Meta · TLDR · TechCrunch · Import AI</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, borderBottom: "1px solid var(--border)", paddingBottom: 20 }}>
          <h1 className="serif" style={{ fontSize: "clamp(40px,7vw,72px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 0.95, color: "var(--text)" }}>Industry News</h1>
          <div style={{ textAlign: "right" }}>
            <div className="mono" style={{ fontSize: 30, fontWeight: 700, color: "var(--azure)" }}><AnimatedNumber value={total} /></div>
            <div className="kicker">records indexed</div>
          </div>
        </div>
      </div>

      <ControlPanel>
        <FilterBar label="Source" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={source} onChange={setSource} filters={[
          { label: "All", value: "" }, { label: "Anthropic", value: "anthropic" }, { label: "OpenAI", value: "openai" },
          { label: "DeepMind", value: "google_deepmind" }, { label: "Meta AI", value: "meta_ai" },
          { label: "TLDR AI", value: "tldr_ai" }, { label: "TechCrunch", value: "techcrunch_ai" },
        ]} />
        <FilterBar label="Type" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={cat} onChange={setCat} filters={[
          { label: "All", value: "" }, { label: "Product", value: "product_launch" }, { label: "Research", value: "research" },
          { label: "Funding", value: "funding" }, { label: "Safety", value: "safety" }, { label: "Open Source", value: "open_source" },
        ]} />
        <SortBar value={sort} onChange={setSort} labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} options={[
          { label: "Fetched", value: "fetched" }, { label: "Significance", value: "significance" },
        ]} />
      </ControlPanel>

      {loading ? (
        <div className="grid-2">{[...Array(4)].map((_, i) => <CardSkeleton key={i} />)}</div>
      ) : totalFiltered === 0 ? (
        <EmptyState />
      ) : (
        <>
          <ResultMeta n={totalFiltered} />
          <div className="grid-2">{slice.map((a, i) => <NewsCard key={a.id} article={a} i={i} />)}</div>
          <Paginator page={page} total={totalFiltered} onChange={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </>
      )}
    </div>
  );
}
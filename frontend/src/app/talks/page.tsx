"use client";
import { useState, useEffect } from "react";
import { api, Talk } from "@/lib/api";
import { TalkCard, FilterBar, SortBar, ControlPanel, ResultMeta, EmptyState, CardSkeleton, AnimatedNumber } from "@/components/ui";

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

export default function TalksPage() {
  const [all,     setAll]     = useState<Talk[]>([]);
  const [loading, setLoading] = useState(true);
  const [total,   setTotal]   = useState(0);
  const [channel, setChannel] = useState("");
  const [diff,    setDiff]    = useState("");
  const [sort,    setSort]    = useState("fetched");
  const [page,    setPage]    = useState(1);

  useEffect(() => {
    setLoading(true);
    api.talks("limit=100&sort_by=fetched_at")
      .then((r) => { setAll(r.data); setTotal(r.pagination.total); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { setPage(1); }, [channel, diff, sort]);

  let rows = all.filter((t) => (!channel || t.channel === channel) && (!diff || t.difficulty_level === diff));
  rows = [...rows].sort((a, b) =>
    sort === "relevance" ? ((b.relevance_score ?? 0) - (a.relevance_score ?? 0)) :
    (b.published_date ?? "").localeCompare(a.published_date ?? "")
  );

  const totalFiltered = rows.length;
  const slice = rows.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  return (
    <div className="shell" style={{ paddingTop: 40, paddingBottom: 80 }}>
      <div style={{ marginBottom: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--coral)", fontWeight: 600, letterSpacing: "0.1em" }}>§05</span>
          <span className="eyebrow">Lex Fridman · Yannic Kilcher · Two Minute Papers · AI Explained</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, borderBottom: "1px solid var(--border)", paddingBottom: 20 }}>
          <h1 className="serif" style={{ fontSize: "clamp(40px,7vw,72px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 0.95, color: "var(--text)" }}>Talks & Explainers</h1>
          <div style={{ textAlign: "right" }}>
            <div className="mono" style={{ fontSize: 30, fontWeight: 700, color: "var(--coral)" }}><AnimatedNumber value={total} /></div>
            <div className="kicker">records indexed</div>
          </div>
        </div>
      </div>

      <ControlPanel>
        <FilterBar label="Channel" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={channel} onChange={setChannel} filters={[
          { label: "All", value: "" }, { label: "Lex Fridman", value: "Lex Fridman" },
          { label: "Yannic Kilcher", value: "Yannic Kilcher" }, { label: "Two Minute Papers", value: "Two Minute Papers" },
          { label: "AI Explained", value: "AI Explained" },
        ]} />
        <FilterBar label="Level" labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} value={diff} onChange={setDiff} filters={[
          { label: "All", value: "" }, { label: "Beginner", value: "Beginner" },
          { label: "Intermediate", value: "Intermediate" }, { label: "Advanced", value: "Advanced" },
        ]} />
        <SortBar value={sort} onChange={setSort} labelStyle={{ fontSize: "clamp(10px, 2vw, 12px)", minWidth: 72, marginRight: 12 }} options={[
          { label: "Fetched", value: "fetched" }, { label: "Relevance", value: "relevance" }, { label: "Published", value: "published" },
        ]} />
      </ControlPanel>

      {loading ? (
        <div className="grid-2">{[...Array(4)].map((_, i) => <CardSkeleton key={i} />)}</div>
      ) : totalFiltered === 0 ? (
        <EmptyState />
      ) : (
        <>
          <ResultMeta n={totalFiltered} />
          <div className="grid-2">{slice.map((t, i) => <TalkCard key={t.id} talk={t} i={i} />)}</div>
          <Paginator page={page} total={totalFiltered} onChange={(p) => { setPage(p); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
        </>
      )}
    </div>
  );
}
"use client";
import { useState, useEffect, useRef } from "react";
import type { Paper, NewsArticle, Tool, Benchmark, Talk } from "@/lib/api";

/* ── helpers ── */
export const cx = (...a: (string | boolean | undefined | null)[]) =>
  a.filter(Boolean).join(" ");

export const fmtMin = (wc?: number | null) =>
  wc ? Math.round(wc / 150) + " min" : null;

export const fmtK = (n?: number | null): string | null => {
  if (n == null) return null;
  return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + "k" : String(n);
};

/* ── Source metadata ── */
const SOURCE_META: Record<string, { label: string; hue: string }> = {
  arxiv:                { label: "arXiv",               hue: "#FF7A8A" },
  hf_daily_papers:      { label: "HF Daily",            hue: "#F6B84E" },
  openreview:           { label: "OpenReview",          hue: "#6FB0FF" },
  anthropic:            { label: "Anthropic",           hue: "#D69A6B" },
  openai:               { label: "OpenAI",              hue: "#5FE3B0" },
  google_deepmind:      { label: "DeepMind",            hue: "#6FB0FF" },
  meta_ai:              { label: "Meta AI",             hue: "#6FB0FF" },
  tldr_ai:              { label: "TLDR AI",             hue: "#F6B84E" },
  techcrunch_ai:        { label: "TechCrunch",          hue: "#5FE3B0" },
  import_ai:            { label: "Import AI",           hue: "#B69CFF" },
  github_trending:      { label: "GitHub",              hue: "#EDE9F5" },
  hf_hub_model:         { label: "HF Hub",              hue: "#F6B84E" },
  hf_spaces:            { label: "HF Spaces",           hue: "#F6B84E" },
  product_hunt:         { label: "Product Hunt",        hue: "#FF7A8A" },
  open_llm_leaderboard: { label: "Open LLM",            hue: "#B69CFF" },
  lmsys_arena:          { label: "LMSYS Arena",         hue: "#6FB0FF" },
  artificial_analysis:  { label: "Artificial Analysis", hue: "#5FE3B0" },
};

const ORG_HUE: Record<string, string> = {
  Anthropic: "#D69A6B", Google: "#6FB0FF", OpenAI: "#5FE3B0",
  Meta: "#6FB0FF", Alibaba: "#F6B84E", DeepSeek: "#B69CFF", Mistral: "#FF7A8A",
};

const CHANNEL: Record<string, { hue: string; tag: string }> = {
  "Lex Fridman":       { hue: "#EDE9F5", tag: "azure" },
  "Yannic Kilcher":    { hue: "#B69CFF", tag: "iris"  },
  "Two Minute Papers": { hue: "#F6B84E", tag: "amber" },
  "AI Explained":      { hue: "#6FB0FF", tag: "azure" },
};

const CAT_HUE: Record<string, string> = {
  product_launch: "iris", research: "azure", funding: "amber",
  safety: "coral", open_source: "mint", partnership: "azure",
};

/* ── scoreColor (0–1 normalised) ── */
function scoreColor(p: number): string {
  return p >= 0.75 ? "var(--mint)" : p >= 0.5 ? "var(--amber)" : p >= 0.3 ? "var(--text-2)" : "var(--coral)";
}

/* ══════════════════════════════════════
   PRIMITIVES
══════════════════════════════════════ */

export function Reveal({ i = 0, className = "", children, style, as: Tag = "div", ...rest }:
  { i?: number; className?: string; children?: React.ReactNode; style?: React.CSSProperties; as?: React.ElementType; [key: string]: unknown }) {
  const d = Math.min(i, 8);
  return (
    <Tag className={cx("rise", d ? "d" + d : "", className)} style={style} {...rest}>
      {children}
    </Tag>
  );
}

export function AnimatedNumber({ value, decimals = 0, duration = 900, suffix = "" }:
  { value: number; decimals?: number; duration?: number; suffix?: string }) {
  const [n, setN] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let raf: number;
    let started = false;
    const obs = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (e.isIntersecting && !started) {
          started = true;
          const t0 = performance.now();
          const tick = (t: number) => {
            const p    = Math.min(1, (t - t0) / duration);
            const ease = 1 - Math.pow(1 - p, 3);
            setN(value * ease);
            if (p < 1) raf = requestAnimationFrame(tick);
          };
          raf = requestAnimationFrame(tick);
        }
      });
    }, { threshold: 0.4 });
    if (ref.current) obs.observe(ref.current);
    return () => { obs.disconnect(); cancelAnimationFrame(raf); };
  }, [value, duration]);
  const formatted = decimals > 0 ? n.toFixed(decimals) : Math.round(n).toLocaleString("en-US");
  return <span ref={ref}>{formatted}{suffix}</span>;
}

export function ScoreBadge({ score, max = 10, type = "relevance", size = "sm" }:
  { score?: number | null; max?: number; type?: "relevance" | "significance" | "average"; size?: "sm" | "lg" }) {
  if (score == null) return null;
  const pct = type === "average" ? score / 100 : score / max;
  const col = scoreColor(pct);
  const big = size === "lg";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span className="meter-track" style={{ width: big ? 34 : 24, height: big ? 4 : 3, flexShrink: 0 }}>
        <span className="meter-fill" style={{ width: `${pct * 100}%`, background: col }} />
      </span>
      <span className="mono" style={{ fontSize: big ? 13 : 11, fontWeight: 600, color: col, letterSpacing: "0.02em" }}>
        {type === "average" ? `${score.toFixed(1)}` : `${score}`}
        <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>
          {type === "average" ? "%" : "/10"}
        </span>
      </span>
    </span>
  );
}

export function SourceBadge({ source, strong }: { source: string; strong?: boolean }) {
  const m = SOURCE_META[source] || { label: source, hue: "var(--text-mut)" };
  return (
    <span className="tag" style={strong ? { color: m.hue, borderColor: m.hue + "44", background: m.hue + "14" } : {}}>
      <span className="dot" style={{ background: m.hue }} />
      {m.label}
    </span>
  );
}

export function TagList({ tags, max = 99, variant = "" }: { tags?: string[]; max?: number; variant?: string }) {
  if (!tags || !tags.length) return null;
  const shown = tags.slice(0, max);
  const extra = tags.length - max;
  const cls   = variant ? "tag tag-" + variant : "tag";
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
      {shown.map((t, i) => <span key={i} className={cls}>{t}</span>)}
      {extra > 0 && <span className="tag" style={{ color: "var(--text-dim)" }}>+{extra}</span>}
    </div>
  );
}

export function Field({ label, children, color = "var(--text-2)", mb = 13, labelStyle }:
  { label: string; children?: React.ReactNode; color?: string; mb?: number; labelStyle?: React.CSSProperties }) {
  if (!children) return null;
  return (
    <div style={{ marginBottom: mb }}>
      <div className="flabel" style={{ marginBottom: 6, ...labelStyle }}>{label}</div>
      <p style={{ fontSize: 13.5, color, lineHeight: 1.62, fontFamily: "var(--sans)" }}>{children as string}</p>
    </div>
  );
}

export function BulletField({ label, items, mark = "›", markColor = "var(--iris)", mb = 14 }:
  { label: string; items?: string[]; mark?: string; markColor?: string; mb?: number }) {
  if (!items || !items.length) return null;
  return (
    <div style={{ marginBottom: mb }}>
      <div className="flabel" style={{ marginBottom: 8 }}>{label}</div>
      <ul style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {items.map((it, i) => (
          <li key={i} style={{ fontSize: 13, color: "var(--text-2)", paddingLeft: 16, position: "relative", lineHeight: 1.55 }}>
            <span className="mono" style={{ position: "absolute", left: 0, color: markColor, fontWeight: 700 }}>{mark}</span>
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Stat({ label, children, color = "var(--text)", big, labelStyle }:
  { label: string; children: React.ReactNode; color?: string; big?: boolean; labelStyle?: React.CSSProperties }) {
  return (
    <div>
      <div className="kicker" style={{ marginBottom: 3, ...labelStyle }}>{label}</div>
      <div className="mono" style={{ fontSize: big ? 18 : 14, fontWeight: 600, color }}>{children}</div>
    </div>
  );
}

export function MeterRow({ label, value, suffix = "", maxv = 100 }:
  { label: string; value: number; suffix?: string; maxv?: number }) {
  const p   = Math.max(0, Math.min(1, value / maxv));
  const col = scoreColor(p);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span className="mono" style={{ fontSize: 9.5, color: "var(--text-mut)", width: 62, letterSpacing: "0.06em", flexShrink: 0 }}>{label}</span>
      <span className="meter-track" style={{ flex: 1 }}>
        <span className="meter-fill" style={{ width: `${p * 100}%`, background: col }} />
      </span>
      <span className="mono" style={{ fontSize: 11, fontWeight: 600, color: col, width: 38, textAlign: "right", flexShrink: 0 }}>
        {value.toFixed(1)}{suffix}
      </span>
    </div>
  );
}

export function FilterBar({ label, filters, value, onChange, style, labelStyle }:
  { label?: string; filters: { label: string; value: string }[]; value: string; onChange: (v: string) => void; style?: React.CSSProperties; labelStyle?: React.CSSProperties }) {
  return (
    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8, ...style }}>
      {label && <span className="kicker" style={{ width: 54, ...labelStyle }}>{label}</span>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
        {filters.map((f) => (
          <button key={f.value} className={cx("fpill", value === f.value && "on")} onClick={() => onChange(f.value)}>
            {f.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SortBar({ options, value, onChange, labelStyle }:
  { options: { label: string; value: string }[]; value: string; onChange: (v: string) => void; labelStyle?: React.CSSProperties }) {
  return (
    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
      <span className="kicker" style={{ width: 54, ...labelStyle }}>Sort</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
        {options.map((o) => (
          <button key={o.value} onClick={() => onChange(o.value)} className={cx("fpill", value === o.value && "on")}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function EmptyState({ message = "No signal on this frequency." }: { message?: string }) {
  return (
    <div style={{ textAlign: "center", padding: "70px 24px", border: "1px dashed var(--border-lt)", color: "var(--text-mut)" }}>
      <div className="mono" style={{ fontSize: 30, marginBottom: 14, color: "var(--text-dim)" }}>∅</div>
      <p className="mono" style={{ fontSize: 12.5, letterSpacing: "0.04em" }}>{message}</p>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div className="skel" style={{ width: 90, height: 18 }} />
        <div className="skel" style={{ width: 40, height: 18 }} />
      </div>
      <div className="skel" style={{ width: "85%", height: 22, marginBottom: 10 }} />
      <div className="skel" style={{ width: "100%", height: 52, marginBottom: 14 }} />
      <div className="skel" style={{ width: "60%", height: 14 }} />
    </div>
  );
}

export function ControlPanel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", gap: 14, padding: "20px 22px",
      background: "var(--bg-panel)", border: "1px solid var(--border)", marginBottom: 28, ...style,
    }}>
      {children}
    </div>
  );
}

export function ResultMeta({ n }: { n: number }) {
  return (
    <div className="mono" style={{ fontSize: 11, color: "var(--text-mut)", marginBottom: 18 }}>
      Showing <span style={{ color: "var(--iris)" }}>{n}</span> result{n === 1 ? "" : "s"} · sorted live
    </div>
  );
}

/* ══════════════════════════════════════
   CARDS
══════════════════════════════════════ */

export function PaperCard({ paper: p, i = 0, feature = false }: { paper: Paper; i?: number; feature?: boolean }) {
  return (
    <Reveal i={i} as="a" className="card card-link"
      style={{ padding: feature ? 26 : 20, display: "flex", flexDirection: "column" }}
      href={p.source_url} target="_blank" rel="noopener noreferrer">

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
          <SourceBadge source={p.source} strong />
          {p.primary_category && <span className="tag">{p.primary_category}</span>}
          {p.decision === "Accept" && <span className="tag tag-mint">✓ {p.venue || "Accepted"}</span>}
          {p.upvotes != null && p.upvotes > 0 && <span className="tag tag-amber">▲ {p.upvotes}</span>}
        </div>
        <ScoreBadge score={p.relevance_score} size={feature ? "lg" : "sm"} />
      </div>

      <h3 style={{
        fontFamily: feature ? "var(--serif)" : "var(--sans)",
        fontWeight: feature ? 400 : 600,
        fontSize: feature ? 30 : 16.5, lineHeight: feature ? 1.08 : 1.32,
        letterSpacing: feature ? "-0.01em" : "-0.005em", marginBottom: 10, color: "var(--text)",
      }}>{p.title}</h3>

      {p.one_line_summary && (
        <p style={{ fontSize: "clamp(12px,2vw,14px)", color: "var(--iris-bright)", lineHeight: 1.55, marginBottom: 16, fontStyle: "italic", letterSpacing: "0.02em" }}>
          {p.one_line_summary}
        </p>
      )}

      <hr className="rule" style={{ marginBottom: 14 }} />

      <div className={feature ? "paper-grid" : ""}>
        <Field label="Problem"          labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }}>{p.problem_solved}</Field>
        <Field label="Approach"         labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }}>{p.approach_used}</Field>
        <Field label="Key Results"      labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }} color="var(--text)">{p.key_results}</Field>
        <Field label="Real-World Impact" labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }}>{p.real_world_impact}</Field>
      </div>
      {p.limitations && <Field label="Limitations" labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }} color="var(--text-mut)">{p.limitations}</Field>}

      {p.keywords && p.keywords.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div className="flabel" style={{ marginBottom: 7 }}>Author Keywords</div>
          <TagList tags={p.keywords} max={8} />
        </div>
      )}

      <div style={{ marginTop: "auto" }}>
        <hr className="rule" style={{ margin: "4px 0 13px" }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {p.first_author && (
              <span className="mono" style={{ fontSize: 11.5, color: "var(--text-2)" }}>
                {p.first_author}
                {p.author_count > 1 && <span style={{ color: "var(--text-dim)" }}> +{p.author_count - 1}</span>}
              </span>
            )}
            {p.published_date && <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>{p.published_date}</span>}
          </div>
          <TagList tags={p.ai_tags} max={4} variant="iris" />
        </div>
      </div>
    </Reveal>
  );
}

export function NewsCard({ article: a, i = 0, feature = false }: { article: NewsArticle; i?: number; feature?: boolean }) {
  return (
    <Reveal i={i} as="a" className="card card-link"
      style={{ padding: feature ? 28 : 20, display: "flex", flexDirection: "column" }}
      href={a.url} target="_blank" rel="noopener noreferrer">

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: feature ? 16 : 13 }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
          <SourceBadge source={a.source} strong />
          {a.category && <span className={"tag tag-" + (CAT_HUE[a.category] || "")}>{a.category.replace(/_/g, " ")}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {a.published_date && <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>{a.published_date}</span>}
          <ScoreBadge score={a.significance_score} type="significance" size={feature ? "lg" : "sm"} />
        </div>
      </div>

      <h3 style={{
        fontFamily: feature ? "var(--serif)" : "var(--sans)",
        fontWeight: feature ? 400 : 600,
        fontSize: feature ? 40 : 17, lineHeight: feature ? 1.04 : 1.3,
        letterSpacing: feature ? "-0.015em" : "-0.005em", marginBottom: 12, color: "var(--text)",
        maxWidth: feature ? "16ch" : "none",
      }}>{a.title}</h3>

      {a.summary && (
        <p style={{ fontSize: feature ? 15.5 : 13.5, color: "var(--text-2)", lineHeight: 1.65, marginBottom: 16, maxWidth: feature ? "62ch" : "none" }}>
          {a.summary}
        </p>
      )}

      {a.key_points && a.key_points.length > 0 && (
        <>
          <hr className="rule" style={{ marginBottom: 13 }} />
          <BulletField label="Key Takeaways" items={a.key_points} />
        </>
      )}

      <hr className="rule" style={{ marginBottom: 13 }} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 22, marginBottom: 14 }}>
        {a.companies_mentioned.length > 0 && (
          <div>
            <div className="flabel" style={{ marginBottom: 7 }}>Companies</div>
            <TagList tags={a.companies_mentioned} />
          </div>
        )}
        {a.models_mentioned.length > 0 && (
          <div>
            <div className="flabel" style={{ marginBottom: 7 }}>Models</div>
            <TagList tags={a.models_mentioned} variant="azure" />
          </div>
        )}
      </div>

      <div style={{ marginTop: "auto" }}>
        <TagList tags={a.ai_tags} variant="iris" />
      </div>
    </Reveal>
  );
}

/* ── Tool Card ─────────────────────────────────────────────────── */

export function ToolCard({ tool: t, i = 0 }: { tool: Tool; i?: number }) {
  const primary = t.stars ?? t.likes ?? t.votes ?? t.downloads;
  const pMark   = t.stars != null ? "★" : t.likes != null ? "❤︎" : t.votes != null ? "▲" : "↓";
  const pKey    = t.stars != null ? "Stars" : t.likes != null ? "Likes" : t.votes != null ? "Votes" : "Downloads";

  /* Platform ceiling — used to normalise the popularity bar.
     Reflects a realistic "top" for each platform:
     GitHub stars: 200k (top OSS projects)   HF likes: 50k   PH votes: 5k   Downloads: 50M */
  const CEIL = t.stars != null ? 200_000 : t.likes != null ? 50_000 : t.votes != null ? 5_000 : 50_000_000;

  return (
    <Reveal i={i} as="a" className="card card-link"
      style={{ padding: 20, display: "flex", flexDirection: "column" }}
      href={t.url} target="_blank" rel="noopener noreferrer">

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
          <SourceBadge source={t.source} strong />
          {t.language && <span className="tag tag-azure">{t.language}</span>}
          {t.pipeline_task && <span className="tag">{t.pipeline_task}</span>}
        </div>
        <ScoreBadge score={t.significance_score} type="significance" />
      </div>

      {/* Name */}
      <h3 style={{ fontFamily: "var(--sans)", fontWeight: 600, fontSize: 19, letterSpacing: "-0.01em", marginBottom: 2, color: "var(--text)" }}>{t.name}</h3>
      {t.author && <p className="mono" style={{ fontSize: 11, color: "var(--text-mut)", marginBottom: 12 }}>by {t.author}</p>}

      {/* ── Popularity block ── */}
      {primary != null && (() => {
        const pct   = Math.min(1, primary / CEIL);
        /* colour scale: top-tier = mint, mid = amber, emerging = iris */
        const barCol = pct >= 0.5 ? "var(--mint)" : pct >= 0.15 ? "var(--amber)" : "var(--iris)";
        return (
          <div style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", padding: "13px 15px", marginBottom: 14 }}>
            {/* Count row */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 10 }}>
              <div>
                <div className="kicker" style={{ marginBottom: 3 }}>{pKey}</div>
                <div className="mono" style={{ fontSize: 24, fontWeight: 700, color: "var(--text)", lineHeight: 1 }}>
                  <span style={{ color: "var(--amber)",  marginRight: 6, fontSize: "clamp(20px, 2vw, 25px)" }}>{pMark}</span>
                  <AnimatedNumber value={primary} />
                </div>
              </div>
              {t.trending_score != null && (
                <div style={{ textAlign: "right" }}>
                  <div className="kicker" style={{ marginBottom: 3 }}>Trend Score</div>
                  <div className="mono" style={{ fontSize: 16, fontWeight: 600, color: "var(--mint)", lineHeight: 1 }}>
                    {t.trending_score.toFixed(1)}
                  </div>
                </div>
              )}
            </div>

            {/* Popularity bar — normalised to platform ceiling */}
            <div style={{ marginBottom: 4 }}>
              <span className="meter-track" style={{ display: "block", height: 5, background: "var(--bg-elev-2)" }}>
                <span className="meter-fill" style={{ width: `${pct * 100}%`, background: barCol }} />
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="mono" style={{ fontSize: 9, color: "var(--text-dim)" }}>
                {(pct * 100).toFixed(1)}% of platform top
              </span>
              <span className="mono" style={{ fontSize: 9, color: "var(--text-dim)" }}>
                ceiling: {CEIL.toLocaleString("en-US")}
              </span>
            </div>
          </div>
        );
      })()}

      {/* What it does */}
      {t.what_it_does && (
        <p style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.65, marginBottom: 15 }}>{t.what_it_does}</p>
      )}

      <hr className="rule" style={{ marginBottom: 13 }} />

      {/* Why trending */}
      {t.why_trending && (
        <div style={{ marginBottom: 14, paddingLeft: 12, borderLeft: "2px solid var(--amber)" }}>
          <div className="flabel" style={{ marginBottom: 5, justifyContent: "flex-start" }}>
            <span style={{ color: "var(--amber)" }}>↗ Why Trending</span>
          </div>
          <p style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.5 }}>{t.why_trending}</p>
        </div>
      )}

      <BulletField label="Use Cases" items={t.use_cases} mark="→" />

      {/* Downloads + trend score row (only if not already shown above) */}
      {t.downloads != null && (
        <>
          <hr className="rule" style={{ marginBottom: 13 }} />
          <div style={{ display: "flex", gap: 28, marginBottom: 14 }}>
            <Stat label="Downloads" labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }}>
              {t.downloads.toLocaleString("en-US")}
            </Stat>
            {t.trending_score != null && (
              <Stat label="Trend Score" labelStyle={{ fontSize: "clamp(10px,2vw,12px)" }} color="var(--mint)">
                {t.trending_score.toFixed(1)}
              </Stat>
            )}
          </div>
        </>
      )}

      {/* Tags footer */}
      <div style={{ marginTop: "auto" }}>
        <hr className="rule" style={{ marginBottom: 13 }} />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          <TagList tags={t.tags} max={5} />
          <TagList tags={t.ai_tags} max={3} variant="iris" />
        </div>
      </div>
    </Reveal>
  );
}

/* ── Benchmark Card ────────────────────────────────────────────── */

export function BenchmarkCard({ bench: b, i = 0 }: { bench: Benchmark; i?: number }) {
  const kind   = b.source;
  const orgHue = ORG_HUE[b.organisation || ""] || "var(--iris)";

  /* Sub-scores for Open LLM leaderboard */
  const subScores = [
    { label: "IFEVAL",   v: b.ifeval_score,   tip: "Instruction Following"    },
    { label: "BBH",      v: b.bbh_score,      tip: "Big Bench Hard Reasoning" },
    { label: "MATH",     v: b.math_score,     tip: "MATH Level 5"             },
    { label: "GPQA",     v: b.gpqa_score,     tip: "Graduate Science Q&A"     },
    { label: "MMLU-PRO", v: b.mmlu_pro_score, tip: "Multitask Understanding"  },
  ].filter((s) => s.v != null) as { label: string; v: number; tip: string }[];

  /* Hero metric — label + primary value + colour per leaderboard */
  const hero = kind === "lmsys_arena"
    ? { label: "Arena Elo",   value: b.elo_score         ?? 0, dec: 0, suffix: "",  color: "var(--iris)"  }
    : kind === "artificial_analysis"
    ? { label: "Intelligence", value: b.intelligence_score ?? 0, dec: 1, suffix: "",  color: "var(--mint)"  }
    : { label: "Avg Score",    value: b.average_score      ?? 0, dec: 1, suffix: "%", color: "var(--mint)"  };

  return (
    <Reveal i={i} className="card" style={{ padding: 20, display: "flex", flexDirection: "column" }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
          <SourceBadge source={b.source} strong />
          {b.license && (
            <span className={"tag " + (/MIT|Apache|Community/i.test(b.license) ? "tag-mint" : "")}>
              {b.license}
            </span>
          )}
        </div>
        {b.arena_rank != null && (
          <span className="mono" style={{
            fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", padding: "2px 8px",
            border: "1px solid currentColor", whiteSpace: "nowrap",
            color: b.arena_rank === 1 ? "var(--mint)" : b.arena_rank <= 5 ? "var(--amber)" : "var(--text-mut)",
          }}>
            RANK #{b.arena_rank}
          </span>
        )}
      </div>

      {/* ── Model identity ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 2 }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: orgHue, flexShrink: 0 }} />
        <h3 style={{
          fontFamily: "var(--sans)", fontWeight: 600, fontSize: 17,
          letterSpacing: "-0.01em", color: "var(--text)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          flex: 1, minWidth: 0,
        }}>
          {b.model_display_name}
        </h3>
      </div>
      <div className="mono" style={{ fontSize: 10.5, color: "var(--text-mut)", marginBottom: 16, paddingLeft: 18 }}>
        {b.organisation?.split(" ")[0]}
        {b.params_billions != null ? ` · ${b.params_billions}B params` : ""}
        {b.context_window  ? ` · ${b.context_window} ctx`           : ""}
      </div>

      {/* ══════════════════════════════════
          HERO METRIC BLOCK
          Real data replaces fake sparklines:
          • Open LLM → 5 sub-score mini bars
          • LMSYS    → vote count + rank
          • AA       → intelligence + speed bars
         ══════════════════════════════════ */}
      <div style={{
        position: "relative",
        background: "var(--bg-deep)",
        border: "1px solid var(--border-lt)",
        padding: "16px 18px",
        marginBottom: 16,
        overflow: "hidden",
      }}>
        {/* Subtle colour wash */}
        <div style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: `radial-gradient(130% 90% at 100% 0%, ${hero.color}18, transparent 60%)`,
        }} />

        <div style={{ position: "relative" }}>
          {/* Primary metric */}
          <div className="kicker" style={{ marginBottom: 4, letterSpacing: "0.14em" }}>{hero.label}</div>
          <div className="mono" style={{
            fontSize: 46, fontWeight: 700, lineHeight: 0.95,
            color: hero.color, letterSpacing: "-0.025em", marginBottom: 14,
          }}>
            <AnimatedNumber value={hero.value} decimals={hero.dec} suffix={hero.suffix} />
          </div>

          {/* ── Open LLM: 5 real benchmark sub-scores ── */}
          {kind === "open_llm_leaderboard" && subScores.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {subScores.map((s) => {
                const p   = Math.max(0, Math.min(1, s.v / 100));
                /* colour: green ≥70%, amber ≥45%, grey below */
                const col = p >= 0.70 ? "var(--mint)" : p >= 0.45 ? "var(--amber)" : "var(--text-mut)";
                return (
                  <div key={s.label} title={s.tip} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <span className="mono" style={{ fontSize: 9, color: "var(--text-dim)", width: 56, flexShrink: 0, letterSpacing: "0.04em" }}>
                      {s.label}
                    </span>
                    <span className="meter-track" style={{ flex: 1, height: 4, background: "var(--bg-elev-2)" }}>
                      <span className="meter-fill" style={{ width: `${p * 100}%`, background: col }} />
                    </span>
                    <span className="mono" style={{
                      fontSize: 11, fontWeight: 600, color: col,
                      width: 36, textAlign: "right", flexShrink: 0,
                    }}>
                      {s.v.toFixed(1)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* ── LMSYS: vote count + rank reliability ── */}
          {kind === "lmsys_arena" && (
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              {b.num_votes != null && (
                <div>
                  <div className="kicker" style={{ marginBottom: 3 }}>Human Votes</div>
                  <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)" }}>
                    {b.num_votes.toLocaleString("en-US")}
                  </div>
                  {/* Reliability bar — more votes = more reliable */}
                  {(() => {
                    const r   = Math.min(1, b.num_votes / 50_000); // 50k votes = max reliability
                    const col = r >= 0.6 ? "var(--mint)" : r >= 0.2 ? "var(--amber)" : "var(--iris)";
                    return (
                      <div style={{ marginTop: 5 }}>
                        <span className="meter-track" style={{ display: "block", width: 80, height: 3, background: "var(--bg-elev-2)" }}>
                          <span className="meter-fill" style={{ width: `${r * 100}%`, background: col }} />
                        </span>
                        <span className="mono" style={{ fontSize: 8, color: "var(--text-dim)", marginTop: 3, display: "block" }}>
                          vote reliability
                        </span>
                      </div>
                    );
                  })()}
                </div>
              )}
              {b.arena_rank != null && (
                <div>
                  <div className="kicker" style={{ marginBottom: 3 }}>Global Rank</div>
                  <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--amber)" }}>
                    #{b.arena_rank} <span style={{ fontSize: 10, color: "var(--text-dim)", fontWeight: 400 }}>of 180+</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Artificial Analysis: intelligence + speed bars ── */}
          {kind === "artificial_analysis" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {[
                { label: "Intelligence", v: b.intelligence_score, max: 65,  col: "var(--mint)",  unit: ""      },
                { label: "Speed",        v: b.speed_tps,          max: 300, col: "var(--azure)", unit: " t/s"  },
              ].filter((x) => x.v != null).map((x) => {
                const p = Math.max(0, Math.min(1, x.v! / x.max));
                return (
                  <div key={x.label} style={{ display: "flex", alignItems: "center", gap: 9 }}>
                    <span className="mono" style={{ fontSize: 9, color: "var(--text-dim)", width: 70, flexShrink: 0, letterSpacing: "0.04em" }}>
                      {x.label}
                    </span>
                    <span className="meter-track" style={{ flex: 1, height: 4, background: "var(--bg-elev-2)" }}>
                      <span className="meter-fill" style={{ width: `${p * 100}%`, background: x.col }} />
                    </span>
                    <span className="mono" style={{
                      fontSize: 11, fontWeight: 600, color: x.col,
                      width: 52, textAlign: "right", flexShrink: 0,
                    }}>
                      {x.v!.toFixed(1)}{x.unit}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Secondary stat grid (shown BELOW hero block) ── */}

      {/* LMSYS: speed + cost (if available) */}
      {kind === "lmsys_arena" && (b.input_cost_per_1m != null || b.speed_tps != null) && (
        <div style={{ display: "flex", gap: 0, marginBottom: 14, border: "1px solid var(--border)" }}>
          {b.speed_tps != null && (
            <div style={{ flex: 1, padding: "10px 13px", borderRight: b.input_cost_per_1m != null ? "1px solid var(--border)" : "none" }}>
              <Stat label="Speed" color="var(--azure)">
                ⚡ {b.speed_tps}<span style={{ fontSize: 10, color: "var(--text-mut)" }}> t/s</span>
              </Stat>
            </div>
          )}
          {b.input_cost_per_1m != null && (
            <div style={{ flex: 1, padding: "10px 13px", borderRight: b.output_cost_per_1m != null ? "1px solid var(--border)" : "none" }}>
              <Stat label="In / 1M" color="var(--mint)">${b.input_cost_per_1m}</Stat>
            </div>
          )}
          {b.output_cost_per_1m != null && (
            <div style={{ flex: 1, padding: "10px 13px" }}>
              <Stat label="Out / 1M" color="var(--amber)">${b.output_cost_per_1m}</Stat>
            </div>
          )}
        </div>
      )}

      {/* AA: cost grid */}
      {kind === "artificial_analysis" && (b.input_cost_per_1m != null || b.output_cost_per_1m != null) && (
        <div style={{ display: "flex", gap: 0, marginBottom: 14, border: "1px solid var(--border)" }}>
          {b.speed_tps != null && (
            <div style={{ flex: 1, padding: "10px 13px", borderRight: "1px solid var(--border)" }}>
              <Stat label="Speed" color="var(--azure)">
                ⚡ {b.speed_tps}<span style={{ fontSize: 10, color: "var(--text-mut)" }}> t/s</span>
              </Stat>
            </div>
          )}
          {b.input_cost_per_1m != null && (
            <div style={{ flex: 1, padding: "10px 13px", borderRight: b.output_cost_per_1m != null ? "1px solid var(--border)" : "none" }}>
              <Stat label="In / 1M" color="var(--mint)">${b.input_cost_per_1m}</Stat>
            </div>
          )}
          {b.output_cost_per_1m != null && (
            <div style={{ flex: 1, padding: "10px 13px" }}>
              <Stat label="Out / 1M" color="var(--amber)">${b.output_cost_per_1m}</Stat>
            </div>
          )}
        </div>
      )}

      {/* ── Model summary ── */}
      {b.model_summary && (
        <p style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.62, marginBottom: 15 }}>{b.model_summary}</p>
      )}

      <hr className="rule" style={{ marginBottom: 13 }} />

      {/* ── Strengths + Weaknesses ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 14, marginBottom: 14 }}>
        {b.strengths.length > 0 && (
          <BulletField label="Strengths"  items={b.strengths}  mark="+" markColor="var(--mint)"  mb={0} />
        )}
        {b.weaknesses.length > 0 && (
          <BulletField label="Weaknesses" items={b.weaknesses} mark="–" markColor="var(--coral)" mb={0} />
        )}
      </div>

      {/* ── Best for ── */}
      {b.best_for && (
        <div style={{ marginTop: "auto" }}>
          <hr className="rule" style={{ marginBottom: 12 }} />
          <div className="flabel" style={{ marginBottom: 6 }}>Best For</div>
          <p style={{
            fontSize: "clamp(11px,2vw,13px)", color: "var(--iris-bright)",
            lineHeight: 1.55, fontStyle: "italic", letterSpacing: "0.02em",
          }}>
            {b.best_for}
          </p>
        </div>
      )}
    </Reveal>
  );
}

/* ── Talk Card ─────────────────────────────────────────────────── */

export function TalkCard({ talk: t, i = 0, feature = false }: { talk: Talk; i?: number; feature?: boolean }) {
  const ch      = CHANNEL[t.channel] || { hue: "var(--text)", tag: "" };
  const diffTag = t.difficulty_level === "Advanced" ? "coral" : t.difficulty_level === "Intermediate" ? "amber" : "mint";

  return (
    <Reveal i={i} as="a" className="card card-link"
      style={{ padding: feature ? 26 : 20, display: "flex", flexDirection: "column" }}
      href={t.video_url} target="_blank" rel="noopener noreferrer">

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
          <span className={"tag tag-" + ch.tag} style={{ color: ch.hue, borderColor: ch.hue + "44" }}>
            <span style={{ marginRight: 1 }}>▶</span> {t.channel}
          </span>
          {t.difficulty_level && <span className={"tag tag-" + diffTag}>{t.difficulty_level}</span>}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {fmtMin(t.transcript_word_count) && (
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-mut)" }}>◷ {fmtMin(t.transcript_word_count)}</span>
          )}
          <ScoreBadge score={t.relevance_score} />
        </div>
      </div>

      <h3 style={{
        fontFamily: feature ? "var(--serif)" : "var(--sans)",
        fontWeight: feature ? 400 : 600,
        fontSize: feature ? 28 : 16.5, lineHeight: feature ? 1.1 : 1.3,
        letterSpacing: "-0.005em", marginBottom: 8, color: "var(--text)",
      }}>
        {t.title}
      </h3>

      {t.guest_name && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{
            width: 22, height: 22, borderRadius: "50%",
            background: "var(--bg-elev-2)", border: "1px solid var(--border-lt)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, color: ch.hue, fontFamily: "var(--mono)",
          }}>
            {t.guest_name.split(" ").map((w) => w[0]).slice(0, 2).join("")}
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--azure)" }}>{t.guest_name}</span>
          {t.guest_affiliation && (
            <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>· {t.guest_affiliation}</span>
          )}
        </div>
      )}

      {t.summary && (
        <p style={{ fontSize: 13.5, color: "var(--text-2)", lineHeight: 1.65, marginBottom: 15 }}>{t.summary}</p>
      )}

      {t.key_insights.length > 0 && (
        <>
          <hr className="rule" style={{ marginBottom: 13 }} />
          <BulletField label="Key Insights" items={t.key_insights} markColor={ch.hue} />
        </>
      )}

      {t.topics_covered.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div className="flabel" style={{ marginBottom: 7 }}>Topics</div>
          <TagList tags={t.topics_covered} />
        </div>
      )}

      {(t.papers_mentioned.length > 0 || t.people_mentioned.length > 0) && (
        <>
          <hr className="rule" style={{ marginBottom: 13 }} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 20, marginBottom: 14 }}>
            {t.papers_mentioned.length > 0 && (
              <div style={{ flex: 1, minWidth: 180 }}>
                <div className="flabel" style={{ marginBottom: 7 }}>Papers Referenced</div>
                <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  {t.papers_mentioned.map((pp, k) => (
                    <li key={k} className="mono" style={{ fontSize: 11, color: "var(--text-2)", paddingLeft: 12, position: "relative" }}>
                      <span style={{ position: "absolute", left: 0, color: "var(--iris)" }}>·</span>{pp}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {t.people_mentioned.length > 0 && (
              <div>
                <div className="flabel" style={{ marginBottom: 7 }}>People</div>
                <TagList tags={t.people_mentioned} />
              </div>
            )}
          </div>
        </>
      )}

      <div style={{ marginTop: "auto" }}>
        <hr className="rule" style={{ marginBottom: 12 }} />
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)" }}>{t.published_date}</span>
          <TagList tags={t.ai_tags} max={4} variant="iris" />
        </div>
      </div>
    </Reveal>
  );
}
"use client";
import { useState, useEffect, useRef } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, Paper, NewsArticle, Tool, Benchmark, Talk } from "@/lib/api";
import { AnimatedNumber, cx } from "@/components/ui";

const NAV = [
  { href: "/",           label: "Digest"     },
  { href: "/ask",        label: "Ask AI"     },
  { href: "/papers",     label: "Papers"     },
  { href: "/news",       label: "News"       },
  { href: "/tools",      label: "Tools"      },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/talks",      label: "Talks"      },
];

type StatusData = { papers:{summarised:number}; news:{summarised:number}; tools:{summarised:number}; benchmarks:{summarised:number}; talks:{summarised:number} };

/* ── Radar mark SVG ── */
function RadarMark() {
  return (
    <span style={{ position: "relative", width: 30, height: 30, display: "inline-flex", flexShrink: 0 }}>
      <svg width="30" height="30" viewBox="0 0 30 30">
        <circle cx="15" cy="15" r="13" fill="none" stroke="var(--border-lt)" strokeWidth="1" />
        <circle cx="15" cy="15" r="8"  fill="none" stroke="var(--border)"    strokeWidth="1" />
        <circle cx="15" cy="15" r="3.5" fill="none" stroke="var(--border)"   strokeWidth="1" />
        <line x1="15" y1="15" x2="15" y2="2" stroke="var(--iris)" strokeWidth="1.5"
          style={{ transformOrigin: "15px 15px", animation: "radar-sweep 4s linear infinite" }} />
        <circle cx="21" cy="9" r="1.6" fill="var(--mint)" />
      </svg>
    </span>
  );
}

/* ── Ticker strip ── */
// function Ticker({ status }: { status: StatusData | null }) {
//   const items = status ? [
//     { k: "PAPERS",     v: `${status.papers.summarised} indexed`,     c: "iris"  },
//     { k: "NEWS",       v: `${status.news.summarised} articles`,      c: "azure" },
//     { k: "TOOLS",      v: `${status.tools.summarised} trending`,     c: "mint"  },
//     { k: "BENCHMARKS", v: `${status.benchmarks.summarised} models`,  c: "amber" },
//     { k: "TALKS",      v: `${status.talks.summarised} episodes`,     c: "iris"  },
//     { k: "PIPELINE",   v: "runs daily at 07:00 UTC",                  c: "mint"  },
//   ] : [];
//   const doubled = [...items, ...items];
//   const hue: Record<string, string> = { mint: "var(--mint)", iris: "var(--iris)", amber: "var(--amber)", azure: "var(--azure)" };
//   if (!items.length) return null;
//   return (
//     <div className="ticker-wrap" style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-deep)", overflow: "hidden", height: 30, display: "flex", alignItems: "center", position: "relative", zIndex: 40 }}>
//       <span className="mono" style={{ flexShrink: 0, padding: "0 14px", height: "100%", display: "flex", alignItems: "center", fontSize: 10, letterSpacing: "0.12em", color: "var(--bg)", background: "var(--iris)", fontWeight: 700, position: "relative", zIndex: 2, whiteSpace: "nowrap" }}>
//         LIVE&nbsp;FEED
//       </span>
//       <div style={{ overflow: "hidden", flex: 1 }}>
//         <div className="ticker-track">
//           {doubled.map((it, i) => (
//             <span key={i} className="mono" style={{ fontSize: 11, padding: "0 22px", display: "inline-flex", alignItems: "center", gap: 8, borderRight: "1px solid var(--border)" }}>
//               <span style={{ color: hue[it.c] || "var(--iris)", fontWeight: 600 }}>{it.k}</span>
//               <span style={{ color: "var(--text-mut)" }}>{it.v}</span>
//             </span>
//           ))}
//         </div>
//       </div>
//     </div>
//   );
// }

function Ticker({ items }: { items: { label: string; title: string; color: string; breaking: boolean }[] }) {
  if (!items.length) return null;
  const doubled = [...items, ...items]; // double for seamless loop

  return (
    <div
      className="ticker-wrap"
      style={{
        borderBottom: "1px solid var(--border)",
        background: "var(--bg-deep)",
        overflow: "hidden",
        height: 30,
        display: "flex",
        alignItems: "center",
        position: "relative",
        zIndex: 40,
      }}
    >
      {/* LIVE badge */}
      <span
        className="mono"
        style={{
          flexShrink: 0, padding: "0 14px", height: "100%",
          display: "flex", alignItems: "center",
          fontSize: 10, letterSpacing: "0.12em",
          color: "var(--bg)", background: "var(--iris)",
          fontWeight: 700, position: "relative", zIndex: 2, whiteSpace: "nowrap",
        }}
      >
        LIVE FEED
      </span>

      <div style={{ overflow: "hidden", flex: 1, display: "flex", alignItems: "center" }}>
        <div className="ticker-track" style={{ animationDuration: "200s" }}>
          {doubled.map((it, i) => (
            <span
              key={i}
              className="mono"
              style={{
                fontSize: 11, padding: "0 28px",
                display: "inline-flex", alignItems: "center", gap: 10,
                borderRight: "1px solid var(--border)",
              }}
              >
              {/* BREAKING badge for high-score items */}
              {it.breaking && (
                <span style={{
                  fontSize: 8.5, fontWeight: 700, letterSpacing: "0.1em",
                  color: "var(--bg)", background: "var(--coral)",
                  padding: "2px 5px", lineHeight: 1,           
                  alignSelf: "center", flexShrink: 0,
                }}>
                  BREAKING
                </span>
              )}
              {/* Source label */}
              <span style={{ color: it.color, fontWeight: 700, letterSpacing: "0.08em", fontSize: 10 }}>
                {it.label}
              </span>
              {/* Separator */}
              <span style={{ color: "gray", fontSize: 10 }}>{">"}</span>
              {/* Headline */}
              <span style={{ color: "var(--text-2)", letterSpacing: "0.01em" }}>
                {it.title}
              </span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Search palette ── */
type SearchItem = { kind: string; title: string; href: string; hue: string; meta: string };

function SearchPalette({ open, onClose, allData }: {
  open: boolean; onClose: () => void;
  allData: { papers: Paper[]; news: NewsArticle[]; tools: Tool[]; benchmarks: Benchmark[]; talks: Talk[] };
}) {
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!open) return null;

  const corpus: SearchItem[] = [
    ...allData.papers.map((p) => ({ kind: "Paper", title: p.title, href: p.source_url, hue: "var(--coral)", meta: p.first_author || "" })),
    ...allData.news.map((n)   => ({ kind: "News",  title: n.title, href: n.url,        hue: "var(--azure)", meta: n.source_display_name })),
    ...allData.tools.map((t)  => ({ kind: "Tool",  title: t.name,  href: t.url,        hue: "var(--mint)",  meta: t.author || ""  })),
    ...allData.benchmarks.map((b) => ({ kind: "Model",  title: b.model_display_name, href: b.hf_url || "#", hue: "var(--amber)", meta: b.organisation || "" })),
    ...allData.talks.map((t)  => ({ kind: "Talk",  title: t.title, href: t.video_url,  hue: "var(--iris)",  meta: t.channel })),
  ];

  const ql = q.toLowerCase();
  const results = ql.length >= 2
    ? corpus.filter((c) => (c.title + " " + c.meta).toLowerCase().includes(ql)).slice(0, 8)
    : [];
  const suggestions = ["reasoning", "agents", "Anthropic", "open source", "benchmarks", "robotics"];

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(5,4,9,0.75)", backdropFilter: "blur(6px)", display: "flex", justifyContent: "center", paddingTop: "12vh", animation: "fadeIn .15s ease" }}>
      <div onClick={(e) => e.stopPropagation()} className="rise" style={{ width: "min(620px, 92vw)", height: "fit-content", background: "var(--bg-card)", border: "1px solid var(--border-lt)", boxShadow: "0 30px 90px -20px rgba(0,0,0,0.9)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 20px", borderBottom: "1px solid var(--border)" }}>
          <span style={{ color: "var(--iris)", fontSize: 18 }}>⌕</span>
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Search papers, news, tools, models, talks…"
            style={{ flex: 1, background: "none", border: "none", outline: "none", color: "var(--text)", fontFamily: "var(--sans)", fontSize: 16 }} />
          <span className="mono" style={{ fontSize: 9, color: "var(--text-dim)", border: "1px solid var(--border-lt)", padding: "2px 6px" }}>ESC</span>
        </div>
        <div style={{ maxHeight: "52vh", overflowY: "auto" }}>
          {!q && (
            <div style={{ padding: "18px 20px" }}>
              <div className="flabel" style={{ marginBottom: 12 }}>Try searching</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {suggestions.map((s) => <button key={s} className="tag" onClick={() => setQ(s)} style={{ cursor: "pointer" }}>{s}</button>)}
              </div>
            </div>
          )}
          {q && results.length === 0 && (
            <div className="mono" style={{ padding: "30px 20px", textAlign: "center", color: "var(--text-mut)", fontSize: 12.5 }}>No matches for "{q}".</div>
          )}
          {results.map((r, i) => (
            <a key={i} href={r.href} target="_blank" rel="noopener noreferrer" onClick={onClose}
              className="search-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", padding: "13px 20px", borderBottom: "1px solid var(--border)", textAlign: "left", gap: 14, transition: "background .12s ease" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 13.5, color: "var(--text)", marginBottom: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.title}</div>
                <div className="mono" style={{ fontSize: 10.5, color: "var(--text-mut)" }}>{r.meta}</div>
              </div>
              <span className="mono" style={{ fontSize: 9, color: r.hue, border: `1px solid ${r.hue}44`, padding: "2px 7px", flexShrink: 0, letterSpacing: "0.06em", textTransform: "uppercase" as const }}>{r.kind}</span>
            </a>
          ))}
        </div>
        {q && results.length > 0 && (
          <div className="mono" style={{ padding: "10px 20px", fontSize: 10, color: "var(--text-dim)", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "space-between" }}>
            <span>{results.length} result{results.length === 1 ? "" : "s"}</span>
            <span>click to open source</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Footer ── */
export function Footer() {
  return (
    <footer style={{ borderTop: "1px solid var(--border)", marginTop: 40, padding: "40px 0 60px" }}>
      <div className="shell" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <RadarMark />
          <div>
            <div className="serif" style={{ fontSize: 17, color: "var(--text)" }}>AI Radar</div>
            <div className="mono" style={{ fontSize: 9.5, color: "var(--text-mut)", letterSpacing: "0.1em" }}>THE SIGNAL DESK · EST. 2026</div>
          </div>
        </div>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--text-dim)", textAlign: "right", lineHeight: 1.7 }}>
          Pipeline runs daily at 07:00 UTC<br />
          <span style={{ color: "var(--text-mut)" }}>Sources read so you don't have to.</span>
        </div>
      </div>
    </footer>
  );
}

/* ── Main Navigation ── */
export function Navigation() {
  const path   = usePathname();
  const router = useRouter();
  const [status,  setStatus]  = useState<StatusData | null>(null);
  const [search,  setSearch]  = useState(false);
  const [allData, setAllData] = useState<{ papers: Paper[]; news: NewsArticle[]; tools: Tool[]; benchmarks: Benchmark[]; talks: Talk[] }>({ papers: [], news: [], tools: [], benchmarks: [], talks: [] });
  const [mobileOpen, setMobileOpen] = useState(false);

  const total = status ? Object.values(status).reduce((a, s) => a + s.summarised, 0) : 0;

  const [tickerItems, setTickerItems] = useState<{ label: string; title: string; color: string; breaking: boolean }[]>([]);

  const SOURCE_LABEL: Record<string, { label: string; color: string }> = {
    anthropic:        { label: "ANTHROPIC",  color: "#D69A6B" },
    openai:           { label: "OPENAI",     color: "#5FE3B0" },
    google_deepmind:  { label: "DEEPMIND",   color: "#6FB0FF" },
    meta_ai:          { label: "META AI",    color: "#6FB0FF" },
    tldr_ai:          { label: "TLDR",       color: "#F6B84E" },
    techcrunch_ai:    { label: "TECHCRUNCH", color: "#FF7A8A" },
    import_ai:        { label: "IMPORT AI",  color: "#B69CFF" },
    arxiv:            { label: "PAPER",      color: "#FF7A8A" },
    hf_daily_papers:  { label: "HF PAPER",   color: "#F6B84E" },
    openreview:       { label: "PAPER",      color: "#6FB0FF" },
    github_trending:  { label: "GITHUB",     color: "#EDE9F5" },
    hf_hub_model:     { label: "HF MODEL",   color: "#F6B84E" },
    product_hunt:     { label: "PRODUCT",    color: "#FF7A8A" },
  };

  useEffect(() => {
    Promise.all([
      api.news("limit=10&sort_by=significance_score"),
      api.papers("limit=6&sort_by=relevance_score"),
      api.tools("limit=5&sort_by=significance_score"),
    ]).then(([n, p, t]) => {
      const items = [
        ...n.data.map((a) => ({
          label:    SOURCE_LABEL[a.source]?.label   || a.source_display_name.toUpperCase(),
          color:    SOURCE_LABEL[a.source]?.color   || "var(--azure)",
          title:    a.title.length > 80 ? a.title.slice(0, 77) + "…" : a.title,
          breaking: (a.significance_score ?? 0) >= 8,
        })),
        ...p.data.map((pp) => ({
          label:    SOURCE_LABEL[pp.source]?.label  || "PAPER",
          color:    SOURCE_LABEL[pp.source]?.color  || "var(--coral)",
          title:    pp.title.length > 80 ? pp.title.slice(0, 77) + "…" : pp.title,
          breaking: (pp.relevance_score ?? 0) >= 8,
        })),
        ...t.data.map((tool) => ({
          label:    SOURCE_LABEL[tool.source]?.label || "TOOL",
          color:    SOURCE_LABEL[tool.source]?.color || "var(--mint)",
          title:    tool.name + (tool.why_trending ? " — " + tool.why_trending.slice(0, 55) + "…" : ""),
          breaking: false,
        })),
      ];
      setTickerItems(items);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
  }, []);

  // Pre-load data for search when search opens
  useEffect(() => {
    if (!search || allData.papers.length > 0) return;
    Promise.all([
      api.papers("limit=50&sort_by=fetched_at"),
      api.news("limit=50&sort_by=fetched_at"),
      api.tools("limit=50&sort_by=fetched_at"),
      api.benchmarks("limit=50&sort_by=fetched_at"),
      api.talks("limit=50&sort_by=fetched_at"),
    ]).then(([p, n, t, b, tk]) => {
      setAllData({ papers: p.data, news: n.data, tools: t.data, benchmarks: b.data, talks: tk.data });
    }).catch(() => {});
  }, [search]);

  // Cmd+K shortcut
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch((s) => !s); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const isActive = (href: string) => href === "/" ? path === "/" : path.startsWith(href);

  return (
    <>
      <Ticker items={tickerItems} />
      <nav style={{ position: "sticky", top: 0, zIndex: 50, background: "rgba(10,8,16,0.88)", backdropFilter: "blur(16px)", borderBottom: "1px solid var(--border)" }}>
        <div className="shell" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: 62, gap: 20 }}>

          {/* Logo */}
          <button onClick={() => router.push("/")} style={{ display: "flex", alignItems: "center", gap: 11, background: "none", border: "none", cursor: "pointer" }}>
            <RadarMark />
            <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", lineHeight: 1 }}>
              <span className="serif" style={{ fontSize: 21, letterSpacing: "-0.01em", color: "var(--text)" }}>AI&nbsp;Radar</span>
              <span className="mono" style={{ fontSize: 8.5, letterSpacing: "0.18em", color: "var(--text-mut)", marginTop: 2 }}>
                <AnimatedNumber value={total} /> INDEXED
              </span>
            </span>
          </button>

          {/* Desktop nav */}
          <div className="nav-desktop" style={{ gap: 26 }}>
            {NAV.map((n) => (
              <button key={n.href} onClick={() => router.push(n.href)}
                className={cx("nav-link", isActive(n.href) && "on")}>
                {n.label}
              </button>
            ))}
          </div>

          {/* Search + mobile burger */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button onClick={() => setSearch(true)} className="search-trigger flex" style={{
              alignItems: "center", gap: 10, padding: "8px 12px",
              border: "1px solid var(--border)", background: "var(--bg-panel)",
              color: "var(--text-mut)", fontFamily: "var(--mono)", fontSize: 11.5, minWidth: 180, justifyContent: "space-between",
            }}>
              <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ color: "var(--iris)" }}>⌕</span> Search the desk…
              </span>
              <span style={{ border: "1px solid var(--border-lt)", padding: "1px 5px", fontSize: 9, color: "var(--text-dim)" }}>CTRL K</span>
            </button>
            <button className="nav-burger" onClick={() => setMobileOpen((x) => !x)} style={{ color: "var(--iris)", fontSize: 18, background: "none", border: "none" }}>⌕</button>
          </div>
        </div>

        {/* Mobile menu */}
        <div className="nav-mobile" style={{ borderTop: "1px solid var(--border)", overflowX: "auto" }}>
          <div style={{ display: "flex", padding: "0 16px", gap: 20 }}>
            {NAV.map((n) => (
              <button key={n.href} onClick={() => { router.push(n.href); setMobileOpen(false); }}
                className={cx("nav-link", isActive(n.href) && "on")} style={{ padding: "12px 0", whiteSpace: "nowrap" }}>
                {n.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      <SearchPalette open={search} onClose={() => setSearch(false)} allData={allData} />
    </>
  );
}

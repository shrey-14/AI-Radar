"use client";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { Digest, Status } from "@/lib/api";
import {
  PaperCard, NewsCard, ToolCard, BenchmarkCard, TalkCard,
  AnimatedNumber, Reveal, BulletField, TagList, SourceBadge, ScoreBadge,
} from "@/components/ui";

/* ── Ordinal helper ── */
function ordinal(n: number): string {
  const s = ["th","st","nd","rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}
function todayWords(): string {
  const d = new Date();
  const day   = ordinal(d.getDate());
  const month = d.toLocaleDateString("en-GB", { month: "long" });
  const year  = d.getFullYear();
  return `on ${day} ${month} ${year}`;
}

/* ── Typewriter ── */
function Typewriter({ words, type = 130, erase = 70, hold = 1500, gap = 350 }:
  { words: string[]; type?: number; erase?: number; hold?: number; gap?: number }) {
  const [idx,   setIdx]   = useState(0);
  const [text,  setText]  = useState("");
  const [phase, setPhase] = useState<"typing"|"holding"|"erasing"|"gap">("typing");

  useEffect(() => {
    const word = words[idx % words.length];
    let t: ReturnType<typeof setTimeout>;
    if (phase === "typing") {
      if (text.length < word.length)
        t = setTimeout(() => setText(word.slice(0, text.length + 1)), type);
      else
        t = setTimeout(() => setPhase("holding"), 0);
    } else if (phase === "holding") {
      t = setTimeout(() => setPhase("erasing"), hold);
    } else if (phase === "erasing") {
      if (text.length > 0)
        t = setTimeout(() => setText(word.slice(0, text.length - 1)), erase);
      else
        t = setTimeout(() => setPhase("gap"), 0);
    } else if (phase === "gap") {
      t = setTimeout(() => { setIdx((i) => i + 1); setPhase("typing"); }, gap);
    }
    return () => clearTimeout(t);
  }, [text, phase, idx, words, type, erase, hold, gap]);

  return (
    <span style={{ fontStyle: "italic", color: "var(--iris)", whiteSpace: "nowrap" }}>
      {text}<span className="type-caret" aria-hidden="true">|</span>
    </span>
  );
}

/* ── Section shell ── */
function SectionShell({ index, title, sub, count, children, accent = "var(--iris)" }:
  { index: string; title: string; sub: string; count: number; children: React.ReactNode; accent?: string }) {
  return (
    <section style={{ marginBottom: 64 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, paddingBottom: 14, marginBottom: 22, borderBottom: "1px solid var(--border)", flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <span className="mono" style={{ fontSize: 12, color: accent, fontWeight: 600, letterSpacing: "0.1em" }}>§{index}</span>
          <h2 className="serif" style={{ fontSize: "clamp(30px,4vw,42px)", fontWeight: 400, letterSpacing: "-0.015em", lineHeight: 1, color: "var(--text)", whiteSpace: "nowrap" }}>{title}</h2>
          <span className="eyebrow" style={{ alignSelf: "flex-end", paddingBottom: 5 }}>{sub}</span>
        </div>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-mut)", whiteSpace: "nowrap" }}>
          <span style={{ color: accent }}>{count}</span> today
        </span>
      </div>
      {children}
    </section>
  );
}

/* ── See all link ── */
function SeeAllLink({ href, label, labelStyle }: { href: string; label: string; labelStyle?: React.CSSProperties }) {
  return (
    <a href={href} className="see-all" style={{
      display: "block", marginTop: 22, width: "100%", padding: "14px",
      border: "1px dashed var(--border-lt)", background: "transparent",
      color: "var(--text-mut)", fontFamily: "var(--mono)", fontSize: 11.5,
      letterSpacing: "0.08em", textTransform: "uppercase", textAlign: "center",
      transition: "all .2s ease", ...labelStyle,
    }}>
      {label} <span style={{ color: "var(--iris)" }}>→</span>
    </a>
  );
}

/* ── Lead story ── */
function LeadStory({ article: a }: { article: NonNullable<Digest["news"]>[0] }) {
  return (
    <Reveal className="card" style={{ overflow: "hidden" }}>
      <div className="lead-story">
        <div style={{ padding: 30, borderRight: "1px solid var(--border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 7 }}>
              <span className="tag tag-iris" style={{ letterSpacing: "0.08em" }}>★ TOP STORY</span>
              <SourceBadge source={a.source} strong />
              {a.category && <span className="tag">{a.category.replace(/_/g, " ")}</span>}
            </div>
            <ScoreBadge score={a.significance_score} type="significance" size="lg" />
          </div>
          <h2 className="serif" style={{ fontSize: "clamp(34px,4.4vw,56px)", fontWeight: 400, lineHeight: 1.0, letterSpacing: "-0.02em", marginBottom: 20, color: "var(--text)" }}>
            {a.title}
          </h2>
          <p style={{ fontSize: 16.5, color: "var(--text-2)", lineHeight: 1.62, marginBottom: 22 }}>{a.summary}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 24 }}>
            {a.companies_mentioned.length > 0 && (
              <div><div className="flabel" style={{ marginBottom: 7 }}>Companies</div><TagList tags={a.companies_mentioned} /></div>
            )}
            {a.models_mentioned.length > 0 && (
              <div><div className="flabel" style={{ marginBottom: 7 }}>Models</div><TagList tags={a.models_mentioned} variant="azure" /></div>
            )}
          </div>
        </div>
        <div style={{ padding: 30, background: "var(--bg-panel)", display: "flex", flexDirection: "column" }}>
          <BulletField label="What you need to know" items={a.key_points} mb={20} />
          <div style={{ marginTop: "auto" }}>
            <hr className="rule" style={{ marginBottom: 16 }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <TagList tags={a.ai_tags} variant="iris" />
              <a href={a.url} target="_blank" rel="noopener noreferrer" className="mono"
                style={{ fontSize: 11, color: "var(--iris)", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>
                READ SOURCE →
              </a>
            </div>
          </div>
        </div>
      </div>
    </Reveal>
  );
}

/* ── Skeleton strip ── */
function Skel({ w, h }: { w: string; h: number }) {
  return <div className="skel" style={{ width: w, height: h, marginBottom: 8 }} />;
}

/* ══════════════════════════════════════════════ */
export default function HomePage() {
  const [digest,  setDigest]  = useState<Digest  | null>(null);
  const [status,  setStatus]  = useState<Status  | null>(null);
  const [loading, setLoading] = useState(true);

  const WORDS = ["today", todayWords()];
  const keys  = ["papers","news","tools","benchmarks","talks"] as const;

  useEffect(() => {
    Promise.all([api.digest(), api.status()])
      .then(([d, s]) => { setDigest(d); setStatus(s); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);


  return (
    <div className="shell">

      {/* ── Hero ── */}
      <header style={{ paddingTop: 44, marginBottom: 30 }}>
        <Reveal style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16, marginBottom: 26, paddingBottom: 16, borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span className="eyebrow" style={{ fontSize: "clamp(11px, 2vw, 13px)" }}>Daily Intelligence Briefing</span>
            {/* <span style={{ width: 4, height: 4, borderRadius: "50%", background: "var(--iris)" }} />
            <span className="mono" style={{ fontSize: 11, color: "var(--text-2)" }}>
              {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
            </span> */}
          </div>
        </Reveal>

        <Reveal i={1}>
          <h1 className="serif" style={{
            fontSize: "clamp(46px, 8vw, 104px)", fontWeight: 400, lineHeight: 0.94,
            letterSpacing: "-0.02em", marginBottom: 22, color: "var(--text)",
          }}>
            What actually matters<br />in AI{" "}
            <Typewriter words={WORDS} type={110} erase={60} hold={1800} gap={400} />
          </h1>
          <p style={{ fontSize: "clamp(15px,2.2vw,19px)", color: "var(--text-2)", lineHeight: 1.55, maxWidth: "60ch" }}>
            Every day, the desk scrapes, reads, and scores the entire AI frontier —{" "}
            <span style={{ color: "var(--text)" }}>papers, news, tools, benchmarks, and talks</span> —
            so you read five things that matter instead of fifty that don't.
          </p>
        </Reveal>
      </header>

      {/* ── Pipeline strip ── */}
      {status ? (
        <Reveal i={1} className="card" style={{ padding: 0, display: "flex", flexWrap: "wrap", alignItems: "stretch", marginBottom: 56 }}>
          <div style={{ padding: "16px 22px", borderRight: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 12 }}>
            <span className="live-dot" />
            <div>
              <div className="kicker" style={{ marginBottom: 2, fontSize: "clamp(10px, 2vw, 12px)" }}>Pipeline</div>
              <div className="mono" style={{ fontSize: 13, color: "var(--mint)", fontWeight: 600 }}>OPERATIONAL</div>
            </div>
          </div>
          {keys.map((k, i) => {
            const s = status[k];
            const pct = s.total > 0 ? s.summarised / s.total : 0;
            return (
              <div key={k} style={{ flex: "1 1 130px", padding: "14px 20px", borderRight: i < keys.length - 1 ? "1px solid var(--border)" : "none" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
                  <span className="kicker" style={{ fontSize: "clamp(10px, 2vw, 12px)" }}>{k}</span>
                  {s.pending > 0
                    ? <span className="mono" style={{ fontSize: 9, color: "var(--amber)", fontStyle: "clamp(10px, 2vw, 12px) !important" }}>{s.pending}↻</span>
                    : <span className="mono" style={{ fontSize: 9, color: "var(--mint)", fontStyle: "clamp(10px, 2vw, 12px) !important" }}>✓</span>}
                </div>
                <div className="mono" style={{ fontSize: 17, fontWeight: 600, color: "var(--text)", marginBottom: 6 }}>
                  <AnimatedNumber value={s.summarised} />
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}> / {s.total}</span>
                </div>
                <span className="meter-track" style={{ display: "block" }}>
                  <span className="meter-fill" style={{ width: `${pct * 100}%`, background: "var(--iris)" }} />
                </span>
              </div>
            );
          })}
          <div style={{ padding: "14px 22px", display: "flex", flexDirection: "column", justifyContent: "center", background: "var(--bg-panel)" }}>
            <div className="kicker" style={{ marginBottom: 2, fontSize: "clamp(10px, 2vw, 12px)" }}>Total Indexed</div>
            <div className="mono" style={{ fontSize: 17, fontWeight: 700, color: "var(--iris)" }}>
              <AnimatedNumber value={keys.reduce((a, k) => a + (status[k]?.summarised || 0), 0)} />
            </div>
          </div>
        </Reveal>
      ) : (
        <div className="card" style={{ padding: 20, marginBottom: 56, display: "flex", gap: 20 }}>
          {[...Array(6)].map((_, i) => <Skel key={i} w="120px" h={48} />)}
        </div>
      )}

      {/* ── API error state ── */}
      {!loading && !digest && (
        <div style={{ padding: "80px 24px", textAlign: "center" }}>
          <div className="mono" style={{ fontSize: 30, color: "var(--text-dim)", marginBottom: 14 }}>∅</div>
          <p className="mono" style={{ fontSize: 12.5, color: "var(--text-mut)" }}>
            The Signal Desk is temporarily unavailable. Please try again in a moment.
          </p>
        </div>
      )}

      {/* ── Loading skeletons ── */}
      {loading && (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {[...Array(3)].map((_, i) => (
            <div key={i}>
              <Skel w="40%" h={22} />
              <div className="grid-2" style={{ marginTop: 16 }}>
                {[...Array(2)].map((_, j) => (
                  <div key={j} className="card" style={{ padding: 20 }}>
                    <Skel w="35%" h={16} /><Skel w="80%" h={20} /><Skel w="100%" h={60} /><Skel w="55%" h={14} />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Content ── */}
      {digest && (
        <>
          {/* Lead Story */}
          {digest.news[0] && (
            <section style={{ marginBottom: 64 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18 }}>
                <span className="live-dot" />
                <span className="eyebrow" style={{ color: "var(--iris)", fontSize: "clamp(11px, 2vw, 13px)" }}>Leading the desk</span>
                <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
              </div>
              <LeadStory article={digest.news[0]} />
            </section>
          )}

          {/* Papers */}
          {digest.papers.length > 0 && (
            <SectionShell index="01" title="Research Papers" sub="arXiv · HF Daily · OpenReview" count={digest.papers.length}>
              {digest.papers[0] && (
                <div style={{ marginBottom: 20 }}>
                  <PaperCard paper={digest.papers[0]} feature i={0} />
                </div>
              )}
              {digest.papers.length > 1 && (
                <div className="grid-2">
                  {digest.papers.slice(1).map((p, i) => <PaperCard key={p.id} paper={p} i={i} />)}
                </div>
              )}
              <SeeAllLink href="/papers" label="All research papers" labelStyle={{ fontSize: "clamp(11px, 2vw, 13px)" }} />
            </SectionShell>
          )}

          {/* News */}
          {digest.news.length > 1 && (
            <SectionShell index="02" title="Industry News" sub="7 sources" count={digest.news.length} accent="var(--azure)">
              <div className="grid-2">
                {digest.news.slice(1).map((n, i) => <NewsCard key={n.id} article={n} i={i} />)}
              </div>
              <SeeAllLink href="/news" label="All news" labelStyle={{ fontSize: "clamp(11px, 2vw, 13px)" }} />
            </SectionShell>
          )}

          {/* Tools */}
          {digest.tools.length > 0 && (
            <SectionShell index="03" title="Tools & Releases" sub="GitHub · HF · Product Hunt" count={digest.tools.length} accent="var(--mint)">
              <div className="grid-2">
                {digest.tools.map((t, i) => <ToolCard key={t.id} tool={t} i={i} />)}
              </div>
              <SeeAllLink href="/tools" label="All tools" labelStyle={{ fontSize: "clamp(11px, 2vw, 13px)" }} />
            </SectionShell>
          )}

          {/* Benchmarks */}
          {digest.benchmarks.length > 0 && (
            <SectionShell index="04" title="Benchmarks" sub="Open LLM · Arena · Artificial Analysis" count={digest.benchmarks.length} accent="var(--amber)">
              <div className="grid-3">
                {digest.benchmarks.map((b, i) => <BenchmarkCard key={b.id} bench={b} i={i} />)}
              </div>
              <SeeAllLink href="/benchmarks" label="Full leaderboards" labelStyle={{ fontSize: "clamp(11px, 2vw, 13px)" }} />
            </SectionShell>
          )}

          {/* Talks */}
          {digest.talks.length > 0 && (
            <SectionShell index="05" title="Talks & Explainers" sub="Lex · Yannic · 2MP · AI Explained" count={digest.talks.length} accent="var(--coral)">
              <div className="lead-grid">
                <TalkCard talk={digest.talks[0]} feature i={0} />
                <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                  {digest.talks.slice(1, 3).map((t, i) => <TalkCard key={t.id} talk={t} i={i + 1} />)}
                </div>
              </div>
              <SeeAllLink href="/talks" label="All talks" labelStyle={{ fontSize: "clamp(11px, 2vw, 13px)" }} />
            </SectionShell>
          )}
        </>
      )}
    </div>
  );
}
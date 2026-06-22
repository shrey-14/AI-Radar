"use client";
import { useState, useRef, useEffect } from "react";
import { api, AskResponse, AskSource } from "@/lib/api";
import { Reveal, EmptyState, cx } from "@/components/ui";

/* ── Section metadata — matches Navigation.tsx / ui.tsx hue conventions ── */
const SECTION_META: Record<string, { label: string; hue: string; href: string }> = {
  papers:     { label: "PAPER",     hue: "var(--coral)", href: "/papers" },
  news:       { label: "NEWS",      hue: "var(--azure)", href: "/news" },
  tools:      { label: "TOOL",      hue: "var(--mint)",  href: "/tools" },
  benchmarks: { label: "BENCHMARK", hue: "var(--amber)", href: "/benchmarks" },
  talks:      { label: "TALK",      hue: "var(--iris)",  href: "/talks" },
};

const SAMPLE_QUERIES = [
  "What's the cheapest model that still performs well?",
  "What has Anthropic announced recently?",
  "Which papers discuss AI agents using tools?",
  "What's trending for fine-tuning right now?",
];

type ChatTurn = {
  query: string;
  response?: AskResponse;
  error?: string;
  loading: boolean;
};

/* ── Citation chip — renders inline [PAPERS 1] markers as styled badges ── */
function renderAnswerWithCitations(text: string, sources: AskSource[]) {
  // Matches [PAPERS 1], [NEWS 3], [BENCHMARKS 2] etc — case-insensitive, tolerant of stray whitespace
  const pattern = /\[([A-Z]+)\s*(\d+)\]/gi;
  const parts: (string | { section: string; idx: number; key: string })[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let i = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push({ section: match[1].toLowerCase(), idx: Number(match[2]), key: `cite-${i++}` });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));

  return parts.map((p, k) => {
    if (typeof p === "string") return <span key={k}>{p}</span>;
    const src = sources.find((s) => s.section === p.section && s.index === p.idx);
    const meta = SECTION_META[p.section];
    if (!src || !meta) return <span key={k}>{`[${p.section.toUpperCase()} ${p.idx}]`}</span>;
    return (
      <a
        key={p.key}
        href={src.url || meta.href}
        target="_blank"
        rel="noopener noreferrer"
        className="mono"
        style={{
          display: "inline-flex", alignItems: "center", gap: 3,
          fontSize: 10, fontWeight: 700, letterSpacing: "0.04em",
          color: meta.hue, border: `1px solid ${meta.hue}44`, background: meta.hue + "14",
          padding: "1px 6px", margin: "0 2px", verticalAlign: "middle",
          textDecoration: "none", whiteSpace: "nowrap",
        }}
        title={src.title}
      >
        {meta.label} {p.idx}
      </a>
    );
  });
}

/* ── Source card — shown below each answer ── */
function SourceCard({ source }: { source: AskSource }) {
  const meta = SECTION_META[source.section] || { label: source.section.toUpperCase(), hue: "var(--text-mut)", href: "#" };
  return (
    <a
      href={source.url || meta.href}
      target="_blank"
      rel="noopener noreferrer"
      className="card"
      style={{
        display: "flex", flexDirection: "column", gap: 8, padding: "14px 16px",
        textDecoration: "none", minWidth: 0,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span
          className="mono"
          style={{
            fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
            color: meta.hue, border: `1px solid ${meta.hue}44`, background: meta.hue + "14",
            padding: "2px 7px", flexShrink: 0,
          }}
        >
          {meta.label} {source.index}
        </span>
        <span className="mono" style={{ fontSize: 10, color: "var(--text-dim)", flexShrink: 0 }}>
          {(source.similarity * 100).toFixed(0)}% match
        </span>
      </div>
      <div style={{
        fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.45,
        overflow: "hidden", textOverflow: "ellipsis", display: "-webkit-box",
        WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const,
      }}>
        {source.title}
      </div>
    </a>
  );
}

/* ── Loading indicator — matches radar-sweep / pulse vocabulary ── */
function ThinkingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "4px 0" }}>
      <span className="live-dot" />
      <span className="mono" style={{ fontSize: 11.5, color: "var(--text-mut)", letterSpacing: "0.04em" }}>
        Scanning the desk
        <span className="type-caret" />
      </span>
    </div>
  );
}

/* ── Section pills under each routed query ── */
function SectionPills({ sections }: { sections: string[] }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {sections.map((s) => {
        const meta = SECTION_META[s];
        if (!meta) return null;
        return (
          <span
            key={s}
            className="mono"
            style={{
              fontSize: 9.5, fontWeight: 600, letterSpacing: "0.06em",
              color: meta.hue, border: `1px solid ${meta.hue}33`,
              padding: "2px 8px",
            }}
          >
            {meta.label}S
          </span>
        );
      })}
    </div>
  );
}

export default function AskPage() {
  const [input, setInput]   = useState("");
  const [turns, setTurns]   = useState<ChatTurn[]>([]);
  const inputRef            = useRef<HTMLTextAreaElement>(null);
  const bottomRef            = useRef<HTMLDivElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns]);

  async function submit(q: string) {
    const query = q.trim();
    if (!query) return;
    setInput("");

    const turnIndex = turns.length;
    setTurns((t) => [...t, { query, loading: true }]);

    try {
      const response = await api.ask(query);
      setTurns((t) => {
        const next = [...t];
        next[turnIndex] = { query, response, loading: false };
        return next;
      });
    } catch (e) {
      setTurns((t) => {
        const next = [...t];
        next[turnIndex] = { query, error: "Couldn't reach the desk. Try again in a moment.", loading: false };
        return next;
      });
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  const hasConversation = turns.length > 0;

  return (
    <div className="shell" style={{ paddingTop: 40, paddingBottom: 60, display: "flex", flexDirection: "column", minHeight: "calc(100vh - 140px)" }}>

      {/* ── Header — matches §0N section convention from other pages ── */}
      <div style={{ marginBottom: 26 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12, color: "var(--iris)", fontWeight: 600, letterSpacing: "0.1em" }}>§06</span>
          <span className="eyebrow">Retrieval-Augmented · Grounded in today's signal</span>
        </div>
        <div style={{ borderBottom: "1px solid var(--border)", paddingBottom: 20 }}>
          <h1 className="serif" style={{ fontSize: "clamp(40px,7vw,72px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 0.95, color: "var(--text)" }}>
            Ask the Desk
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-mut)", marginTop: 12, maxWidth: 560, lineHeight: 1.6 }}>
            Ask anything about today's papers, news, tools, benchmarks, or talks.
            Every answer is grounded in what's actually been indexed — no outside guessing.
          </p>
        </div>
      </div>

      {/* ── Empty state: sample queries ── */}
      {!hasConversation && (
        <Reveal style={{ marginBottom: 32 }}>
          <div className="flabel" style={{ marginBottom: 12 }}>Try asking</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 9 }}>
            {SAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => submit(q)}
                className="tag"
                style={{ cursor: "pointer", fontSize: 12.5, padding: "8px 14px" }}
              >
                {q}
              </button>
            ))}
          </div>
        </Reveal>
      )}

      {/* ── Conversation ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 28 }}>
        {turns.map((turn, i) => (
          <Reveal key={i} i={Math.min(i, 4)}>
            {/* User query */}
            <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--iris)", fontWeight: 700, flexShrink: 0, paddingTop: 2 }}>
                ASK
              </span>
              <p style={{ fontSize: 16, color: "var(--text)", lineHeight: 1.5, fontFamily: "var(--sans)" }}>
                {turn.query}
              </p>
            </div>

            {/* Response */}
            <div style={{ display: "flex", gap: 12 }}>
              <span className="mono" style={{ fontSize: 11, color: "var(--mint)", fontWeight: 700, flexShrink: 0, paddingTop: 2 }}>
                DESK
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                {turn.loading && <ThinkingIndicator />}

                {turn.error && (
                  <p className="mono" style={{ fontSize: 12.5, color: "var(--coral)" }}>{turn.error}</p>
                )}

                {turn.response && (
                  <>
                    {turn.response.sources.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <SectionPills sections={turn.response.sections_queried} />
                      </div>
                    )}

                    <div style={{ fontSize: 14.5, color: "var(--text-2)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                      {renderAnswerWithCitations(turn.response.answer, turn.response.sources)}
                    </div>

                    {turn.response.sources.length > 0 ? (
                      <div style={{ marginTop: 18 }}>
                        <div className="flabel" style={{ marginBottom: 10 }}>Sources</div>
                        <div style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                          gap: 10,
                        }}>
                          {turn.response.sources.map((s) => (
                            <SourceCard key={`${s.section}-${s.index}`} source={s} />
                          ))}
                        </div>
                      </div>
                    ) : (
                      <EmptyState message="No matching records found. Try rephrasing." />
                    )}

                    <div className="mono" style={{ fontSize: 9.5, color: "var(--text-dim)", marginTop: 14 }}>
                      {turn.response.latency_ms}ms · {turn.response.sources.length} record{turn.response.sources.length === 1 ? "" : "s"} retrieved
                    </div>
                  </>
                )}
              </div>
            </div>
          </Reveal>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ── Input bar — sticky at bottom ── */}
      <div style={{
        position: "sticky", bottom: 0, marginTop: 32, paddingTop: 16,
        background: "linear-gradient(180deg, transparent, var(--bg) 30%)",
      }}>
        <div style={{
          display: "flex", alignItems: "flex-end", gap: 10,
          padding: "12px 14px", background: "var(--bg-panel)",
          border: "1px solid var(--border-lt)",
        }}>
          <span style={{ color: "var(--iris)", fontSize: 16, paddingBottom: 6, flexShrink: 0 }}>⌕</span>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about papers, news, tools, benchmarks, or talks…"
            rows={1}
            style={{
              flex: 1, background: "none", border: "none", outline: "none",
              color: "var(--text)", fontFamily: "var(--sans)", fontSize: 14.5,
              lineHeight: 1.5, resize: "none", maxHeight: 120, paddingTop: 6, paddingBottom: 6,
            }}
          />
          <button
            onClick={() => submit(input)}
            disabled={!input.trim()}
            className={cx("fpill", input.trim() && "on")}
            style={{
              flexShrink: 0, cursor: input.trim() ? "pointer" : "not-allowed",
              opacity: input.trim() ? 1 : 0.4,
            }}
          >
            Ask →
          </button>
        </div>
        <div className="mono" style={{ fontSize: 9.5, color: "var(--text-dim)", marginTop: 8, textAlign: "right" }}>
          Enter to ask · Shift+Enter for new line
        </div>
      </div>
    </div>
  );
}
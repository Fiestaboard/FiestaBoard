"use client";

import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * Chat-tuned markdown renderer for AI assistant messages.
 *
 * Differences from the plugin README renderer:
 * - Tighter vertical rhythm (chat panels are narrow + dense).
 * - Inline FiestaBoard tokens get highlighted: `{{plugin.var}}` renders
 *   as a brand-tinted chip and `{color}` color tokens render as a
 *   small swatch + label so the user can spot them in prose without
 *   parsing markdown noise.
 * - No margins on the first/last block so the message bubble keeps
 *   the AI message's own padding clean.
 */
export interface ChatMarkdownProps {
  children: string;
  className?: string;
}

// ---------------------------------------------------------------------------
// FiestaBoard-aware token highlighter
// ---------------------------------------------------------------------------

const VAR_RE = /\{\{\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)(?:\s*\|[^}]+)?\s*\}\}/g;
const COLOR_RE = /\{(red|orange|yellow|green|blue|violet|white|black|degree|sun|heart|moon|star)\}/g;

const COLOR_SWATCHES: Record<string, string> = {
  red: "var(--color-board-red, #eb4034)",
  orange: "var(--color-board-orange, #f5a623)",
  yellow: "var(--color-board-yellow, #f8e71c)",
  green: "var(--color-board-green, #7ed321)",
  blue: "var(--color-board-blue, #4a90d9)",
  violet: "var(--color-board-violet, #9b59b6)",
  white: "#ffffff",
  black: "#1a1a1a",
};

function VarChip({ plugin, field }: { plugin: string; field: string }) {
  return (
    <code
      className="inline-flex items-center rounded-md bg-brand-emphasis/15 px-1.5 py-0 font-mono text-[11px] text-brand-emphasis"
      title={`Plugin variable: ${plugin}.${field}`}
    >
      {`{{${plugin}.${field}}}`}
    </code>
  );
}

function ColorChip({ token }: { token: string }) {
  const swatch = COLOR_SWATCHES[token];
  return (
    <code
      className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-1.5 py-0 font-mono text-[11px]"
      title={`Color/symbol token: ${token}`}
    >
      {swatch && (
        <span
          aria-hidden
          className="inline-block h-2.5 w-2.5 rounded-sm border border-border/60"
          style={{ background: swatch }}
        />
      )}
      {`{${token}}`}
    </code>
  );
}

/**
 * Walk a string and replace `{{plugin.var}}` + `{color}` tokens with
 * highlighted React elements. Returns a flat array we can drop into
 * any markdown leaf renderer (paragraph, list item, table cell, …).
 *
 * `react-markdown` hands children to component renderers as either
 * strings or already-rendered React nodes (for nested markdown like
 * **bold**). We only transform raw strings — anything that's already
 * a node passes through untouched.
 */
function highlightTokens(children: React.ReactNode): React.ReactNode {
  if (typeof children === "string") {
    return splitWithTokens(children);
  }
  if (Array.isArray(children)) {
    return children.map((child, i) =>
      typeof child === "string" ? (
        <React.Fragment key={i}>{splitWithTokens(child)}</React.Fragment>
      ) : (
        child
      ),
    );
  }
  return children;
}

function splitWithTokens(text: string): React.ReactNode[] {
  // Combined tokenizer: walk through the string, emitting plain text
  // and chip nodes in source order. Two regexes makes the simplest
  // correct implementation — one pass against each, sorted by index.
  type Match =
    | { kind: "var"; start: number; end: number; plugin: string; field: string }
    | { kind: "color"; start: number; end: number; token: string };

  const matches: Match[] = [];
  for (const m of text.matchAll(VAR_RE)) {
    matches.push({
      kind: "var",
      start: m.index ?? 0,
      end: (m.index ?? 0) + m[0].length,
      plugin: m[1],
      field: m[2],
    });
  }
  for (const m of text.matchAll(COLOR_RE)) {
    matches.push({
      kind: "color",
      start: m.index ?? 0,
      end: (m.index ?? 0) + m[0].length,
      token: m[1],
    });
  }
  if (matches.length === 0) return [text];
  matches.sort((a, b) => a.start - b.start);

  const out: React.ReactNode[] = [];
  let cursor = 0;
  matches.forEach((match, i) => {
    if (match.start < cursor) return; // overlap — skip
    if (match.start > cursor) {
      out.push(text.slice(cursor, match.start));
    }
    if (match.kind === "var") {
      out.push(<VarChip key={`v${i}`} plugin={match.plugin} field={match.field} />);
    } else {
      out.push(<ColorChip key={`c${i}`} token={match.token} />);
    }
    cursor = match.end;
  });
  if (cursor < text.length) {
    out.push(text.slice(cursor));
  }
  return out;
}

// ---------------------------------------------------------------------------
// Renderer
// ---------------------------------------------------------------------------

export function ChatMarkdown({ children, className }: ChatMarkdownProps) {
  // The components map is stable per render; memoize to avoid React's
  // markdown reconciler re-creating component identities mid-stream.
  const components = useMemo(
    () =>
      ({
        p: ({ children, ...props }) => (
          <p className="text-sm leading-relaxed first:mt-0 last:mb-0 mb-2" {...props}>
            {highlightTokens(children)}
          </p>
        ),
        strong: ({ children, ...props }) => (
          <strong className="font-semibold text-foreground" {...props}>
            {highlightTokens(children)}
          </strong>
        ),
        em: ({ children, ...props }) => (
          <em className="italic" {...props}>
            {highlightTokens(children)}
          </em>
        ),
        h1: ({ children, ...props }) => (
          <h3 className="mt-3 mb-1.5 text-sm font-semibold first:mt-0" {...props}>
            {highlightTokens(children)}
          </h3>
        ),
        h2: ({ children, ...props }) => (
          <h3 className="mt-3 mb-1.5 text-sm font-semibold first:mt-0" {...props}>
            {highlightTokens(children)}
          </h3>
        ),
        h3: ({ children, ...props }) => (
          <h4
            className="mt-2.5 mb-1 text-[13px] font-semibold first:mt-0"
            {...props}
          >
            {highlightTokens(children)}
          </h4>
        ),
        h4: ({ children, ...props }) => (
          <h5
            className="mt-2 mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground first:mt-0"
            {...props}
          >
            {highlightTokens(children)}
          </h5>
        ),
        ul: ({ children, ...props }) => (
          <ul
            className="my-1 list-disc space-y-0.5 pl-5 text-sm leading-relaxed first:mt-0 last:mb-0"
            {...props}
          >
            {children}
          </ul>
        ),
        ol: ({ children, ...props }) => (
          <ol
            className="my-1 list-decimal space-y-0.5 pl-5 text-sm leading-relaxed first:mt-0 last:mb-0"
            {...props}
          >
            {children}
          </ol>
        ),
        li: ({ children, ...props }) => (
          <li {...props}>{highlightTokens(children)}</li>
        ),
        a: ({ href, children, ...props }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-emphasis underline decoration-brand-emphasis/40 underline-offset-2 hover:decoration-brand-emphasis"
            {...props}
          >
            {highlightTokens(children)}
          </a>
        ),
        code: ({ children, className, ...props }) => {
          // Block code (fenced) is wrapped in <pre> by react-markdown,
          // so this branch is the inline case. Treat the inline code
          // as raw text and run the FiestaBoard tokenizer over it so
          // ``{{plugin.var}}`` shows the same chip as in prose.
          const isBlock = className?.startsWith("language-");
          if (isBlock) {
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          }
          return (
            <code
              className="rounded-sm bg-muted px-1 py-0 font-mono text-[11px]"
              {...props}
            >
              {highlightTokens(children)}
            </code>
          );
        },
        pre: ({ children, ...props }) => (
          <pre
            className="my-2 overflow-x-auto rounded-md border bg-muted/40 p-2 text-[11px] first:mt-0 last:mb-0"
            {...props}
          >
            {children}
          </pre>
        ),
        blockquote: ({ children, ...props }) => (
          <blockquote
            className="my-2 border-l-2 border-brand-emphasis/40 pl-2.5 text-sm italic text-muted-foreground first:mt-0 last:mb-0"
            {...props}
          >
            {children}
          </blockquote>
        ),
        hr: () => <hr className="my-2 border-border/60" />,
        table: ({ children, ...props }) => (
          <div className="my-2 overflow-x-auto first:mt-0 last:mb-0">
            <table className="w-full border-collapse text-[11px]" {...props}>
              {children}
            </table>
          </div>
        ),
        thead: ({ children, ...props }) => (
          <thead className="bg-muted/40" {...props}>
            {children}
          </thead>
        ),
        th: ({ children, ...props }) => (
          <th
            className="border border-border/60 px-1.5 py-1 text-left font-medium"
            {...props}
          >
            {highlightTokens(children)}
          </th>
        ),
        td: ({ children, ...props }) => (
          <td className="border border-border/60 px-1.5 py-1" {...props}>
            {highlightTokens(children)}
          </td>
        ),
      }) satisfies React.ComponentProps<typeof ReactMarkdown>["components"],
    [],
  );

  return (
    <div className={cn("space-y-0", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

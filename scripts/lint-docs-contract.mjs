#!/usr/bin/env node
// Docs contract gate for the published Docusaurus site source (docs/**,
// excluding docs/internal/ which is never published).
//
// FiestaBoard no longer builds the site itself — docs/** is synced to
// Fiestaboard/fiestaboard.github.io, which builds and deploys
// fiestaboard.app. Without this gate, a malformed doc would only surface
// as a build failure two repos later. This script enforces, at the source,
// the contract the site build depends on:
//
//   1. Every _category_.json under docs/ parses as JSON, and every
//      directory that holds published pages has one (Docusaurus sidebar
//      metadata — every published directory carries one today).
//   2. No relative markdown link resolves to a path outside docs/. Such
//      links "work" on GitHub but 404 once published: the site repo only
//      receives docs/**, so ../ escapes point at files that don't exist
//      there. The site build itself only WARNS on broken markdown links
//      (onBrokenMarkdownLinks: 'warn'), so this gate is deliberately
//      stricter than the build.
//   3. No MDX-hostile syntax. The site compiles .md as MDX, where a bare
//      `<` starts JSX: `<` followed by a non-tag character is a compile
//      error, and an opened JSX/HTML tag that is never closed fails the
//      page. Code fences and inline code spans are exempt (MDX leaves
//      those alone). Heuristics are conservative: only constructs that
//      actually break `mdx` compilation are flagged.
//
// Frontmatter presence + required fields are enforced by the companion
// script lint-docs-frontmatter.mjs; this script adds a structural check
// that the frontmatter block is parseable YAML mapping shape (a stray
// non `key: value` line fails the site's gray-matter parse).
//
// Plain Node ESM — no dependencies, so it runs with a bare `node` in CI.

import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs'
import { join, relative, resolve, dirname, sep } from 'node:path'

const ROOT = process.cwd()
const DOCS_DIR = join(ROOT, 'docs')
const INTERNAL_DIR = join(DOCS_DIR, 'internal')

const violations = []
function fail(file, line, reason) {
  violations.push({ file: relative(ROOT, file), line, reason })
}

/** Recursively collect files under docs/, skipping docs/internal/. */
function walk(dir, out = { docs: [], categories: [], dirs: [] }) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (full === INTERNAL_DIR) continue // unpublished; not part of the contract
    if (statSync(full).isDirectory()) {
      out.dirs.push(full)
      walk(full, out)
    } else if (/\.mdx?$/.test(entry)) {
      out.docs.push(full)
    } else if (entry === '_category_.json') {
      out.categories.push(full)
    }
  }
  return out
}

// ---------------------------------------------------------------------------
// 1. _category_.json: parses as JSON; present in every published directory.
// ---------------------------------------------------------------------------

function checkCategories({ categories, dirs, docs }) {
  for (const file of categories) {
    try {
      const parsed = JSON.parse(readFileSync(file, 'utf8'))
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        fail(file, 1, 'must be a JSON object (Docusaurus category metadata)')
      }
    } catch (err) {
      fail(file, 1, `invalid JSON: ${err.message}`)
    }
  }
  for (const dir of dirs) {
    const holdsDocs = docs.some(d => d.startsWith(dir + sep))
    if (holdsDocs && !existsSync(join(dir, '_category_.json'))) {
      fail(dir, 1, 'directory holds published pages but has no _category_.json')
    }
  }
}

// ---------------------------------------------------------------------------
// Shared: mask code so fences/inline code never trigger link or MDX checks.
// ---------------------------------------------------------------------------

/**
 * Replace fenced code blocks and inline code spans with spaces (preserving
 * newlines and offsets, so line numbers stay accurate).
 */
function maskCode(source) {
  const lines = source.split('\n')
  let inFence = false
  let fenceMarker = ''
  const masked = lines.map(line => {
    const fence = line.match(/^\s*(```+|~~~+)/)
    if (fence) {
      if (!inFence) {
        inFence = true
        fenceMarker = fence[1][0]
      } else if (fence[1][0] === fenceMarker) {
        inFence = false
      }
      return line.replace(/./g, ' ')
    }
    if (inFence) return line.replace(/./g, ' ')
    // Inline code spans: `...` (or ``...`` for spans containing backticks).
    return line.replace(/(`+)[^`]*?\1/g, m => ' '.repeat(m.length))
  })
  return masked.join('\n')
}

/** Strip the YAML frontmatter block (masking it, offsets preserved). */
function maskFrontmatter(source) {
  const match = source.match(/^---\r?\n[\s\S]*?\r?\n---/)
  if (!match) return source
  return match[0].replace(/[^\n]/g, ' ') + source.slice(match[0].length)
}

// ---------------------------------------------------------------------------
// 2. Frontmatter block must be a parseable YAML mapping shape.
// ---------------------------------------------------------------------------

function checkFrontmatterShape(file, source) {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return // presence is lint-docs-frontmatter.mjs's job
  const lines = match[1].split(/\r?\n/)
  lines.forEach((line, i) => {
    const lineNo = i + 2 // 1-based, +1 for the opening `---`
    if (line.includes('\t')) {
      fail(file, lineNo, 'frontmatter contains a tab character (invalid YAML indentation)')
      return
    }
    if (/^\s*$/.test(line) || /^\s*#/.test(line)) return // blank / comment
    if (/^\s+/.test(line)) return // indented continuation (nested value, list, block scalar)
    if (/^-\s/.test(line)) return // top-level list item
    if (/^[A-Za-z0-9_.-]+:(\s|$)/.test(line)) return // key: value
    fail(file, lineNo, `frontmatter line is not valid YAML mapping syntax: ${JSON.stringify(line)}`)
  })
}

// ---------------------------------------------------------------------------
// 3. Relative links must not escape docs/ (they 404 once published).
// ---------------------------------------------------------------------------

const LINK_RE = /!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)|^\s*\[[^\]]+\]:\s+(\S+)/gm

function isRelativeTarget(target) {
  return (
    !/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(target) && // http:, https:, mailto:, data:, …
    !target.startsWith('#') &&
    !target.startsWith('/')
  )
}

function checkLinks(file, masked) {
  for (const match of masked.matchAll(LINK_RE)) {
    const target = (match[1] ?? match[2]).replace(/[#?].*$/, '')
    if (!target || !isRelativeTarget(target)) continue
    const resolved = resolve(dirname(file), target)
    if (resolved !== DOCS_DIR && !resolved.startsWith(DOCS_DIR + sep)) {
      const line = masked.slice(0, match.index).split('\n').length
      fail(
        file,
        line,
        `relative link escapes docs/ and will 404 once published: ${match[1] ?? match[2]}`,
      )
    }
  }
}

// ---------------------------------------------------------------------------
// 4. MDX-hostile constructs (the site compiles .md as MDX).
// ---------------------------------------------------------------------------

// HTML void elements: no closing tag expected.
const VOID_ELEMENTS = new Set([
  'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
  'link', 'meta', 'source', 'track', 'wbr',
])

function checkMdx(file, masked) {
  const lines = masked.split('\n')

  // 4a. Bare `<` followed by something that cannot start a JSX tag,
  // fragment (`<>`), closing tag (`</`), or comment/doctype (`<!`).
  // MDX fails compilation on e.g. `<3`, `<-`, `<=`. Whitespace (or end of
  // line) after `<` is plain text in MDX and stays allowed.
  lines.forEach((line, i) => {
    const bare = line.match(/<(?![A-Za-z/!>\s])(?!$)/)
    if (bare) {
      fail(
        file,
        i + 1,
        `bare \`<\` breaks MDX compilation (col ${bare.index + 1}); ` +
          'escape it as `&lt;` or wrap it in backticks',
      )
    }
  })

  // 4b. Opened JSX/HTML tags that are never closed. Balance open vs close
  // per tag name across the file; self-closing (`<Foo />`) and void HTML
  // elements are exempt.
  const open = new Map() // name -> [{line}]
  const closed = new Map() // name -> count
  const TAG_RE = /<(\/?)([A-Za-z][A-Za-z0-9]*)((?:[^<>"']|"[^"]*"|'[^']*')*?)(\/?)>/g
  for (const match of masked.matchAll(TAG_RE)) {
    const [, closing, name, , selfClosing] = match
    const line = masked.slice(0, match.index).split('\n').length
    if (closing) {
      closed.set(name, (closed.get(name) ?? 0) + 1)
    } else if (!selfClosing && !VOID_ELEMENTS.has(name.toLowerCase())) {
      if (!open.has(name)) open.set(name, [])
      open.get(name).push({ line })
    }
  }
  for (const [name, occurrences] of open) {
    const unclosed = occurrences.length - (closed.get(name) ?? 0)
    for (const { line } of occurrences.slice(0, Math.max(unclosed, 0))) {
      fail(
        file,
        line,
        `unclosed <${name}> tag fails the MDX page build; ` +
          `close it (</${name}>) or self-close it (<${name} … />)`,
      )
    }
  }
}

// ---------------------------------------------------------------------------

const tree = walk(DOCS_DIR)
checkCategories(tree)
for (const file of tree.docs) {
  const source = readFileSync(file, 'utf8')
  checkFrontmatterShape(file, source)
  const masked = maskCode(maskFrontmatter(source))
  checkLinks(file, masked)
  checkMdx(file, masked)
}

if (violations.length > 0) {
  console.error(`✗ Docs contract check failed (${violations.length} issue(s)):\n`)
  for (const v of violations.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)) {
    console.error(`  ${v.file}:${v.line}: ${v.reason}`)
  }
  console.error(
    '\ndocs/** (outside docs/internal/) is published by the site repo; it must ' +
      'stay buildable there. See scripts/lint-docs-contract.mjs for the contract.',
  )
  process.exit(1)
}

console.log(
  `✓ Docs contract holds: ${tree.docs.length} pages, ${tree.categories.length} category files checked`,
)

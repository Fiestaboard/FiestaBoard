#!/usr/bin/env node
// Frontmatter linter for the published Docusaurus site (docs-site/docs/**).
//
// Every page MUST carry a YAML frontmatter block with a non-empty
// `description:` field. Docusaurus uses it for the page <meta description>
// (SEO + social cards) and search snippets; a missing description silently
// degrades both. The page title comes from the in-body `# H1`, so we do NOT
// require a `title:` field here.
//
// Scope is deliberately narrower than the markdown/spell checks: plugin
// READMEs and root-level markdown are GitHub-rendered and legitimately have
// no frontmatter, so requiring it there would be wrong.
//
// Plain Node ESM — no dependencies, so it runs with a bare `node` in CI.

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const ROOT = process.cwd()
const DOCS_DIR = join(ROOT, 'docs-site', 'docs')

/** Recursively collect every .md / .mdx file under a directory. */
function collectDocs(dir) {
  const out = []
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      out.push(...collectDocs(full))
    } else if (/\.mdx?$/.test(entry)) {
      out.push(full)
    }
  }
  return out.sort()
}

/** Return the raw YAML frontmatter block, or null if the file has none. */
function extractFrontmatter(source) {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  return match ? match[1] : null
}

/** Pull a non-empty scalar value for `key:` out of a frontmatter block. */
function frontmatterValue(frontmatter, key) {
  const line = frontmatter
    .split(/\r?\n/)
    .find(l => l.match(new RegExp(`^${key}:`)))
  if (!line) return ''
  // Strip the key, surrounding quotes, and whitespace.
  return line
    .replace(new RegExp(`^${key}:\\s*`), '')
    .replace(/^['"]|['"]$/g, '')
    .trim()
}

function lintFile(file) {
  const source = readFileSync(file, 'utf8')
  const frontmatter = extractFrontmatter(source)
  if (frontmatter === null) return 'missing YAML frontmatter block'
  if (!frontmatterValue(frontmatter, 'description')) {
    return 'missing or empty `description:`'
  }
  return null
}

const files = collectDocs(DOCS_DIR)
const violations = files
  .map(file => ({ file: relative(ROOT, file), reason: lintFile(file) }))
  .filter(v => v.reason)

if (violations.length > 0) {
  console.error(
    `✗ Frontmatter lint failed (${violations.length} issue(s) across ${files.length} file(s)):\n`,
  )
  for (const v of violations) console.error(`  ${v.file}: ${v.reason}`)
  console.error(
    '\nEvery docs-site/docs/**/*.{md,mdx} must have a non-empty `description:` in its YAML frontmatter.',
  )
  process.exit(1)
}

console.log(`✓ Frontmatter valid: ${files.length} files checked`)

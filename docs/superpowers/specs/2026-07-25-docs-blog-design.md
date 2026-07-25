# Docs-Site Blog (Announcements) — Design

**Date:** 2026-07-25
**Status:** Approved pending user review

## Problem

FiestaBoard announcements are posted to r/Vestaboard, where reach has dropped
off after the first few posts. The project wants a first-party announcement
channel on fiestaboard.app: blog-style posts with good social-media preview
metadata, so future announcements can be posted once on the docs site and
linked from Reddit/Discord/etc. with a rich preview card.

## Decision Summary

- **Engine:** Enable the Docusaurus classic preset's built-in blog (currently
  `blog: false` in `docs-site/docusaurus.config.ts`). No custom page code.
- **Name/path:** "Blog" at `/blog` (Docusaurus default).
- **Backfill:** Recreate the three existing Reddit announcements as posts,
  dated to their original Reddit posting dates.
- **Social preview:** Per-post custom 1200×630 social card image via post
  `image` frontmatter.
- **Feeds:** RSS + Atom enabled (`/blog/rss.xml`, `/blog/atom.xml`).
- **Search:** Blog stays out of local search (`indexBlog: false` unchanged).
- **Byline:** Generic "FiestaBoard Team" author (no personal name).
- **Reddit backlinks:** None — posts stand alone; the blog is canonical.
- **Out of scope:** Release automation for future posts; search indexing.

## Architecture

### Config changes (`docs-site/docusaurus.config.ts`)

Replace `blog: false` with:

- `blogTitle` / `blogDescription` — announcement-oriented copy
- `showReadingTime: true`
- `feedOptions: { type: ["rss", "atom"], ... }`
- `blogSidebarTitle: "Recent posts"`, `blogSidebarCount` default
- `onUntruncatedBlogPosts: "throw"` — every post must carry a
  `<!-- truncate -->` marker so the index shows clean excerpts
- No `editUrl` for blog posts (announcements aren't community-editable docs)

Navbar: add `{ to: "/blog", label: "Blog", position: "left" }` after
"Stats". Footer: add a "Blog" link in the Community column.

The blog adds three markdown pages to the build — negligible weight relative
to the versioned-docs cap that guards against deploy OOM.

### Content (`docs-site/blog/`)

```
docs-site/blog/
  authors.yml                     # single "team" author entry
  2026-02-04-introducing-fiestaboard/
    index.md
    social-card.png               # 1200×630 og:image
    *.png                         # recovered Reddit screenshots, kebab-case
  2026-02-15-wysiwyg-editor-scheduling-disney-parks/
    index.md
    social-card.png
    *.png / *.jpg
  2026-05-02-may-2026-update/
    index.md
    social-card.png               # composed from existing docs-site imagery
```

`authors.yml`:

```yaml
team:
  name: FiestaBoard Team
  url: https://github.com/Fiestaboard/FiestaBoard
  image_url: /img/logo.png
```

### Post frontmatter contract

Each post declares: `title`, `description` (drives og:description),
`slug`, `authors: [team]`, `tags`, `image` (post-relative path to
`social-card.png` — drives og:image/twitter:image), `date` (implicit from
directory name). First paragraph(s) end with `<!-- truncate -->`.

### Content adaptation rules

Source text is the author's original Reddit copy (recovered verbatim via
Playwright, stored with original timestamps). Adaptation is light and
mechanical:

- Remove Reddit-context phrasing ("see original post", "in the comments",
  "first and second posts") — replace with links to the earlier blog posts
  or GitHub/Discord as appropriate.
- Emoji section headers become markdown `##` headings (emoji kept).
- Screenshots embedded inline at the position they appeared in the gallery,
  with descriptive alt text.
- Voice, claims, and feature descriptions unchanged.
- The May 2026 post (text-only on Reddit) gets inline illustrations from
  existing `docs-site/static/img/` screenshots where a matching one exists;
  none are fabricated.

### Social cards

One `social-card.png` (1200×630) per post, generated with ImageMagick:
post's hero screenshot composited on a brand-colored background with the
FiestaBoard logo lockup. Kept in the post directory so the whole post is
self-contained.

## Error handling

- `onUntruncatedBlogPosts: "throw"` and existing `onBrokenLinks: "throw"`
  make CI fail on malformed posts or dead links.
- Feed generation and sitemap inclusion are handled by Docusaurus; no custom
  failure modes introduced.

## Testing / verification

1. `npm run build` in `docs-site/` with `DOCS_PR_MODE=1` (skips historical
   version snapshots; same mode CI uses on PRs).
2. Grep built HTML for each post: `og:title`, `og:description`, `og:image`
   (absolute URL to social card), `og:type=article`,
   `article:published_time`.
3. Confirm `/blog` index, three post pages, and `/blog/rss.xml` exist in
   `build/`.
4. Visual check of index + one post via local serve in Playwright.

## Rollout

Feature branch `feat-docs-blog` → PR → merge deploys via the existing docs
deploy workflow. Future announcements = add one directory with `index.md` +
social card; share the `/blog/<slug>` URL anywhere.

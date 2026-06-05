/**
 * Utilities for fetching plugin content directly from GitHub's raw content CDN.
 * FiestaBoard registry plugins are expected to use github.com; raw.githubusercontent.com
 * supports CORS, so these fetches work client-side.
 */

const FETCH_TIMEOUT_MS = 10000;

function fetchReadmeSignal(): AbortSignal {
  return AbortSignal.timeout(FETCH_TIMEOUT_MS);
}

/**
 * Converts a GitHub repo URL to the raw content base URL.
 * e.g. https://github.com/Fiestaboard/fiestaboard-plugin--weather
 *   -> https://raw.githubusercontent.com/Fiestaboard/fiestaboard-plugin--weather/main
 */
export function getGitHubRawBaseUrl(repoUrl: string, branch = "main"): string {
  const cleaned = repoUrl.replace(/\.git$/, "").replace(/\/$/, "");
  const match = cleaned.match(/github\.com\/(.+)/);
  if (!match) return "";
  return `https://raw.githubusercontent.com/${match[1]}/${branch}`;
}

/** Returns `owner/repo` for a github.com HTTPS URL, or null if not GitHub. */
export function parseGitHubRepoPath(repoUrl: string): string | null {
  const cleaned = repoUrl.replace(/\.git$/, "").replace(/\/$/, "");
  const match = cleaned.match(/github\.com\/(.+)/);
  return match ? match[1] : null;
}

/**
 * Converts a relative path (e.g. "./docs/board-display.png" or "docs/board-display.png")
 * to a fully-qualified raw GitHub URL.
 */
export function resolveGitHubRawUrl(repoUrl: string, relativePath: string, branch = "main"): string {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return relativePath;
  const normalised = relativePath.replace(/^\.\//, "");
  return `${base}/${normalised}`;
}

async function tryFetchReadmeAtBranch(repoUrl: string, branch: string): Promise<string | null> {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return null;
  try {
    const res = await fetch(`${base}/README.md`, { signal: fetchReadmeSignal() });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

export interface FetchPluginReadmeResult {
  markdown: string;
  /** Branch used for raw/blob URLs (registry branch, or main/master fallback). */
  resolvedBranch: string;
}

/**
 * Fetches README.md from a GitHub repo.
 * - If `registryBranch` is non-empty, only that branch is tried.
 * - If empty, tries `main` then `master` (common default branches).
 * Returns null on failure (network, 404, non-GitHub URL).
 */
export async function fetchPluginReadme(repoUrl: string, registryBranch = ""): Promise<FetchPluginReadmeResult | null> {
  if (!parseGitHubRepoPath(repoUrl)) return null;

  const explicit = registryBranch.trim();
  if (explicit) {
    const markdown = await tryFetchReadmeAtBranch(repoUrl, explicit);
    if (markdown === null) return null;
    return { markdown, resolvedBranch: explicit };
  }

  for (const branch of ["main", "master"] as const) {
    const markdown = await tryFetchReadmeAtBranch(repoUrl, branch);
    if (markdown !== null) {
      return { markdown, resolvedBranch: branch };
    }
  }
  return null;
}

/**
 * Fetches and parses the manifest.json from a GitHub repo.
 * Returns null on failure.
 */
export async function fetchPluginManifest(repoUrl: string, branch = "main"): Promise<Record<string, unknown> | null> {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return null;
  try {
    const res = await fetch(`${base}/manifest.json`, { signal: fetchReadmeSignal() });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Given a manifest's screenshots array, finds the primary screenshot src
 * and resolves it to a fully-qualified raw GitHub URL.
 * Falls back to the conventional "docs/board-display.png" path.
 */
export function resolveHeroImageUrl(
  repoUrl: string,
  manifest: Record<string, unknown> | null,
  branch = "main",
): string {
  const screenshots = manifest?.screenshots as Array<{ src: string; primary?: boolean }> | undefined;
  let src: string | undefined;

  if (screenshots?.length) {
    const primary = screenshots.find((s) => s.primary);
    src = primary?.src ?? screenshots[0]?.src;
  }

  // Fall back to convention
  src = src ?? "docs/board-display.png";
  return resolveGitHubRawUrl(repoUrl, src, branch);
}

/**
 * Rewrites all relative image src attributes inside markdown content to
 * fully-qualified raw GitHub URLs so they render correctly in the modal.
 * Handles both `![alt](./docs/foo.png)` and `![alt](docs/foo.png)` patterns.
 */
export function rewriteMarkdownImageUrls(markdown: string, repoUrl: string, branch = "main"): string {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return markdown;

  // Match markdown images with relative paths (not starting with http/https)
  return markdown.replace(/!\[([^\]]*)\]\(((?!https?:\/\/)\.?\/?\S+)\)/g, (_, alt, src) => {
    const normalised = src.replace(/^\.\//, "");
    return `![${alt}](${base}/${normalised})`;
  });
}

/**
 * Rewrites relative markdown links (not images) to github.com blob URLs so they open
 * the correct file on GitHub instead of resolving against the app origin.
 * Skips http(s), mailto, #anchors-only, and javascript: URLs.
 */
export function rewriteMarkdownRepoLinks(markdown: string, repoUrl: string, branch: string): string {
  const repoPath = parseGitHubRepoPath(repoUrl);
  if (!repoPath) return markdown;

  const blobBase = `https://github.com/${repoPath}/blob/${branch}/`;

  return markdown.replace(/(?<!\!)\[([^\]]*)\]\(([^)]+)\)/g, (full, label: string, hrefRaw: string) => {
    const href = hrefRaw.trim();
    if (/^https?:\/\//i.test(href) || /^mailto:/i.test(href) || /^javascript:/i.test(href)) {
      return full;
    }
    if (/^#/.test(href)) {
      return full;
    }

    const hashIdx = href.indexOf("#");
    const pathPart = hashIdx === -1 ? href : href.slice(0, hashIdx);
    const hash = hashIdx === -1 ? "" : href.slice(hashIdx);
    const pathOnly = pathPart.trim();
    if (!pathOnly) {
      return full;
    }

    const normalised = pathOnly.replace(/^\.\//, "");
    return `[${label}](${blobBase}${normalised}${hash})`;
  });
}

/**
 * Keep in sync with web/src/lib/github.ts (fetchPluginReadme + markdown rewrites).
 * Duplicated here because docs-site does not share a package with the Next.js app.
 */

const FETCH_TIMEOUT_MS = 10000;

function fetchReadmeSignal(): AbortSignal {
  return AbortSignal.timeout(FETCH_TIMEOUT_MS);
}

export function getGitHubRawBaseUrl(repoUrl: string, branch = "main"): string {
  const cleaned = repoUrl.replace(/\.git$/, "").replace(/\/$/, "");
  const match = cleaned.match(/github\.com\/(.+)/);
  if (!match) return "";
  return `https://raw.githubusercontent.com/${match[1]}/${branch}`;
}

export function parseGitHubRepoPath(repoUrl: string): string | null {
  const cleaned = repoUrl.replace(/\.git$/, "").replace(/\/$/, "");
  const match = cleaned.match(/github\.com\/(.+)/);
  return match ? match[1] : null;
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
  resolvedBranch: string;
}

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

export function rewriteMarkdownImageUrls(markdown: string, repoUrl: string, branch = "main"): string {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return markdown;

  return markdown.replace(/!\[([^\]]*)\]\(((?!https?:\/\/)\.?\/?\S+)\)/g, (_, alt: string, src: string) => {
    const normalised = src.replace(/^\.\//, "");
    return `![${alt}](${base}/${normalised})`;
  });
}

export function rewriteMarkdownRepoLinks(markdown: string, repoUrl: string, branch: string): string {
  const repoPath = parseGitHubRepoPath(repoUrl);
  if (!repoPath) return markdown;

  const blobBase = `https://github.com/${repoPath}/blob/${branch}/`;

  return markdown.replace(/(?<!!)\[([^\]]*)\]\(([^)]+)\)/g, (full, label: string, hrefRaw: string) => {
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

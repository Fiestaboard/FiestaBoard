/**
 * Utilities for fetching plugin content directly from GitHub's raw content CDN.
 * All FiestaBoard external plugins live under github.com/Fiestaboard/fiestaboard-plugin--{name}.
 * raw.githubusercontent.com supports CORS, so these fetches work client-side.
 */

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

/**
 * Fetches the raw README.md content from a GitHub repo.
 * Returns null on failure (network error, 404, etc.).
 */
export async function fetchPluginReadme(repoUrl: string, branch = "main"): Promise<string | null> {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return null;
  try {
    const res = await fetch(`${base}/README.md`, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

/**
 * Fetches and parses the manifest.json from a GitHub repo.
 * Returns null on failure.
 */
export async function fetchPluginManifest(repoUrl: string, branch = "main"): Promise<Record<string, unknown> | null> {
  const base = getGitHubRawBaseUrl(repoUrl, branch);
  if (!base) return null;
  try {
    const res = await fetch(`${base}/manifest.json`, { signal: AbortSignal.timeout(10000) });
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
  branch = "main"
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
  return markdown.replace(
    /!\[([^\]]*)\]\(((?!https?:\/\/)\.?\/?\S+)\)/g,
    (_, alt, src) => {
      const normalised = src.replace(/^\.\//, "");
      return `![${alt}](${base}/${normalised})`;
    }
  );
}

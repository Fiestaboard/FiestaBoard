import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  getGitHubRawBaseUrl,
  parseGitHubRepoPath,
  resolveGitHubRawUrl,
  fetchPluginReadme,
  fetchPluginManifest,
  resolveHeroImageUrl,
  rewriteMarkdownImageUrls,
  rewriteMarkdownRepoLinks,
} from "@/lib/github";

// ---------------------------------------------------------------------------
// getGitHubRawBaseUrl
// ---------------------------------------------------------------------------

describe("getGitHubRawBaseUrl", () => {
  it("converts a standard github.com URL to raw.githubusercontent.com", () => {
    const result = getGitHubRawBaseUrl(
      "https://github.com/Fiestaboard/fiestaboard-plugin--weather"
    );
    expect(result).toBe(
      "https://raw.githubusercontent.com/Fiestaboard/fiestaboard-plugin--weather/main"
    );
  });

  it("uses a custom branch when provided", () => {
    const result = getGitHubRawBaseUrl(
      "https://github.com/Org/my-repo",
      "develop"
    );
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/my-repo/develop"
    );
  });

  it("strips a trailing .git suffix", () => {
    const result = getGitHubRawBaseUrl(
      "https://github.com/Org/my-repo.git"
    );
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/my-repo/main"
    );
  });

  it("strips a trailing slash", () => {
    const result = getGitHubRawBaseUrl(
      "https://github.com/Org/my-repo/"
    );
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/my-repo/main"
    );
  });

  it("returns an empty string for non-GitHub URLs", () => {
    expect(getGitHubRawBaseUrl("https://gitlab.com/Org/my-repo")).toBe("");
  });

  it("returns an empty string for an empty string", () => {
    expect(getGitHubRawBaseUrl("")).toBe("");
  });

  it("handles nested org/repo paths", () => {
    const result = getGitHubRawBaseUrl(
      "https://github.com/SomeOrg/some-repo"
    );
    expect(result).toBe(
      "https://raw.githubusercontent.com/SomeOrg/some-repo/main"
    );
  });
});

// ---------------------------------------------------------------------------
// parseGitHubRepoPath
// ---------------------------------------------------------------------------

describe("parseGitHubRepoPath", () => {
  it("returns owner/repo for a github.com URL", () => {
    expect(parseGitHubRepoPath("https://github.com/Org/my-plugin")).toBe("Org/my-plugin");
  });

  it("returns null for non-GitHub URLs", () => {
    expect(parseGitHubRepoPath("https://gitlab.com/Org/repo")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// resolveGitHubRawUrl
// ---------------------------------------------------------------------------

describe("resolveGitHubRawUrl", () => {
  const REPO = "https://github.com/Org/plugin-name";

  it("resolves a ./relative path to a full raw URL", () => {
    const result = resolveGitHubRawUrl(REPO, "./docs/board-display.png");
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("resolves a bare relative path (no leading ./) to a full raw URL", () => {
    const result = resolveGitHubRawUrl(REPO, "docs/board-display.png");
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("returns the relative path unchanged when the repo URL is not a GitHub URL", () => {
    const result = resolveGitHubRawUrl(
      "https://gitlab.com/Org/repo",
      "./docs/image.png"
    );
    expect(result).toBe("./docs/image.png");
  });

  it("uses the custom branch in the resolved URL", () => {
    const result = resolveGitHubRawUrl(REPO, "README.md", "v2");
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/v2/README.md"
    );
  });

  it("handles a file at the repo root", () => {
    const result = resolveGitHubRawUrl(REPO, "manifest.json");
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/manifest.json"
    );
  });
});

// ---------------------------------------------------------------------------
// fetchPluginReadme
// ---------------------------------------------------------------------------

describe("fetchPluginReadme", () => {
  const REPO = "https://github.com/Org/plugin-name";

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns README text and resolved branch on a successful fetch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => "# My Plugin\nThis is the README.",
      })
    );

    const result = await fetchPluginReadme(REPO);
    expect(result).not.toBeNull();
    expect(result!.markdown).toBe("# My Plugin\nThis is the README.");
    expect(result!.resolvedBranch).toBe("main");
  });

  it("fetches from the correct raw.githubusercontent.com URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => "content",
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchPluginReadme(REPO);

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("raw.githubusercontent.com");
    expect(calledUrl).toContain("README.md");
  });

  it("uses only the registry branch when provided (no main/master fallback)", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      text: async () => "from develop",
    });
    vi.stubGlobal("fetch", mockFetch);

    const result = await fetchPluginReadme(REPO, "develop");

    expect(mockFetch).toHaveBeenCalledOnce();
    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/develop/");
    expect(calledUrl).toContain("README.md");
    expect(result?.markdown).toBe("from develop");
    expect(result?.resolvedBranch).toBe("develop");
  });

  it("falls back from main to master when registry branch is empty", async () => {
    const mockFetch = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 404 })
      .mockResolvedValueOnce({
        ok: true,
        text: async () => "# Legacy default branch",
      });
    vi.stubGlobal("fetch", mockFetch);

    const result = await fetchPluginReadme(REPO);

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(String(mockFetch.mock.calls[0][0])).toContain("/main/");
    expect(String(mockFetch.mock.calls[1][0])).toContain("/master/");
    expect(result?.markdown).toBe("# Legacy default branch");
    expect(result?.resolvedBranch).toBe("master");
  });

  it("returns null when the response is not ok on both main and master", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 })
    );

    const result = await fetchPluginReadme(REPO);
    expect(result).toBeNull();
  });

  it("returns null on network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("Network error"))
    );

    const result = await fetchPluginReadme(REPO);
    expect(result).toBeNull();
  });

  it("returns null for a non-GitHub repo URL", async () => {
    const result = await fetchPluginReadme("https://gitlab.com/Org/repo");
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// fetchPluginManifest
// ---------------------------------------------------------------------------

describe("fetchPluginManifest", () => {
  const REPO = "https://github.com/Org/plugin-name";

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns parsed manifest object on success", async () => {
    const manifest = { id: "plugin-name", name: "Plugin", version: "1.0.0" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => manifest,
      })
    );

    const result = await fetchPluginManifest(REPO);
    expect(result).toEqual(manifest);
  });

  it("fetches from manifest.json at the raw CDN URL", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", mockFetch);

    await fetchPluginManifest(REPO);

    const calledUrl = mockFetch.mock.calls[0][0] as string;
    expect(calledUrl).toContain("raw.githubusercontent.com");
    expect(calledUrl).toContain("manifest.json");
  });

  it("returns null when the response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 })
    );

    const result = await fetchPluginManifest(REPO);
    expect(result).toBeNull();
  });

  it("returns null on network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    );

    const result = await fetchPluginManifest(REPO);
    expect(result).toBeNull();
  });

  it("returns null for a non-GitHub repo URL", async () => {
    const result = await fetchPluginManifest("https://example.com/not-github");
    expect(result).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// resolveHeroImageUrl
// ---------------------------------------------------------------------------

describe("resolveHeroImageUrl", () => {
  const REPO = "https://github.com/Org/plugin-name";

  it("uses the primary screenshot src when present", () => {
    const manifest = {
      screenshots: [
        { src: "docs/board-display.png", primary: true },
        { src: "docs/configuration.png" },
      ],
    };
    const result = resolveHeroImageUrl(REPO, manifest);
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("falls back to the first screenshot when none is primary", () => {
    const manifest = {
      screenshots: [{ src: "docs/other.png" }],
    };
    const result = resolveHeroImageUrl(REPO, manifest);
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/other.png"
    );
  });

  it("falls back to docs/board-display.png when screenshots array is empty", () => {
    const result = resolveHeroImageUrl(REPO, { screenshots: [] });
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("falls back to docs/board-display.png when manifest is null", () => {
    const result = resolveHeroImageUrl(REPO, null);
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("falls back to docs/board-display.png when manifest has no screenshots field", () => {
    const result = resolveHeroImageUrl(REPO, { name: "Plugin" });
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });

  it("resolves ./relative paths in screenshot src", () => {
    const manifest = {
      screenshots: [{ src: "./docs/board-display.png", primary: true }],
    };
    const result = resolveHeroImageUrl(REPO, manifest);
    expect(result).toBe(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
  });
});

// ---------------------------------------------------------------------------
// rewriteMarkdownImageUrls
// ---------------------------------------------------------------------------

describe("rewriteMarkdownImageUrls", () => {
  const REPO = "https://github.com/Org/plugin-name";

  it("rewrites a ./relative image URL to a full raw GitHub URL", () => {
    const markdown = "![Display](./docs/board-display.png)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toBe(
      "![Display](https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png)"
    );
  });

  it("rewrites a bare relative image URL (no leading ./)", () => {
    const markdown = "![Display](docs/board-display.png)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toBe(
      "![Display](https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png)"
    );
  });

  it("does NOT rewrite already-absolute https URLs", () => {
    const markdown =
      "![Display](https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toBe(markdown);
  });

  it("does NOT rewrite http:// URLs", () => {
    const markdown = "![Display](http://example.com/image.png)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toBe(markdown);
  });

  it("rewrites multiple relative images in one pass", () => {
    const markdown = `
# Readme

![Hero](./docs/board-display.png)

Some text.

![Config](./docs/configuration.png)
    `.trim();
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toContain(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/board-display.png"
    );
    expect(result).toContain(
      "https://raw.githubusercontent.com/Org/plugin-name/main/docs/configuration.png"
    );
  });

  it("leaves non-image markdown links untouched", () => {
    const markdown = "[Click me](./docs/SETUP.md)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toBe("[Click me](./docs/SETUP.md)");
  });

  it("returns markdown unchanged when repo URL is not a GitHub URL", () => {
    const markdown = "![Display](./docs/board-display.png)";
    const result = rewriteMarkdownImageUrls(markdown, "https://gitlab.com/Org/repo");
    expect(result).toBe(markdown);
  });

  it("returns an empty string unchanged", () => {
    const result = rewriteMarkdownImageUrls("", REPO);
    expect(result).toBe("");
  });

  it("preserves alt text with special characters", () => {
    const markdown = "![Board display: 6×22 grid](./docs/board-display.png)";
    const result = rewriteMarkdownImageUrls(markdown, REPO);
    expect(result).toContain("raw.githubusercontent.com");
    expect(result).toContain("Board display");
  });
});

// ---------------------------------------------------------------------------
// rewriteMarkdownRepoLinks
// ---------------------------------------------------------------------------

describe("rewriteMarkdownRepoLinks", () => {
  const REPO = "https://github.com/Org/plugin-name";

  it("rewrites a relative .md link to a GitHub blob URL", () => {
    const markdown = "[Setup guide](./docs/SETUP.md)";
    const result = rewriteMarkdownRepoLinks(markdown, REPO, "main");
    expect(result).toBe(
      "[Setup guide](https://github.com/Org/plugin-name/blob/main/docs/SETUP.md)"
    );
  });

  it("uses the resolved branch in the blob path", () => {
    const markdown = "[Readme](README.md)";
    const result = rewriteMarkdownRepoLinks(markdown, REPO, "master");
    expect(result).toBe(
      "[Readme](https://github.com/Org/plugin-name/blob/master/README.md)"
    );
  });

  it("preserves hash fragments on relative paths", () => {
    const markdown = "[Section](./docs/SETUP.md#troubleshooting)";
    const result = rewriteMarkdownRepoLinks(markdown, REPO, "main");
    expect(result).toBe(
      "[Section](https://github.com/Org/plugin-name/blob/main/docs/SETUP.md#troubleshooting)"
    );
  });

  it("does not rewrite https links", () => {
    const markdown = "[External](https://example.com/page)";
    expect(rewriteMarkdownRepoLinks(markdown, REPO, "main")).toBe(markdown);
  });

  it("does not rewrite mailto links", () => {
    const markdown = "[Email](mailto:a@example.com)";
    expect(rewriteMarkdownRepoLinks(markdown, REPO, "main")).toBe(markdown);
  });

  it("does not rewrite hash-only anchor links", () => {
    const markdown = "[TOC](#configuration)";
    expect(rewriteMarkdownRepoLinks(markdown, REPO, "main")).toBe(markdown);
  });

  it("does not rewrite javascript: URLs", () => {
    const markdown = "[X](javascript:alert(1))";
    expect(rewriteMarkdownRepoLinks(markdown, REPO, "main")).toBe(markdown);
  });

  it("returns markdown unchanged when repo URL is not GitHub", () => {
    const markdown = "[Setup](./docs/SETUP.md)";
    const result = rewriteMarkdownRepoLinks(markdown, "https://gitlab.com/Org/repo", "main");
    expect(result).toBe(markdown);
  });
});

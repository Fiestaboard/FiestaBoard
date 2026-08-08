import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import { StaticBoardDisplay } from "@fiestaboard/ui";
import { fetchPluginReadme, rewriteMarkdownImageUrls, rewriteMarkdownRepoLinks } from "@site/src/lib/github-readme";
import type { PluginEntry } from "@site/src/plugin-data";
import {
  CATEGORY_LABELS,
  pluginBoardImagePath,
  pluginPreviews,
  plugins,
  previewLabel,
  previewMessage,
} from "@site/src/plugin-data";
import Heading from "@theme/Heading";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { type ReactNode, useEffect, useState } from "react";

import styles from "./detail.module.css";

/* ── README renderer (client-only) ── */

function ReadmeContent({ markdown }: { markdown: string }) {
  const [Markdown, setMarkdown] = useState<React.ComponentType<{ children: string }> | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([import("react-markdown"), import("remark-gfm")]).then(([rm, rgfm]) => {
      if (cancelled) return;
      const ReactMarkdown = rm.default;
      const remarkGfm = rgfm.default;

      // Create a wrapper component that applies remark-gfm and custom renderers
      const Wrapper = ({ children }: { children: string }) => (
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children: kids, ...props }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {kids}
              </a>
            ),
            img: ({ src, alt, ...props }) => (
              <img src={src} alt={alt ?? ""} className={styles.readmeImage} loading="lazy" {...props} />
            ),
            pre: ({ children: kids, ...props }) => (
              <pre className={styles.readmePre} {...props}>
                {kids}
              </pre>
            ),
            code: ({ children: kids, className, ...props }) => {
              const isBlock = className?.startsWith("language-");
              return isBlock ? (
                <code className={className} {...props}>
                  {kids}
                </code>
              ) : (
                <code className={styles.readmeInlineCode} {...props}>
                  {kids}
                </code>
              );
            },
            table: ({ children: kids, ...props }) => (
              <div className={styles.readmeTableWrap}>
                <table className={styles.readmeTable} {...props}>
                  {kids}
                </table>
              </div>
            ),
            thead: ({ children: kids, ...props }) => (
              <thead className={styles.readmeThead} {...props}>
                {kids}
              </thead>
            ),
            th: ({ children: kids, ...props }) => (
              <th className={styles.readmeTh} {...props}>
                {kids}
              </th>
            ),
            td: ({ children: kids, ...props }) => (
              <td className={styles.readmeTd} {...props}>
                {kids}
              </td>
            ),
            h1: ({ children: kids, ...props }) => (
              <h1 className={styles.readmeH1} {...props}>
                {kids}
              </h1>
            ),
            h2: ({ children: kids, ...props }) => (
              <h2 className={styles.readmeH2} {...props}>
                {kids}
              </h2>
            ),
            h3: ({ children: kids, ...props }) => (
              <h3 className={styles.readmeH3} {...props}>
                {kids}
              </h3>
            ),
            p: ({ children: kids, ...props }) => (
              <p className={styles.readmeP} {...props}>
                {kids}
              </p>
            ),
            ul: ({ children: kids, ...props }) => (
              <ul className={styles.readmeUl} {...props}>
                {kids}
              </ul>
            ),
            ol: ({ children: kids, ...props }) => (
              <ol className={styles.readmeOl} {...props}>
                {kids}
              </ol>
            ),
            blockquote: ({ children: kids, ...props }) => (
              <blockquote className={styles.readmeBlockquote} {...props}>
                {kids}
              </blockquote>
            ),
            hr: () => <hr className={styles.readmeHr} />,
            strong: ({ children: kids, ...props }) => (
              <strong className={styles.readmeStrong} {...props}>
                {kids}
              </strong>
            ),
          }}
        >
          {children}
        </ReactMarkdown>
      );
      setMarkdown(() => Wrapper);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!Markdown) {
    return (
      <div className={styles.skeleton}>
        <div />
        <div />
        <div />
        <div />
      </div>
    );
  }

  return <Markdown>{markdown}</Markdown>;
}

/* ── Detail page content (uses browser APIs) ── */

function DetailContent() {
  const [boardColor, setBoardColor] = useState<"black" | "white">("black");
  const [activePreview, setActivePreview] = useState(0);
  const [readme, setReadme] = useState<string | null>(null);
  const [loadingReadme, setLoadingReadme] = useState(true);

  // Read plugin ID from query string
  const params = new URLSearchParams(window.location.search);
  const pluginId = params.get("id") ?? "";
  const plugin: PluginEntry | undefined = plugins.find((p) => p.id === pluginId);

  useEffect(() => {
    if (!plugin?.repository) {
      setLoadingReadme(false);
      return;
    }
    let cancelled = false;
    fetchPluginReadme(plugin.repository, plugin.branch ?? "")
      .then((result) => {
        if (cancelled) return;
        if (!result) {
          setReadme(null);
          return;
        }
        const processed = rewriteMarkdownRepoLinks(
          rewriteMarkdownImageUrls(result.markdown, plugin.repository, result.resolvedBranch),
          plugin.repository,
          result.resolvedBranch,
        );
        setReadme(processed);
      })
      .catch(() => {
        if (!cancelled) setReadme(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingReadme(false);
      });
    return () => {
      cancelled = true;
    };
  }, [plugin?.repository, plugin?.branch]);

  if (!plugin) {
    return (
      <div className={styles.notFound}>
        <Heading as="h1">Plugin Not Found</Heading>
        <p>The plugin "{pluginId}" doesn't exist in the registry.</p>
        <Link className="button button--primary" to="/plugins">
          ← Back to Plugin Directory
        </Link>
      </div>
    );
  }

  const categoryLabel = CATEGORY_LABELS[plugin.category] ?? plugin.category;
  const previews = pluginPreviews[plugin.id]?.previews ?? [];
  const preview = previews[Math.min(activePreview, previews.length - 1)];
  // Authors may declare several previews of the same shape ("Flagship" twice);
  // number the repeats so every tab has a distinct accessible name.
  const tabLabels = previews.map((entry, index) => {
    const label = previewLabel(entry);
    const repeat = previews.slice(0, index).filter((other) => previewLabel(other) === label).length;
    return repeat > 0 ? `${label} ${repeat + 1}` : label;
  });

  return (
    <>
      {/* Back link */}
      <div className={styles.backRow}>
        <Link to="/plugins" className={styles.backLink}>
          ← Back to Plugin Directory
        </Link>
      </div>

      {/* Board preview: one board mounted at a time, tabs across previews[] */}
      {preview && (
        <div className={styles.heroBoard}>
          {previews.length > 1 && (
            <div className={styles.deviceTabs} role="tablist" aria-label="Board shape">
              {tabLabels.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  role="tab"
                  aria-selected={index === activePreview}
                  className={clsx(styles.deviceTab, index === activePreview && styles.deviceTabActive)}
                  onClick={() => setActivePreview(index)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          <div className={styles.heroBoardDisplay}>
            <StaticBoardDisplay
              message={previewMessage(preview)}
              size="md"
              boardType={boardColor}
              deviceType={preview.device_type ?? "flagship"}
              notesWide={preview.notes_wide ?? 1}
              notesTall={preview.notes_tall ?? 1}
              previewLabel={`${plugin.name} displayed on a split-flap board`}
            />
          </div>
        </div>
      )}

      {/* Backwards compat: plugins with no previews entry yet keep their
          legacy screenshot hero (hidden if the image doesn't exist either) */}
      {!preview && (
        <div className={styles.heroImage}>
          <img
            src={pluginBoardImagePath(plugin, boardColor === "white" ? "light" : "dark")}
            alt={`${plugin.name} displayed on a split-flap board`}
            onError={(e) => {
              (e.target as HTMLImageElement).parentElement!.style.display = "none";
            }}
          />
        </div>
      )}

      {/* Board color toggle */}
      <div className={styles.boardColorToggle} role="radiogroup" aria-label="Board color">
        <button
          type="button"
          role="radio"
          className={clsx(styles.boardColorOption, boardColor === "black" && styles.boardColorOptionActive)}
          onClick={() => setBoardColor("black")}
          aria-checked={boardColor === "black"}
        >
          Black Board
        </button>
        <button
          type="button"
          role="radio"
          className={clsx(styles.boardColorOption, boardColor === "white" && styles.boardColorOptionActive)}
          onClick={() => setBoardColor("white")}
          aria-checked={boardColor === "white"}
        >
          White Board
        </button>
      </div>

      {/* Plugin header */}
      <div className={styles.pluginHeader}>
        <div className={styles.pluginMeta}>
          <div className={styles.pluginTitleRow}>
            <Heading as="h1" className={styles.pluginName}>
              {plugin.name}
            </Heading>
            <span className={clsx(styles.categoryBadge, styles[`category_${plugin.category}`])}>{categoryLabel}</span>
          </div>
          <p className={styles.pluginDescription}>{plugin.description}</p>
          <div className={styles.pluginDetails}>
            <span>by {plugin.author}</span>
            <span className={styles.detailDot}>·</span>
            <span>Requires FiestaBoard {plugin.fiestaboard_version}</span>
          </div>
        </div>

        <div className={styles.pluginActions}>
          {plugin.repository && (
            <a
              href={plugin.repository}
              target="_blank"
              rel="noopener noreferrer"
              className="button button--outline button--primary button--sm"
            >
              View on GitHub ↗
            </a>
          )}
        </div>
      </div>

      {/* README section */}
      <div className={styles.readmeSection}>
        <Heading as="h2" className={styles.readmeSectionTitle}>
          Documentation
        </Heading>
        {loadingReadme ? (
          <div className={styles.skeleton}>
            <div />
            <div />
            <div />
            <div />
          </div>
        ) : readme ? (
          <div className={styles.readmeBody}>
            <ReadmeContent markdown={readme} />
          </div>
        ) : (
          <p className={styles.readmeEmpty}>
            Documentation not available.{" "}
            {plugin.repository && (
              <a href={plugin.repository} target="_blank" rel="noopener noreferrer">
                View the source on GitHub
              </a>
            )}
          </p>
        )}
      </div>
    </>
  );
}

/* ── Page wrapper ── */

export default function PluginDetailPage(): ReactNode {
  return (
    <Layout title="Plugin Details" description="View plugin details, documentation, and screenshots.">
      <main className={styles.detailPage}>
        <div className="container">
          <BrowserOnly
            fallback={
              <div className={styles.skeleton}>
                <div />
                <div />
                <div />
              </div>
            }
          >
            {() => <DetailContent />}
          </BrowserOnly>
        </div>
      </main>
    </Layout>
  );
}

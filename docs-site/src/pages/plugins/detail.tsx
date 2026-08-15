import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import {
  BoardShowcase,
  Box,
  Button,
  EmptyState,
  Flex,
  Heading,
  PluginCategoryBadge,
  Skeleton,
  Table,
  TableCell,
  TableHead,
  TableHeader,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { fetchPluginReadme, rewriteMarkdownImageUrls, rewriteMarkdownRepoLinks } from "@site/src/lib/github-readme";
import type { PluginEntry } from "@site/src/plugin-data";
import { CATEGORY_LABELS, pluginBoardImagePath, pluginPreviews, plugins } from "@site/src/plugin-data";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { PackageX } from "lucide-react";
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
          /*
           * These renderers are markdown *output* nodes, not app markup, so the
           * prose ones stay as raw elements for the same reason the docs' own
           * MDX does (see src/css/custom.css): FiestaUI's Text/Heading/List/Code
           * are sized for the app's dense chrome, and README bodies need the
           * long-form type scale that detail.module.css defines. Table nodes are
           * the exception and do map onto the DS Table set, matching
           * src/theme/MDXComponents.ts.
           */
          /* eslint-disable react/forbid-elements */
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
            // Table nodes map onto the design-system Table set, the same way
            // src/theme/MDXComponents.ts maps GFM tables in the docs themselves.
            table: ({ children: kids, ...props }) => (
              <Box className={styles.readmeTableWrap}>
                <Table className={styles.readmeTable} {...props}>
                  {kids}
                </Table>
              </Box>
            ),
            thead: ({ children: kids, ...props }) => (
              <TableHeader className={styles.readmeThead} {...props}>
                {kids}
              </TableHeader>
            ),
            th: ({ children: kids, ...props }) => (
              <TableHead className={styles.readmeTh} {...props}>
                {kids}
              </TableHead>
            ),
            td: ({ children: kids, ...props }) => (
              <TableCell className={styles.readmeTd} {...props}>
                {kids}
              </TableCell>
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
          /* eslint-enable react/forbid-elements */
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
      <Box className={styles.skeleton}>
        <Skeleton />
        <Skeleton />
        <Skeleton />
        <Skeleton />
      </Box>
    );
  }

  return <Markdown>{markdown}</Markdown>;
}

/* ── Detail page content (uses browser APIs) ── */

function DetailContent() {
  // Only the legacy screenshot fallback needs page-owned colour state;
  // BoardShowcase owns shape tabs and the colour toggle itself.
  const [boardColor, setBoardColor] = useState<"black" | "white">("black");
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
      <EmptyState
        className={styles.notFound}
        icon={PackageX}
        title="Plugin not found"
        description={`The plugin "${pluginId}" doesn't exist in the registry.`}
        action={
          <Button asChild>
            <Link to="/plugins">← Back to Plugin Directory</Link>
          </Button>
        }
      />
    );
  }

  const categoryLabel = CATEGORY_LABELS[plugin.category] ?? plugin.category;
  const previews = pluginPreviews[plugin.id]?.previews ?? [];

  return (
    <>
      {/* Back link */}
      <Box className={styles.backRow}>
        <Link to="/plugins" className={styles.backLink}>
          ← Back to Plugin Directory
        </Link>
      </Box>

      {/* Board preview: shape tabs + colour toggle live inside BoardShowcase */}
      {previews.length > 0 ? (
        <Box className={styles.heroBoard}>
          <BoardShowcase
            previews={previews}
            size="md"
            previewLabel={`${plugin.name} displayed on a split-flap board`}
          />
        </Box>
      ) : (
        <>
          {/* Backwards compat: plugins with no previews entry yet keep their
              legacy screenshot hero (hidden if the image doesn't exist either) */}
          <Box className={styles.heroImage}>
            <img
              src={pluginBoardImagePath(plugin, boardColor === "white" ? "light" : "dark")}
              alt={`${plugin.name} displayed on a split-flap board`}
              onError={(e) => {
                (e.target as HTMLImageElement).parentElement!.style.display = "none";
              }}
            />
          </Box>
          <Box className={styles.boardColorToggle} role="radiogroup" aria-label="Board color">
            {(["black", "white"] as const).map((color) => (
              <Button
                key={color}
                type="button"
                variant="ghost"
                role="radio"
                className={clsx(styles.boardColorOption, boardColor === color && styles.boardColorOptionActive)}
                onClick={() => setBoardColor(color)}
                aria-checked={boardColor === color}
              >
                {color === "black" ? "Black Board" : "White Board"}
              </Button>
            ))}
          </Box>
        </>
      )}

      {/* Plugin header */}
      <Box className={styles.pluginHeader}>
        <Box className={styles.pluginMeta}>
          <Box className={styles.pluginTitleRow}>
            <h1 className={styles.pluginName}>{plugin.name}</h1>
            <PluginCategoryBadge category={plugin.category} label={categoryLabel} />
          </Box>
          <Text className={styles.pluginDescription}>{plugin.description}</Text>
          <Flex align="center" gap="2" wrap className={styles.pluginDetails}>
            <Text as="span">by {plugin.author}</Text>
            <Text as="span" className={styles.detailDot}>
              ·
            </Text>
            <Text as="span">Requires FiestaBoard {plugin.fiestaboard_version}</Text>
          </Flex>
        </Box>

        <Box className={styles.pluginActions}>
          {plugin.repository && (
            <Button variant="outline" size="sm" asChild>
              <Link href={plugin.repository} target="_blank" rel="noopener noreferrer">
                View on GitHub ↗
              </Link>
            </Button>
          )}
        </Box>
      </Box>

      {/* README section */}
      <Box className={styles.readmeSection}>
        <Heading level={2} className={styles.readmeSectionTitle}>
          Documentation
        </Heading>
        {loadingReadme ? (
          <Box className={styles.skeleton}>
            <Skeleton />
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </Box>
        ) : readme ? (
          <Box className={styles.readmeBody}>
            <ReadmeContent markdown={readme} />
          </Box>
        ) : (
          <Text className={styles.readmeEmpty}>
            Documentation not available.{" "}
            {plugin.repository && (
              <TextLink href={plugin.repository} target="_blank" rel="noopener noreferrer">
                View the source on GitHub
              </TextLink>
            )}
          </Text>
        )}
      </Box>
    </>
  );
}

/* ── Page wrapper ── */

export default function PluginDetailPage(): ReactNode {
  return (
    <Layout title="Plugin Details" description="View plugin details, documentation, and screenshots.">
      <Box as="main" className={styles.detailPage}>
        <Box className="container">
          <BrowserOnly
            fallback={
              <Box className={styles.skeleton}>
                <Skeleton />
                <Skeleton />
                <Skeleton />
              </Box>
            }
          >
            {() => <DetailContent />}
          </BrowserOnly>
        </Box>
      </Box>
    </Layout>
  );
}

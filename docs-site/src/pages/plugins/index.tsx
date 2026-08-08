import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import { Badge, BoardTeaser, Box, Button, EmptyState, Flex, Heading, Input, Text } from "@fiestaboard/ui";
import type { PluginEntry } from "@site/src/plugin-data";
import { CATEGORIES, CATEGORY_LABELS, pluginPreviews, plugins } from "@site/src/plugin-data";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { SearchX } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import styles from "./index.module.css";

function CategoryBadge({ category }: { category: string }) {
  const label = CATEGORY_LABELS[category] ?? category;
  return (
    <Badge variant="secondary" className={clsx(styles.categoryBadge, styles[`category_${category}`])}>
      {label}
    </Badge>
  );
}

/**
 * Scales the fixed-size BoardTeaser strip up to the card's available width
 * (viewport breakpoints can't see card width, so this measures instead).
 * `transform` doesn't affect layout, so the wrapper height tracks the scale.
 */
function ScaledTeaser({ teaser, boardType }: { teaser: string; boardType: "black" | "white" }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useEffect(() => {
    const container = containerRef.current;
    const strip = container?.firstElementChild as HTMLElement | null;
    if (!container || !strip) return;
    const compute = () => {
      // offsetWidth ignores the transform, so this is the intrinsic width.
      if (strip.offsetWidth > 0) {
        setScale(Math.min(1.5, Math.max(0.85, container.clientWidth / strip.offsetWidth)));
      }
    };
    compute();
    const observer = new ResizeObserver(compute);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return (
    <Box ref={containerRef} className={styles.teaserScaler} style={{ height: `${18 * scale}px` }}>
      <Box style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}>
        <BoardTeaser teaser={teaser} boardType={boardType} />
      </Box>
    </Box>
  );
}

function PluginCard({ plugin }: { plugin: PluginEntry }) {
  const { colorMode } = useColorMode();
  const teaser = pluginPreviews[plugin.id]?.teaser ?? plugin.name;

  return (
    <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.pluginCard}>
      <Box className={styles.pluginCardBody}>
        <Box className={styles.pluginCardHeader}>
          <Heading level={3} className={styles.pluginCardTitle}>
            {plugin.name}
          </Heading>
          <CategoryBadge category={plugin.category} />
        </Box>
        <Text className={styles.pluginCardDescription}>{plugin.description}</Text>
        <Text as="span" className={styles.pluginCardAuthor}>
          by {plugin.author}
        </Text>
      </Box>
      <Box className={styles.pluginCardTeaser}>
        <ScaledTeaser teaser={teaser} boardType={colorMode === "dark" ? "black" : "white"} />
      </Box>
    </Link>
  );
}

export default function PluginDirectory(): ReactNode {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const filtered = useMemo(() => {
    return plugins.filter((p) => {
      if (activeCategory && p.category !== activeCategory) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || p.id.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [search, activeCategory]);

  return (
    <Layout
      title="Plugin Directory"
      description="Browse all FiestaBoard plugins - weather, stocks, transit, sports, art, and more. Explore what's available for your split-flap display."
    >
      <Box as="main" className={styles.directoryPage}>
        <Box className="container">
          {/* Header */}
          <Box className={styles.header}>
            <h1 className={styles.title}>Plugin Directory</h1>
            <Text className={styles.subtitle}>
              Explore {plugins.length} plugins for your split-flap display - from weather and stocks to Disney park wait
              times and generative art.
            </Text>
          </Box>

          {/* Search and filters */}
          <Box className={styles.controls}>
            <Input
              type="search"
              className={styles.searchInput}
              placeholder="Search plugins..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search plugins"
            />
            <Flex wrap gap="2" className={styles.categoryFilters}>
              <Button
                type="button"
                variant="ghost"
                aria-pressed={activeCategory === null}
                className={clsx(styles.filterButton, activeCategory === null && styles.filterButtonActive)}
                onClick={() => setActiveCategory(null)}
              >
                All
              </Button>
              {CATEGORIES.map((cat) => (
                <Button
                  key={cat}
                  type="button"
                  variant="ghost"
                  aria-pressed={activeCategory === cat}
                  className={clsx(styles.filterButton, activeCategory === cat && styles.filterButtonActive)}
                  onClick={() => setActiveCategory(cat === activeCategory ? null : cat)}
                >
                  {CATEGORY_LABELS[cat]}
                </Button>
              ))}
            </Flex>
          </Box>

          {/* Results */}
          {filtered.length > 0 ? (
            <Box className={styles.pluginGrid}>
              {filtered.map((plugin) => (
                <PluginCard key={plugin.id} plugin={plugin} />
              ))}
            </Box>
          ) : (
            <EmptyState
              className={styles.emptyState}
              icon={SearchX}
              title="No plugins found"
              description="No plugins match your search. Try a different query or category."
            />
          )}

          {/* CTA */}
          <Box className={styles.cta}>
            <Text>
              Want to build your own plugin?{" "}
              <Link to="/docs/development/plugin-guide">Check out the Plugin Development Guide →</Link>
            </Text>
          </Box>
        </Box>
      </Box>
    </Layout>
  );
}

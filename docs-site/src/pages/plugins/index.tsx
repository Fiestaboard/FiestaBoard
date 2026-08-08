import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import { BoardTeaser } from "@fiestaboard/ui";
import type { PluginEntry } from "@site/src/plugin-data";
import { CATEGORIES, CATEGORY_LABELS, pluginPreviews, plugins } from "@site/src/plugin-data";
import Heading from "@theme/Heading";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import styles from "./index.module.css";

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
    <div ref={containerRef} className={styles.teaserScaler} style={{ height: `${18 * scale}px` }}>
      <div style={{ transform: `scale(${scale})`, transformOrigin: "top center" }}>
        <BoardTeaser teaser={teaser} boardType={boardType} />
      </div>
    </div>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const label = CATEGORY_LABELS[category] ?? category;
  return <span className={clsx(styles.categoryBadge, styles[`category_${category}`])}>{label}</span>;
}

function PluginCard({ plugin }: { plugin: PluginEntry }) {
  const { colorMode } = useColorMode();
  const teaser = pluginPreviews[plugin.id]?.teaser ?? plugin.name;

  return (
    <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.pluginCard}>
      <div className={styles.pluginCardBody}>
        <div className={styles.pluginCardHeader}>
          <Heading as="h3" className={styles.pluginCardTitle}>
            {plugin.name}
          </Heading>
          <CategoryBadge category={plugin.category} />
        </div>
        <p className={styles.pluginCardDescription}>{plugin.description}</p>
        <span className={styles.pluginCardAuthor}>by {plugin.author}</span>
      </div>
      <div className={styles.pluginCardTeaser}>
        <ScaledTeaser teaser={teaser} boardType={colorMode === "dark" ? "black" : "white"} />
      </div>
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
      <main className={styles.directoryPage}>
        <div className="container">
          {/* Header */}
          <div className={styles.header}>
            <Heading as="h1" className={styles.title}>
              Plugin Directory
            </Heading>
            <p className={styles.subtitle}>
              Explore {plugins.length} plugins for your split-flap display - from weather and stocks to Disney park wait
              times and generative art.
            </p>
          </div>

          {/* Search and filters */}
          <div className={styles.controls}>
            <input
              type="search"
              className={styles.searchInput}
              placeholder="Search plugins..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              aria-label="Search plugins"
            />
            <div className={styles.categoryFilters}>
              <button
                type="button"
                className={clsx(styles.filterButton, activeCategory === null && styles.filterButtonActive)}
                onClick={() => setActiveCategory(null)}
              >
                All
              </button>
              {CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={clsx(styles.filterButton, activeCategory === cat && styles.filterButtonActive)}
                  onClick={() => setActiveCategory(cat === activeCategory ? null : cat)}
                >
                  {CATEGORY_LABELS[cat]}
                </button>
              ))}
            </div>
          </div>

          {/* Results */}
          {filtered.length > 0 ? (
            <div className={styles.pluginGrid}>
              {filtered.map((plugin) => (
                <PluginCard key={plugin.id} plugin={plugin} />
              ))}
            </div>
          ) : (
            <div className={styles.emptyState}>
              <p>No plugins match your search. Try a different query or category.</p>
            </div>
          )}

          {/* CTA */}
          <div className={styles.cta}>
            <p>
              Want to build your own plugin?{" "}
              <Link to="/docs/development/plugin-guide">Check out the Plugin Development Guide →</Link>
            </p>
          </div>
        </div>
      </main>
    </Layout>
  );
}

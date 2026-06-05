import Link from "@docusaurus/Link";
import type { PluginEntry } from "@site/src/plugin-data";
import { CATEGORIES, CATEGORY_LABELS, pluginBoardImagePath, plugins } from "@site/src/plugin-data";
import Heading from "@theme/Heading";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { type ReactNode, useMemo, useState } from "react";

import styles from "./index.module.css";

function CategoryBadge({ category }: { category: string }) {
  const label = CATEGORY_LABELS[category] ?? category;
  return <span className={clsx(styles.categoryBadge, styles[`category_${category}`])}>{label}</span>;
}

function PluginCard({ plugin, boardColor }: { plugin: PluginEntry; boardColor: "black" | "white" }) {
  const imgSrc = pluginBoardImagePath(plugin, boardColor === "white" ? "light" : "dark");

  return (
    <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.pluginCard}>
      <div className={styles.pluginCardImage}>
        <img
          src={imgSrc}
          alt={`${plugin.name} displayed on a split-flap board`}
          loading="lazy"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = "none";
          }}
        />
      </div>
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
    </Link>
  );
}

export default function PluginDirectory(): ReactNode {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [boardColor, setBoardColor] = useState<"black" | "white">("black");

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
      description="Browse all FiestaBoard plugins — weather, stocks, transit, sports, art, and more. Explore what's available for your split-flap display."
    >
      <main className={styles.directoryPage}>
        <div className="container">
          {/* Header */}
          <div className={styles.header}>
            <Heading as="h1" className={styles.title}>
              Plugin Directory
            </Heading>
            <p className={styles.subtitle}>
              Explore {plugins.length} plugins for your split-flap display — from weather and stocks to Disney park wait
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

          {/* Results */}
          {filtered.length > 0 ? (
            <div className={styles.pluginGrid}>
              {filtered.map((plugin) => (
                <PluginCard key={plugin.id} plugin={plugin} boardColor={boardColor} />
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

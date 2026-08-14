import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import { Box, Button, EmptyState, Flex, Input, PluginCard, Text } from "@fiestaboard/ui";
import type { PluginEntry } from "@site/src/plugin-data";
import { CATEGORIES, CATEGORY_LABELS, pluginPreviews, plugins } from "@site/src/plugin-data";
import Layout from "@theme/Layout";
import clsx from "clsx";
import { SearchX } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import styles from "./index.module.css";

function DirectoryCard({ plugin }: { plugin: PluginEntry }) {
  const { colorMode } = useColorMode();
  const teaser = pluginPreviews[plugin.id]?.teaser ?? plugin.name;

  return (
    <PluginCard
      name={plugin.name}
      description={plugin.description}
      authorLabel={`by ${plugin.author}`}
      category={plugin.category}
      categoryLabel={CATEGORY_LABELS[plugin.category] ?? plugin.category}
      teaser={teaser}
      boardType={colorMode === "dark" ? "black" : "white"}
      renderLink={({ className, children }) => (
        <Link to={`/plugins/detail?id=${plugin.id}`} className={className}>
          {children}
        </Link>
      )}
    />
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
                <DirectoryCard key={plugin.id} plugin={plugin} />
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

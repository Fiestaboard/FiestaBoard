import Link from "@docusaurus/Link";
import { Badge, Box, Button, Heading, List, ListItem, StaticBoardDisplay, Text } from "@fiestaboard/ui";
import type { PluginEntry } from "@site/src/plugin-data";
import {
  CATEGORY_LABELS as REGISTRY_CATEGORY_LABELS,
  pluginBoardImagePath,
  pluginPreviews,
  plugins,
  previewMessage,
} from "@site/src/plugin-data";
import Layout from "@theme/Layout";
import * as Icons from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import styles from "./stats.module.css";

interface PluginStat {
  id: string;
  name: string;
  category: string;
  description: string;
  version: string | null;
  created_at: string | null;
  updated_at: string | null;
  // null when GitHub exposes no traffic data for the repo (community-hosted
  // plugins outside the Fiestaboard org — the traffic API needs push access).
  clones_14d_count: number | null;
  clones_14d_uniques: number | null;
}

interface StatsData {
  generated_at: string;
  window_days: number;
  plugins: PluginStat[];
}

const CATEGORY_LABELS = REGISTRY_CATEGORY_LABELS;

const pluginById = new Map<string, PluginEntry>(plugins.map((p) => [p.id, p]));

function PluginIcon({ name, size = 24 }: { name: string; size?: number }) {
  const key = name
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("");
  const Icon = (Icons as unknown as Record<string, React.ComponentType<{ size?: number }>>)[key];
  if (!Icon) return null;
  return <Icon size={size} />;
}

function StatStrip({ items }: { items: { value: string | number; label: string }[] }) {
  return (
    <Box className={styles.statStrip}>
      {items.map((item, i) => (
        <Box key={i} className={styles.statStripItem}>
          <Text as="span" className={styles.statStripValue}>
            {item.value}
          </Text>
          <Text as="span" className={styles.statStripLabel}>
            {item.label}
          </Text>
        </Box>
      ))}
    </Box>
  );
}

function BarRow({ plugin, max }: { plugin: PluginStat; max: number }) {
  const uniques = plugin.clones_14d_uniques ?? 0;
  const pct = max > 0 ? (uniques / max) * 100 : 0;
  return (
    <Box className={styles.barRow}>
      <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.barName}>
        {plugin.name}
      </Link>
      <Box className={styles.barTrack}>
        <Box className={styles.barFill} style={{ width: `${pct}%` }} />
      </Box>
      <Text as="span" className={styles.barValue}>
        {uniques.toLocaleString()}
      </Text>
    </Box>
  );
}

function TopPluginSpotlight({
  plugin,
  entry,
  windowDays,
}: {
  plugin: PluginStat;
  entry: PluginEntry;
  windowDays: number;
}) {
  const preview = pluginPreviews[plugin.id]?.previews[0];
  // Backwards compat: no previews entry yet -> legacy screenshot -> icon.
  const [imgOk, setImgOk] = useState(true);

  return (
    <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.spotlight}>
      {preview ? (
        <Box className={styles.spotlightBoard}>
          <StaticBoardDisplay
            message={previewMessage(preview)}
            size="sm"
            boardType="black"
            deviceType={preview.device_type ?? "flagship"}
            notesWide={preview.notes_wide ?? 1}
            notesTall={preview.notes_tall ?? 1}
            previewLabel={`${plugin.name} on a split-flap board`}
          />
        </Box>
      ) : imgOk ? (
        <img
          className={styles.spotlightImage}
          src={pluginBoardImagePath(entry, "dark")}
          alt={`${plugin.name} on a split-flap board`}
          loading="lazy"
          onError={() => setImgOk(false)}
        />
      ) : (
        <Box className={styles.spotlightImagePlaceholder}>
          <PluginIcon name={entry.icon} size={32} />
        </Box>
      )}
      <Box className={styles.spotlightFooter}>
        <Box className={styles.spotlightIcon}>
          <PluginIcon name={entry.icon} size={20} />
        </Box>
        <Box className={styles.spotlightBody}>
          <Box className={styles.spotlightName}>{plugin.name}</Box>
          <Box className={styles.spotlightStat}>
            {(plugin.clones_14d_uniques ?? 0).toLocaleString()} unique cloners in the last {windowDays} days
          </Box>
        </Box>
        <Badge variant="secondary" className={styles.spotlightBadge}>
          Most popular
        </Badge>
      </Box>
    </Link>
  );
}

const RANKING_PREVIEW = 15;

export default function StatsPage(): ReactNode {
  const [data, setData] = useState<StatsData | null>(null);
  const [error, setError] = useState(false);
  const [showAllRanking, setShowAllRanking] = useState(false);

  useEffect(() => {
    fetch("/plugin-stats.json")
      .then((r) => {
        if (!r.ok) throw new Error("not ok");
        return r.json();
      })
      .then(setData)
      .catch(() => setError(true));
  }, []);

  // Plugins with null traffic (community-hosted repos GitHub exposes no
  // traffic data for) stay in the directory sections below but are excluded
  // from the popularity ranking and totals — "unknown" is not "zero".
  const ranked = data
    ? data.plugins
        .filter((p) => p.clones_14d_uniques != null)
        .sort((a, b) => (b.clones_14d_uniques ?? 0) - (a.clones_14d_uniques ?? 0))
    : [];

  const topPlugin = ranked[0];
  const totalUniques = ranked.reduce((s, p) => s + (p.clones_14d_uniques ?? 0), 0);
  const maxUniques = topPlugin?.clones_14d_uniques ?? 1;
  const hiddenFromRanking = data ? data.plugins.length - ranked.length : 0;
  const displayedPlugins = showAllRanking ? ranked : ranked.slice(0, RANKING_PREVIEW);

  const byCategory = data
    ? Object.entries(
        data.plugins.reduce<Record<string, number>>((acc, p) => {
          acc[p.category] = (acc[p.category] ?? 0) + (p.clones_14d_uniques ?? 0);
          return acc;
        }, {}),
      ).sort(([, a], [, b]) => b - a)
    : [];

  const recentlyAdded = data
    ? [...data.plugins]
        .filter((p) => p.created_at)
        .sort((a, b) => new Date(b.created_at!).getTime() - new Date(a.created_at!).getTime())
        .slice(0, 6)
    : [];

  const recentlyUpdated = data
    ? [...data.plugins]
        .filter((p) => p.updated_at && p.version)
        .sort((a, b) => new Date(b.updated_at!).getTime() - new Date(a.updated_at!).getTime())
        .slice(0, 6)
    : [];

  const generatedAt = data
    ? new Date(data.generated_at).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : null;

  return (
    <Layout
      title="Plugin Stats"
      description="Live popularity and activity stats for all FiestaBoard plugins, updated daily from GitHub."
    >
      <Box as="main" className={styles.page}>
        <Box className="container">
          <Box className={styles.header}>
            <h1>Plugin Stats</h1>
            <Text className={styles.subtitle}>
              Popularity across all {data ? data.plugins.length : "…"} FiestaBoard plugins, updated daily.
            </Text>
          </Box>

          {error && <Text className={styles.error}>Stats are unavailable right now - check back soon.</Text>}

          {!data && !error && <Box className={styles.loading}>Loading…</Box>}

          {data && (
            <>
              <Box className={styles.dashboard}>
                <Box className={styles.dashboardLeft}>
                  <StatStrip
                    items={[
                      { value: data.plugins.length, label: "plugins" },
                      {
                        value: totalUniques.toLocaleString(),
                        label: `unique cloners (last ${data.window_days} days)`,
                      },
                    ]}
                  />
                  {topPlugin &&
                    (() => {
                      const entry = pluginById.get(topPlugin.id);
                      return entry ? (
                        <TopPluginSpotlight plugin={topPlugin} entry={entry} windowDays={data.window_days} />
                      ) : null;
                    })()}
                </Box>

                <Box as="section" className={styles.dashboardRight}>
                  <Heading level={2}>Popularity ranking</Heading>
                  <Text className={styles.sectionNote}>
                    Unique cloners in the last {data.window_days} days
                    {hiddenFromRanking > 0 &&
                      ` - ${hiddenFromRanking} community-hosted ${hiddenFromRanking === 1 ? "plugin doesn't" : "plugins don't"} expose clone data and ${hiddenFromRanking === 1 ? "is" : "are"} not ranked`}
                  </Text>
                  <Box className={styles.barChart}>
                    {displayedPlugins.map((plugin) => (
                      <BarRow key={plugin.id} plugin={plugin} max={maxUniques} />
                    ))}
                  </Box>
                  {ranked.length > RANKING_PREVIEW && (
                    <Button
                      variant="ghost"
                      className={styles.showMoreBtn}
                      onClick={() => setShowAllRanking(!showAllRanking)}
                    >
                      {showAllRanking ? "Show fewer" : `Show all ${ranked.length} plugins`}
                    </Button>
                  )}
                </Box>
              </Box>

              <Box as="section" className={styles.section}>
                <Heading level={2}>By category</Heading>
                <Text className={styles.sectionNote}>
                  Sum of per-plugin unique cloners by category, last {data.window_days} days - users cloning multiple
                  plugins in the same category are counted once per plugin
                </Text>
                <Box className={styles.categoryGrid}>
                  {byCategory.map(([cat, count]) => (
                    <Box key={cat} className={styles.categoryCard}>
                      <Box className={styles.categoryCount}>{count.toLocaleString()}</Box>
                      <Box className={styles.categoryName}>{CATEGORY_LABELS[cat] ?? cat}</Box>
                    </Box>
                  ))}
                </Box>
              </Box>

              <Box as="section" className={styles.section}>
                <Box className={styles.recentColumns}>
                  <Box>
                    <Heading level={2}>Recently added</Heading>
                    <List gap="0" className={styles.recentList}>
                      {recentlyAdded.map((p) => (
                        <ListItem key={p.id} className={styles.recentItem}>
                          <Link to={`/plugins/detail?id=${p.id}`}>{p.name}</Link>
                          <Text as="span" className={styles.recentMeta}>
                            <Text as="span" className={styles.recentCategory}>
                              {CATEGORY_LABELS[p.category] ?? p.category}
                            </Text>
                            <Text as="span" className={styles.recentDate}>
                              {new Date(p.created_at!).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })}
                            </Text>
                          </Text>
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                  <Box>
                    <Heading level={2}>Recently updated</Heading>
                    <List gap="0" className={styles.recentList}>
                      {recentlyUpdated.map((p) => (
                        <ListItem key={p.id} className={styles.recentItem}>
                          <Link to={`/plugins/detail?id=${p.id}`}>{p.name}</Link>
                          <Text as="span" className={styles.recentMeta}>
                            <Text as="span" className={styles.recentCategory}>
                              {CATEGORY_LABELS[p.category] ?? p.category}
                            </Text>
                            <Text as="span" className={styles.recentVersion}>
                              v{p.version}
                            </Text>
                            <Text as="span" className={styles.recentDate}>
                              {new Date(p.updated_at!).toLocaleDateString("en-US", {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })}
                            </Text>
                          </Text>
                        </ListItem>
                      ))}
                    </List>
                  </Box>
                </Box>
              </Box>

              <Text className={styles.freshness}>
                Data refreshed {generatedAt}. Clone counts reflect the {data.window_days}-day window provided by the
                GitHub Traffic API and include automated traffic such as fleet auto-updates and the weekly security
                scan.
              </Text>
            </>
          )}
        </Box>
      </Box>
    </Layout>
  );
}

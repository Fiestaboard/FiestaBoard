import {useState, useEffect, type ReactNode} from 'react';
import * as Icons from 'lucide-react';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import {plugins, pluginBoardImagePath, CATEGORY_LABELS as REGISTRY_CATEGORY_LABELS} from '@site/src/plugin-data';
import type {PluginEntry} from '@site/src/plugin-data';
import styles from './stats.module.css';

interface PluginStat {
  id: string;
  name: string;
  category: string;
  description: string;
  version: string | null;
  created_at: string | null;
  updated_at: string | null;
  clones_14d_count: number;
  clones_14d_uniques: number;
}

interface StatsData {
  generated_at: string;
  window_days: number;
  plugins: PluginStat[];
}

const CATEGORY_LABELS = REGISTRY_CATEGORY_LABELS;

const pluginById = new Map<string, PluginEntry>(plugins.map((p) => [p.id, p]));

function PluginIcon({name, size = 24}: {name: string; size?: number}) {
  const key = name.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join('');
  const Icon = (Icons as Record<string, React.ComponentType<{size?: number}>>)[key];
  if (!Icon) return null;
  return <Icon size={size} />;
}

function StatStrip({items}: {items: {value: string | number; label: string}[]}) {
  return (
    <div className={styles.statStrip}>
      {items.map((item, i) => (
        <div key={i} className={styles.statStripItem}>
          <span className={styles.statStripValue}>{item.value}</span>
          <span className={styles.statStripLabel}>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function BarRow({plugin, max}: {plugin: PluginStat; max: number}) {
  const pct = max > 0 ? (plugin.clones_14d_uniques / max) * 100 : 0;
  return (
    <div className={styles.barRow}>
      <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.barName}>
        {plugin.name}
      </Link>
      <div className={styles.barTrack}>
        <div className={styles.barFill} style={{width: `${pct}%`}} />
      </div>
      <span className={styles.barValue}>{plugin.clones_14d_uniques.toLocaleString()}</span>
    </div>
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
  const [imgOk, setImgOk] = useState(true);
  const imgSrc = pluginBoardImagePath(entry, 'dark');

  return (
    <Link to={`/plugins/detail?id=${plugin.id}`} className={styles.spotlight}>
      {imgOk ? (
        <img
          className={styles.spotlightImage}
          src={imgSrc}
          alt={`${plugin.name} on a split-flap board`}
          loading="lazy"
          onError={() => setImgOk(false)}
        />
      ) : (
        <div className={styles.spotlightImagePlaceholder}>
          <PluginIcon name={entry.icon} size={32} />
        </div>
      )}
      <div className={styles.spotlightFooter}>
        <div className={styles.spotlightIcon}>
          <PluginIcon name={entry.icon} size={20} />
        </div>
        <div className={styles.spotlightBody}>
          <div className={styles.spotlightName}>{plugin.name}</div>
          <div className={styles.spotlightStat}>
            {plugin.clones_14d_uniques.toLocaleString()} unique installs in the last {windowDays} days
          </div>
        </div>
        <div className={styles.spotlightBadge}>Most popular</div>
      </div>
    </Link>
  );
}

const RANKING_PREVIEW = 15;

export default function StatsPage(): ReactNode {
  const [data, setData] = useState<StatsData | null>(null);
  const [error, setError] = useState(false);
  const [showAllRanking, setShowAllRanking] = useState(false);

  useEffect(() => {
    fetch('/plugin-stats.json')
      .then((r) => {
        if (!r.ok) throw new Error('not ok');
        return r.json();
      })
      .then(setData)
      .catch(() => setError(true));
  }, []);

  const sorted = data
    ? [...data.plugins].sort((a, b) => b.clones_14d_uniques - a.clones_14d_uniques)
    : [];

  const topPlugin = sorted[0];
  const totalUniques = sorted.reduce((s, p) => s + p.clones_14d_uniques, 0);
  const maxUniques = topPlugin?.clones_14d_uniques ?? 1;
  const displayedPlugins = showAllRanking ? sorted : sorted.slice(0, RANKING_PREVIEW);

  const byCategory = data
    ? Object.entries(
        data.plugins.reduce<Record<string, number>>((acc, p) => {
          acc[p.category] = (acc[p.category] ?? 0) + p.clones_14d_uniques;
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
    ? new Date(data.generated_at).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  return (
    <Layout
      title="Plugin Stats"
      description="Live popularity and activity stats for all FiestaBoard plugins, updated daily from GitHub.">
      <main className={styles.page}>
        <div className="container">
          <div className={styles.header}>
            <Heading as="h1">Plugin Stats</Heading>
            <p className={styles.subtitle}>
              Popularity across all {data ? data.plugins.length : '—'} FiestaBoard plugins,
              updated daily.
            </p>
          </div>

          {error && (
            <p className={styles.error}>Stats are unavailable right now — check back soon.</p>
          )}

          {!data && !error && <div className={styles.loading}>Loading…</div>}

          {data && (
            <>
              <div className={styles.dashboard}>
                <div className={styles.dashboardLeft}>
                  <StatStrip items={[
                    {value: data.plugins.length, label: 'plugins'},
                    {value: totalUniques.toLocaleString(), label: `unique installs (last ${data.window_days} days)`},
                  ]} />
                  {topPlugin && (() => {
                    const entry = pluginById.get(topPlugin.id);
                    return entry ? <TopPluginSpotlight plugin={topPlugin} entry={entry} windowDays={data.window_days} /> : null;
                  })()}
                </div>

                <section className={styles.dashboardRight}>
                  <Heading as="h2">Popularity ranking</Heading>
                  <p className={styles.sectionNote}>
                    Unique cloners in the last {data.window_days} days
                  </p>
                  <div className={styles.barChart}>
                    {displayedPlugins.map((plugin) => (
                      <BarRow key={plugin.id} plugin={plugin} max={maxUniques} />
                    ))}
                  </div>
                  {sorted.length > RANKING_PREVIEW && (
                    <button
                      className={styles.showMoreBtn}
                      onClick={() => setShowAllRanking(!showAllRanking)}>
                      {showAllRanking ? 'Show fewer' : `Show all ${sorted.length} plugins`}
                    </button>
                  )}
                </section>
              </div>

              <section className={styles.section}>
                <Heading as="h2">By category</Heading>
                <p className={styles.sectionNote}>
                  Sum of per-plugin installs by category, last {data.window_days} days — users
                  installing multiple plugins in the same category are counted once per plugin
                </p>
                <div className={styles.categoryGrid}>
                  {byCategory.map(([cat, count]) => (
                    <div key={cat} className={styles.categoryCard}>
                      <div className={styles.categoryCount}>{count.toLocaleString()}</div>
                      <div className={styles.categoryName}>{CATEGORY_LABELS[cat] ?? cat}</div>
                    </div>
                  ))}
                </div>
              </section>

              <section className={styles.section}>
                <div className={styles.recentColumns}>
                  <div>
                    <Heading as="h2">Recently added</Heading>
                    <ul className={styles.recentList}>
                      {recentlyAdded.map((p) => (
                        <li key={p.id} className={styles.recentItem}>
                          <Link to={`/plugins/detail?id=${p.id}`}>{p.name}</Link>
                          <span className={styles.recentMeta}>
                            <span className={styles.recentCategory}>
                              {CATEGORY_LABELS[p.category] ?? p.category}
                            </span>
                            <span className={styles.recentDate}>
                              {new Date(p.created_at!).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric',
                              })}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <Heading as="h2">Recently updated</Heading>
                    <ul className={styles.recentList}>
                      {recentlyUpdated.map((p) => (
                        <li key={p.id} className={styles.recentItem}>
                          <Link to={`/plugins/detail?id=${p.id}`}>{p.name}</Link>
                          <span className={styles.recentMeta}>
                            <span className={styles.recentCategory}>
                              {CATEGORY_LABELS[p.category] ?? p.category}
                            </span>
                            <span className={styles.recentVersion}>v{p.version}</span>
                            <span className={styles.recentDate}>
                              {new Date(p.updated_at!).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: 'numeric',
                              })}
                            </span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>

              <p className={styles.freshness}>
                Data refreshed {generatedAt}. Clone counts reflect the{' '}
                {data.window_days}-day window provided by the GitHub Traffic API.
              </p>
            </>
          )}
        </div>
      </main>
    </Layout>
  );
}

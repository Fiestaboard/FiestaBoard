import Link from "@docusaurus/Link";
import { type GlobalVersion, useLatestVersion, useVersions } from "@docusaurus/plugin-content-docs/client";
import { Box, Button, Flex, Heading, Table, TableBody, TableCell, TableRow, Text, TextLink } from "@fiestaboard/ui";
import allVersions from "@site/versions.json";
import Layout from "@theme/Layout";
import type { ReactNode } from "react";

import styles from "./versions.module.css";

/**
 * Full documentation-versions index (linked from the footer).
 *
 * The version switcher lives here rather than in the navbar - visitors should
 * land on the latest docs; this page is for the rare case of looking up an
 * older version.
 *
 * Only the most recent versions are hosted on the site (the build caps how many
 * version snapshots compile, to keep the deploy from running out of memory).
 * Older snapshots are archived: their URLs redirect to the latest docs, but the
 * original markdown is preserved in the repo, so we link those to their source
 * on GitHub.
 */
const REPO = "https://github.com/Fiestaboard/FiestaBoard";
const VERSIONED_DOCS = `${REPO}/tree/main/docs-site/versioned_docs`;

/**
 * Entry route for a version. `version.path` is the version's base URL (`/docs`
 * for the latest), which is only a real route when a doc declares `slug: /` -  * ours doesn't, so link to the version's main doc instead. Bare `/docs` fails
 * the `onBrokenLinks: "throw"` build check.
 */
function versionEntryPath(version: GlobalVersion): string {
  return version.docs.find((doc) => doc.id === version.mainDocId)?.path ?? version.path;
}

export default function Versions(): ReactNode {
  const hosted = useVersions("default");
  const latest = useLatestVersion("default");
  const hostedNames = new Set(hosted.map((v) => v.name));

  const maintained = hosted.filter((v) => v !== latest);
  const archived = allVersions.filter((name) => !hostedNames.has(name));

  // Group archived versions by major for a compact, scannable index.
  const archivedByMajor = new Map<string, string[]>();
  for (const name of archived) {
    const major = name.split(".")[0];
    const list = archivedByMajor.get(major) ?? [];
    list.push(name);
    archivedByMajor.set(major, list);
  }
  const majors = [...archivedByMajor.keys()].sort((a, b) => Number(b) - Number(a));

  return (
    <Layout title="Versions" description="Browse every version of the FiestaBoard documentation.">
      <Box as="main" className="container margin-vert--lg">
        <h1>FiestaBoard documentation versions</h1>
        <Text size="base">
          We recommend the{" "}
          <Text as="span" size="base" weight="semibold">
            latest
          </Text>{" "}
          version - it has the newest features and fixes, and it&apos;s what the docs default to. Every released version
          is listed below.
        </Text>

        <Heading level={2}>Current version</Heading>
        <Flex align="center" justify="between" gap="4" wrap className={styles.currentCard}>
          <Box>
            <Text as="span" className={styles.currentLabel}>
              {latest.label}
            </Text>
            <Text as="span" className={styles.currentTag}>
              recommended
            </Text>
          </Box>
          <Button asChild>
            <Link to={versionEntryPath(latest)}>Read the docs</Link>
          </Button>
        </Flex>

        {maintained.length > 0 && (
          <Box className={styles.section}>
            <Heading level={2}>Maintained versions</Heading>
            <Text className={styles.note}>Previous versions still hosted on the site, with full browsable docs.</Text>
            <Table>
              <TableBody>
                {maintained.map((version) => (
                  <TableRow key={version.name}>
                    <TableCell>{version.label}</TableCell>
                    <TableCell>
                      <Link to={versionEntryPath(version)}>Documentation</Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}

        {archived.length > 0 && (
          <Box className={styles.section}>
            <Heading level={2}>Archived versions</Heading>
            <Text className={styles.note}>
              No longer hosted - these {archived.length} snapshots redirect to the latest docs, but the original
              markdown is preserved in the repository. Follow a version to read its docs source on GitHub.
            </Text>
            {majors.map((major) => (
              <Box key={major} className={styles.archivedGroup}>
                <Text className={styles.archivedMajor}>{major}.x</Text>
                <Flex wrap gap="2">
                  {archivedByMajor.get(major)!.map((name) => (
                    <TextLink key={name} className={styles.chip} href={`${VERSIONED_DOCS}/version-${name}`}>
                      {name}
                    </TextLink>
                  ))}
                </Flex>
              </Box>
            ))}
          </Box>
        )}
      </Box>
    </Layout>
  );
}

import Link from "@docusaurus/Link";
import { useLatestVersion, useVersions } from "@docusaurus/plugin-content-docs/client";
import { Table, TableBody, TableCell, TableRow } from "@fiestaboard/ui";
import Layout from "@theme/Layout";
import type { ReactNode } from "react";

/**
 * Standalone documentation-versions page (linked from the footer).
 *
 * The version switcher deliberately lives here rather than in the navbar —
 * visitors should land on the latest docs; this page is for the rare case of
 * looking up an older version.
 */
export default function Versions(): ReactNode {
  const versions = useVersions("default");
  const latest = useLatestVersion("default");
  const pastVersions = versions.filter((version) => version !== latest);

  return (
    <Layout title="Versions" description="FiestaBoard documentation versions">
      <main className="container margin-vert--lg">
        <h1>FiestaBoard documentation versions</h1>
        <p>
          We recommend the <strong>latest</strong> version — it has the newest features and fixes, and it&apos;s what
          the docs default to. Older versions are kept here for reference.
        </p>

        <h2>Latest version</h2>
        <Table>
          <TableBody>
            <TableRow>
              <TableCell>{latest.label}</TableCell>
              <TableCell>
                <Link to={latest.path}>Documentation</Link>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>

        {pastVersions.length > 0 && (
          <>
            <h2>Past versions</h2>
            <Table>
              <TableBody>
                {pastVersions.map((version) => (
                  <TableRow key={version.name}>
                    <TableCell>{version.label}</TableCell>
                    <TableCell>
                      <Link to={version.path}>Documentation</Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </main>
    </Layout>
  );
}

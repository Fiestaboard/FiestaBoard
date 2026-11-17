import { Box, Card, Heading, ListRow, ListRowGroup, Prose, Skeleton, Stack, Text, TextLink } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useTranslations } from "@/i18n/translations";
import { fetchPluginReadme, rewriteMarkdownImageUrls, rewriteMarkdownRepoLinks } from "@/lib/github";

/** One renderer for installed detail and Marketplace: preserve the resolved
 * repository branch for both image and document URLs, and let kit Prose own type. */
export function IntegrationReadme({
  pluginId,
  repository = "",
  branch = "",
  documentation,
  version,
  author,
}: {
  pluginId: string;
  repository?: string;
  branch?: string;
  documentation?: string | null;
  version?: string;
  author?: string;
}) {
  const t = useTranslations("integrations");
  const { data: remote, isLoading } = useQuery({
    queryKey: ["plugin-remote-readme", pluginId, repository, branch],
    queryFn: () => fetchPluginReadme(repository, branch),
    enabled: !!repository && !documentation,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });
  const markdown = documentation || remote?.markdown;
  const resolvedBranch = remote?.resolvedBranch || branch || "main";
  const readme = markdown
    ? rewriteMarkdownRepoLinks(
        rewriteMarkdownImageUrls(markdown, repository, resolvedBranch),
        repository,
        resolvedBranch,
      )
    : null;
  return (
    <Box className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(15rem,0.4fr)]">
      <Card className="min-w-0 p-5 sm:p-7">
        {readme ? (
          <Prose headingOffset={1} className="max-w-none overflow-x-auto">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children, ...props }) => (
                  <TextLink href={href} target="_blank" rel="noopener noreferrer" {...props}>
                    {children}
                  </TextLink>
                ),
                h1: ({ children }) => (
                  <Heading level={3} size="xl">
                    {children}
                  </Heading>
                ),
                h2: ({ children }) => (
                  <Heading level={4} size="lg">
                    {children}
                  </Heading>
                ),
                h3: ({ children }) => (
                  <Heading level={4} size="base">
                    {children}
                  </Heading>
                ),
              }}
            >
              {readme}
            </ReactMarkdown>
          </Prose>
        ) : isLoading ? (
          <Stack gap="3">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </Stack>
        ) : (
          <Text tone="muted">{t("readmeUnavailable")}</Text>
        )}
      </Card>
      <Card role="region" aria-label={t("about")} className="min-w-0 p-5">
        <Heading level={3} size="lg">
          {t("about")}
        </Heading>
        <ListRowGroup variant="plain" className="mt-3">
          {version && <ListRow title={t("versionLabel")} meta={version} />}
          {author && <ListRow title={t("authorLabel")} meta={author} />}
          {repository && (
            <ListRow
              title={t("sourceLabel")}
              meta={
                <TextLink href={repository} target="_blank" rel="noopener noreferrer" className="break-all">
                  {repository.replace(/^https?:\/\//, "").replace(/\.git$/, "")}
                </TextLink>
              }
            />
          )}
        </ListRowGroup>
      </Card>
    </Box>
  );
}

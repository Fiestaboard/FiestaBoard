import {
  Badge,
  Box,
  Button,
  Code,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Heading,
  Input,
  Label,
  List,
  PageLayout,
  Skeleton,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowLeft, CopyPlus, ExternalLink, Puzzle } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import Link from "@/components/smart-link";
import { useParams, useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { fetchPluginReadme, rewriteMarkdownImageUrls, rewriteMarkdownRepoLinks } from "@/lib/github";
import { cn } from "@/lib/utils";

export default function PluginDetailPage() {
  const t = useTranslations("pluginDetail");
  const tCommon = useTranslations("common");
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const pluginId = params.pluginId as string;
  const [addInstanceOpen, setAddInstanceOpen] = useState(false);
  const [instanceLabel, setInstanceLabel] = useState("");
  const [isCreatingInstance, setIsCreatingInstance] = useState(false);

  const CATEGORY_LABELS: Record<string, string> = {
    art: t("categories.art"),
    data: t("categories.data"),
    entertainment: t("categories.entertainment"),
    finance: t("categories.finance"),
    home: t("categories.home"),
    transit: t("categories.transit"),
    utility: t("categories.utility"),
    weather: t("categories.weather"),
  };

  // Find the registry entry for this plugin
  const { data: registryData, isLoading: isLoadingRegistry } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
  });

  const entry = registryData?.entries.find((e) => e.id === pluginId);
  const repoUrl = entry?.repository ?? "";

  // Fetch README from GitHub raw CDN (registry branch, or main/master fallback)
  const { data: readmeRaw, isLoading: isLoadingReadme } = useQuery({
    queryKey: ["plugin-remote-readme", pluginId, entry?.branch ?? ""],
    queryFn: () => fetchPluginReadme(repoUrl, entry?.branch ?? ""),
    enabled: !!repoUrl,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  const readme = readmeRaw
    ? rewriteMarkdownRepoLinks(
        rewriteMarkdownImageUrls(readmeRaw.markdown, repoUrl, readmeRaw.resolvedBranch),
        repoUrl,
        readmeRaw.resolvedBranch,
      )
    : null;
  const categoryLabel = CATEGORY_LABELS[entry?.category ?? "utility"] ?? entry?.category ?? t("categories.utility");

  // Install mutation
  const installMutation = useMutation({
    mutationFn: async () => {
      await api.installRegistryPlugin(pluginId);
      await api.enablePlugin(pluginId);
    },
    onSuccess: () => {
      toast.success(t("toastInstalled", { name: entry?.name ?? pluginId }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      router.push("/integrations?tab=installed");
    },
    onError: (err) => {
      toast.error(t("toastInstallFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
    },
  });

  const isInstalled = registryData?.entries.find((e) => e.id === pluginId)?.installed;
  const isLoading = isLoadingRegistry;

  async function handleAddInstance() {
    if (!instanceLabel.trim()) return;
    setIsCreatingInstance(true);
    try {
      await api.createPluginInstance(pluginId, instanceLabel.trim());
      toast.success(t("toastInstanceCreated", { label: instanceLabel }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      setAddInstanceOpen(false);
      setInstanceLabel("");
    } catch (err) {
      toast.error(
        t("toastCreateInstanceFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }),
      );
    } finally {
      setIsCreatingInstance(false);
    }
  }

  return (
    <PageLayout>
      {/* Back navigation */}
      <Box className="mb-4">
        <Button variant="ghost" size="sm" className="gap-1.5 -ml-2 text-muted-foreground hover:text-foreground" asChild>
          <Link href="/integrations?tab=marketplace">
            <ArrowLeft className="h-4 w-4" />
            {t("backToMarketplace")}
          </Link>
        </Button>
      </Box>

      <Stack gap="6" className="max-w-3xl mx-auto animate-card-fade-in">
        {/* Plugin header card */}
        <Box className="rounded-xl border bg-card px-6 py-5">
          <Flex align="start" justify="between" gap="4">
            <Flex align="start" gap="4" className="min-w-0">
              <Box className="p-2.5 rounded-lg bg-muted text-muted-foreground shrink-0 mt-0.5">
                <Puzzle className="h-5 w-5" />
              </Box>
              <Box className="min-w-0">
                {isLoading ? (
                  <>
                    <Skeleton className="h-6 w-48 mb-2" />
                    <Skeleton className="h-4 w-32" />
                  </>
                ) : (
                  <>
                    <Flex align="center" gap="2" wrap className="mb-1">
                      {/* Custom card header (icon + badge + trailing actions) doesn't
                          match PageHeader's shape, so the page h1 stays raw here
                          (couldn't snap — see wave 1 report). */}
                      <h1 className="text-xl font-semibold">{entry?.name ?? pluginId}</h1>
                      <Badge variant="secondary" className="text-xs">
                        {categoryLabel}
                      </Badge>
                    </Flex>
                    <Text tone="muted">
                      {entry?.author && (
                        <Text as="span" tone="muted" className="mr-3">
                          {t("byAuthor", { author: entry.author })}
                        </Text>
                      )}
                      {entry?.fiestaboard_version && (
                        <Text as="span" size="xs" tone="muted">
                          {t("requiresFiestaboard", { version: entry.fiestaboard_version })}
                        </Text>
                      )}
                    </Text>
                  </>
                )}
              </Box>
            </Flex>

            {/* Actions */}
            <Flex align="center" gap="2" className="shrink-0">
              {entry?.repository && (
                <Button variant="outline" size="sm" asChild>
                  {/* asChild hands this anchor Button's own chrome (border/bg/text) — TextLink's
                      underline+text-primary styling would clash with that, so it stays raw
                      (couldn't snap — see wave 1 report). */}
                  <a href={entry.repository} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                    GitHub
                  </a>
                </Button>
              )}
              {!isLoading &&
                (isInstalled ? (
                  <Button size="sm" variant="outline" onClick={() => setAddInstanceOpen(true)}>
                    <CopyPlus className="h-3.5 w-3.5 mr-1.5" />
                    {t("addInstance")}
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => installMutation.mutate()} disabled={installMutation.isPending}>
                    <ArrowDownToLine
                      className={cn("h-3.5 w-3.5 mr-1.5", installMutation.isPending && "animate-bounce")}
                    />
                    {installMutation.isPending ? t("installing") : t("install")}
                  </Button>
                ))}
            </Flex>
          </Flex>

          {/* Description */}
          {entry?.description && (
            <Text tone="muted" className="mt-4 leading-relaxed border-t pt-4">
              {entry.description}
            </Text>
          )}
        </Box>

        {/* README */}
        <Box className="rounded-xl border bg-card px-6 py-5">
          {isLoadingReadme ? (
            <Stack gap="3">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
              <Skeleton className="h-5 w-1/4 mt-6" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </Stack>
          ) : readme ? (
            <Box className="plugin-readme">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children, ...props }) => (
                    <TextLink href={href} target="_blank" rel="noopener noreferrer" {...props}>
                      {children}
                    </TextLink>
                  ),
                  img: ({ src, alt, ...props }) => (
                    <img src={src} alt={alt ?? ""} className="rounded-lg max-h-64 w-auto my-3" {...props} />
                  ),
                  pre: ({ children, ...props }) => (
                    <pre className="bg-muted rounded-lg p-4 overflow-x-auto text-xs my-4" {...props}>
                      {children}
                    </pre>
                  ),
                  code: ({ children, className, ...props }) => {
                    const isBlock = className?.startsWith("language-");
                    return isBlock ? (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    ) : (
                      <Code {...props}>{children}</Code>
                    );
                  },
                  table: ({ children, ...props }) => (
                    <Table className="text-xs border-collapse my-4" {...props}>
                      {children}
                    </Table>
                  ),
                  thead: ({ children, ...props }) => (
                    <TableHeader className="bg-muted/50" {...props}>
                      {children}
                    </TableHeader>
                  ),
                  tbody: ({ children, ...props }) => <TableBody {...props}>{children}</TableBody>,
                  tr: ({ children, ...props }) => <TableRow {...props}>{children}</TableRow>,
                  th: ({ children, ...props }) => (
                    <TableHead className="border border-border text-left" {...props}>
                      {children}
                    </TableHead>
                  ),
                  td: ({ children, ...props }) => (
                    <TableCell className="border border-border" {...props}>
                      {children}
                    </TableCell>
                  ),
                  h1: ({ children, ...props }) => (
                    // Markdown README content — h1 here is document structure, not the app
                    // page's own title, so PageHeader doesn't fit; stays raw (couldn't snap).
                    <h1 className="text-xl font-bold mt-0 mb-4 pb-2 border-b" {...props}>
                      {children}
                    </h1>
                  ),
                  h2: ({ children, ...props }) => (
                    <Heading level={2} className="mt-6 mb-2" {...props}>
                      {children}
                    </Heading>
                  ),
                  h3: ({ children, ...props }) => (
                    <Heading level={3} size="sm" className="mt-4 mb-1.5" {...props}>
                      {children}
                    </Heading>
                  ),
                  p: ({ children, ...props }) => (
                    <Text tone="muted" className="leading-relaxed mb-3" {...props}>
                      {children}
                    </Text>
                  ),
                  ul: ({ children, ...props }) => (
                    <List marker="disc" gap="1" className="list-inside mb-3 text-sm text-muted-foreground" {...props}>
                      {children}
                    </List>
                  ),
                  ol: ({ children, ...props }) => (
                    <List
                      as="ol"
                      marker="decimal"
                      gap="1"
                      className="list-inside mb-3 text-sm text-muted-foreground"
                      {...props}
                    >
                      {children}
                    </List>
                  ),
                  blockquote: ({ children, ...props }) => (
                    <blockquote
                      className="border-l-2 border-border pl-4 italic text-muted-foreground text-sm my-3"
                      {...props}
                    >
                      {children}
                    </blockquote>
                  ),
                  hr: () => <hr className="border-border my-5" />,
                  strong: ({ children, ...props }) => (
                    <Text as="span" weight="semibold" {...props}>
                      {children}
                    </Text>
                  ),
                }}
              >
                {readme}
              </ReactMarkdown>
            </Box>
          ) : (
            <Text tone="muted" className="italic">
              {t("documentationNotAvailable")}
            </Text>
          )}
        </Box>
      </Stack>

      <Dialog open={addInstanceOpen} onOpenChange={setAddInstanceOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("addInstance")} of {entry?.name ?? pluginId}
            </DialogTitle>
            <DialogDescription>{t("addInstanceDescription")}</DialogDescription>
          </DialogHeader>
          <Stack gap="2" className="py-2">
            <Label htmlFor="detail-instance-label">{t("instanceNameLabel")}</Label>
            <Input
              id="detail-instance-label"
              placeholder={t("instanceNamePlaceholder")}
              value={instanceLabel}
              onChange={(e) => setInstanceLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && instanceLabel.trim()) handleAddInstance();
                if (e.key === "Escape") setAddInstanceOpen(false);
              }}
              autoFocus
            />
            <Text size="xs" tone="muted">
              {t("instanceNameHelp")}
            </Text>
          </Stack>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddInstanceOpen(false)} disabled={isCreatingInstance}>
              {tCommon("cancel")}
            </Button>
            <Button onClick={handleAddInstance} disabled={!instanceLabel.trim() || isCreatingInstance}>
              {isCreatingInstance ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}

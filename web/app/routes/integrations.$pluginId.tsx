import {
  BoardShowcase,
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
  PageSection,
  PluginCategoryBadge,
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
import { ArrowDownToLine, CopyPlus, ExternalLink } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { SectionAction } from "@/components/section-shell";
import { useEffectiveBoardColor } from "@/hooks/use-effective-board-color";
import { useEffectiveCode62Glyph } from "@/hooks/use-effective-code62-glyph";
import { useParams, useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { fetchPluginReadme, rewriteMarkdownImageUrls, rewriteMarkdownRepoLinks } from "@/lib/github";
import { cn } from "@/lib/utils";

export default function PluginDetailPage() {
  const t = useTranslations("pluginDetail");
  const tCommon = useTranslations("common");
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const boardColor = useEffectiveBoardColor();
  const code62Glyph = useEffectiveCode62Glyph();
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
    output: t("categories.output"),
    transit: t("categories.transit"),
    transition: t("categories.transition"),
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
  const previews = entry?.previews ?? [];

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
    <>
      {/* The Integrations section (integrations.tsx) names the plugin in the
          breadcrumb and heading above this; its actions sit on that row. */}
      <SectionAction>
        <Flex align="center" gap="2" wrap>
          {entry?.repository && (
            <Button variant="outline" size="sm" asChild>
              {/* asChild hands this anchor Button's own chrome (border/bg/text) — TextLink's
                  underline+text-primary styling would clash with that, so it stays raw
                  (couldn't snap — see wave 1 report). */}
              {/* eslint-disable-next-line react/forbid-elements -- single Slot child of Button asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling */}
              <a href={entry.repository} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                {t("githubLink")}
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
                <ArrowDownToLine className={cn("h-3.5 w-3.5 mr-1.5", installMutation.isPending && "animate-bounce")} />
                {installMutation.isPending ? t("installing") : t("install")}
              </Button>
            ))}
        </Flex>
      </SectionAction>

      <Box {...anchorProps(`plugin.${pluginId}`)}>
        {/* Board hero — what this plugin actually puts on a board, the same
            way the public directory leads at fiestaboard.app/plugins. Absent
            for plugins that predate the previews contract. */}
        {previews.length > 0 && (
          <PageSection>
            <BoardShowcase
              previews={previews}
              previewLabel={t("boardPreviewLabel", { name: entry?.name ?? pluginId })}
              defaultBoardType={boardColor}
              code62Glyph={code62Glyph}
              labels={{
                flagship: t("deviceFlagship"),
                note: t("deviceNote"),
                noteArray: t("deviceNoteArray"),
                boardShape: t("boardShapeLabel"),
                boardColor: t("boardColorLabel"),
                blackBoard: t("blackBoard"),
                whiteBoard: t("whiteBoard"),
              }}
            />
          </PageSection>
        )}

        {/* What it is: category, the version it needs, its own description. */}
        <PageSection>
          {isLoading ? (
            <Stack gap="2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-4 w-2/3" />
            </Stack>
          ) : (
            <Stack gap="3">
              <Flex align="center" gap="3" wrap>
                <PluginCategoryBadge category={entry?.category ?? "utility"} label={categoryLabel} />
                {entry?.fiestaboard_version && (
                  <Text as="span" size="xs" tone="muted">
                    {t("requiresFiestaboard", { version: entry.fiestaboard_version })}
                  </Text>
                )}
              </Flex>
              {entry?.description && (
                <Text tone="muted" className="leading-relaxed">
                  {entry.description}
                </Text>
              )}
            </Stack>
          )}
        </PageSection>

        {/* README */}
        <PageSection>
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
                      // eslint-disable-next-line react/forbid-elements -- react-markdown code-block override must render a native <code> inside <pre>; the Code primitive is used for inline code below
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
                    // eslint-disable-next-line react/forbid-elements -- react-markdown h1 override renders README document structure, not the app page title
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
        </PageSection>
      </Box>

      <Dialog open={addInstanceOpen} onOpenChange={setAddInstanceOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("addInstanceOfTitle", { name: entry?.name ?? pluginId })}</DialogTitle>
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
    </>
  );
}

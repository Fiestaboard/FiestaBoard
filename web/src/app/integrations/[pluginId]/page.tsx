"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowLeft, CopyPlus, ExternalLink, Puzzle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { toast } from "sonner";

import { PageLayout } from "@/components/page-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
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
      <div className="mb-4">
        <Button variant="ghost" size="sm" className="gap-1.5 -ml-2 text-muted-foreground hover:text-foreground" asChild>
          <Link href="/integrations?tab=marketplace">
            <ArrowLeft className="h-4 w-4" />
            {t("backToMarketplace")}
          </Link>
        </Button>
      </div>

      <div className="max-w-3xl mx-auto space-y-6 animate-card-fade-in">
        {/* Plugin header card */}
        <div className="rounded-xl border bg-card px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4 min-w-0">
              <div className="p-2.5 rounded-lg bg-muted text-muted-foreground shrink-0 mt-0.5">
                <Puzzle className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                {isLoading ? (
                  <>
                    <Skeleton className="h-6 w-48 mb-2" />
                    <Skeleton className="h-4 w-32" />
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <h1 className="text-xl font-semibold">{entry?.name ?? pluginId}</h1>
                      <Badge variant="secondary" className="text-xs">
                        {categoryLabel}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {entry?.author && <span className="mr-3">{t("byAuthor", { author: entry.author })}</span>}
                      {entry?.fiestaboard_version && (
                        <span className="text-xs">
                          {t("requiresFiestaboard", { version: entry.fiestaboard_version })}
                        </span>
                      )}
                    </p>
                  </>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 shrink-0">
              {entry?.repository && (
                <Button variant="outline" size="sm" asChild>
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
            </div>
          </div>

          {/* Description */}
          {entry?.description && (
            <p className="mt-4 text-sm text-muted-foreground leading-relaxed border-t pt-4">{entry.description}</p>
          )}
        </div>

        {/* README */}
        <div className="rounded-xl border bg-card px-6 py-5">
          {isLoadingReadme ? (
            <div className="space-y-3">
              <Skeleton className="h-5 w-1/3" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
              <Skeleton className="h-5 w-1/4 mt-6" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : readme ? (
            <div className="plugin-readme">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children, ...props }) => (
                    <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                      {children}
                    </a>
                  ),
                  img: ({ src, alt, ...props }) => (
                    // eslint-disable-next-line @next/next/no-img-element
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
                      <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                        {children}
                      </code>
                    );
                  },
                  table: ({ children, ...props }) => (
                    <div className="overflow-x-auto my-4">
                      <table className="w-full text-xs border-collapse" {...props}>
                        {children}
                      </table>
                    </div>
                  ),
                  thead: ({ children, ...props }) => (
                    <thead className="bg-muted/50" {...props}>
                      {children}
                    </thead>
                  ),
                  th: ({ children, ...props }) => (
                    <th className="border border-border px-3 py-2 text-left font-medium" {...props}>
                      {children}
                    </th>
                  ),
                  td: ({ children, ...props }) => (
                    <td className="border border-border px-3 py-2" {...props}>
                      {children}
                    </td>
                  ),
                  h1: ({ children, ...props }) => (
                    <h1 className="text-xl font-bold mt-0 mb-4 pb-2 border-b" {...props}>
                      {children}
                    </h1>
                  ),
                  h2: ({ children, ...props }) => (
                    <h2 className="text-base font-semibold mt-6 mb-2 text-foreground" {...props}>
                      {children}
                    </h2>
                  ),
                  h3: ({ children, ...props }) => (
                    <h3 className="text-sm font-semibold mt-4 mb-1.5 text-foreground" {...props}>
                      {children}
                    </h3>
                  ),
                  p: ({ children, ...props }) => (
                    <p className="text-sm leading-relaxed mb-3 text-muted-foreground" {...props}>
                      {children}
                    </p>
                  ),
                  ul: ({ children, ...props }) => (
                    <ul className="list-disc list-inside space-y-1 mb-3 text-sm text-muted-foreground" {...props}>
                      {children}
                    </ul>
                  ),
                  ol: ({ children, ...props }) => (
                    <ol className="list-decimal list-inside space-y-1 mb-3 text-sm text-muted-foreground" {...props}>
                      {children}
                    </ol>
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
                    <strong className="font-semibold text-foreground" {...props}>
                      {children}
                    </strong>
                  ),
                }}
              >
                {readme}
              </ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">{t("documentationNotAvailable")}</p>
          )}
        </div>
      </div>

      <Dialog open={addInstanceOpen} onOpenChange={setAddInstanceOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("addInstance")} of {entry?.name ?? pluginId}
            </DialogTitle>
            <DialogDescription>{t("addInstanceDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
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
            <p className="text-xs text-muted-foreground">{t("instanceNameHelp")}</p>
          </div>
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

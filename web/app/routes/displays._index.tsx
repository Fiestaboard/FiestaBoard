import {
  Badge,
  Box,
  Button,
  Dialog,
  Flex,
  Grid,
  PageCard,
  PageHeader,
  PageLayout,
  PageSection,
  PageToolbar,
  Skeleton,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Monitor, Pause, Play, Plus, Settings2 } from "lucide-react";
import { useState } from "react";

import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayMarketplace } from "@/components/displays/display-marketplace";
import { BoardStatusBadges, BoardSummary, useDisplayBoards } from "@/components/settings/display-settings";
import { AVAILABLE_OUTPUTS_QUERY_KEY, useOutputs } from "@/components/settings/output-boards";
import Link from "@/components/smart-link";
import type { WizardOutputChoice } from "@/components/wizard/step-output-plugin";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { BoardInstance } from "@/lib/api";
import { api } from "@/lib/api";

type Tab = "displays" | "marketplace";

/**
 * Displays (plan D21): every display FiestaBoard shows on — its live
 * preview, name, output and state, with a way into its settings and a
 * pause / resume — and "Add a display".
 *
 * The Marketplace tab lists every display FiestaBoard can drive, installed
 * or not, the way Integrations → Marketplace lists plugins. A card's "Add
 * display" (or a `?add=<output id>` link) opens the add flow at that
 * display's setup.
 */
export default function DisplaysPage() {
  const t = useTranslations("displays");
  const router = useRouter();
  const searchParams = useSearchParams();
  const displays = useDisplayBoards();
  const { data: outputs } = useOutputs();
  const [tab, setTab] = useState<Tab>(() => (searchParams.get("tab") === "marketplace" ? "marketplace" : "displays"));
  // true: the add flow from its first step; an output: from that output's setup.
  const [adding, setAdding] = useState<boolean | WizardOutputChoice>(false);
  const outputName = (board: BoardInstance) => {
    const id = board.output ?? "vestaboard";
    return outputs?.find((o) => o.id === id)?.name ?? id;
  };

  // Shared with the marketplace (same key): the tab's count, and the name a
  // `?add=<id>` link needs.
  const available = useQuery({
    queryKey: AVAILABLE_OUTPUTS_QUERY_KEY,
    queryFn: () => api.listAvailableOutputs(),
    staleTime: 60_000,
  });
  const toInstall = (available.data ?? []).filter((o) => !o.installed).length;

  // A marketplace card's link (`?add=<id>`) opens the add flow for the
  // output it names; closing the dialog drops the parameter.
  const addParam = searchParams.get("add");
  const linked = addParam ? available.data?.find((o) => o.id === addParam) : undefined;
  const open: false | true | WizardOutputChoice =
    adding !== false ? adding : linked ? { id: linked.id, name: linked.name } : false;
  const close = () => {
    setAdding(false);
    if (addParam) router.replace(`/displays?tab=${tab}`, { scroll: false });
  };

  return (
    <PageLayout>
      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
        <PageCard>
          <PageHeader icon={Monitor} title={t("title")} description={t("description")}>
            <Button onClick={() => setAdding(true)} data-testid="add-display">
              <Plus className="mr-1 h-4 w-4" aria-hidden="true" />
              {t("addDisplay")}
            </Button>
          </PageHeader>

          <PageToolbar>
            <TabsList className="w-fit">
              <TabsTrigger value="displays">
                {t("tabDisplays")}
                {!displays.isLoading && (
                  <Badge variant="secondary" className="ml-1.5 h-4 px-1.5 py-0 text-[10px]">
                    {displays.boards.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="marketplace">
                {t("tabMarketplace")}
                {toInstall > 0 && (
                  <Badge variant="outline" className="ml-1.5 h-4 px-1.5 py-0 text-[10px]">
                    {toInstall}
                  </Badge>
                )}
              </TabsTrigger>
            </TabsList>
          </PageToolbar>

          <PageSection {...anchorProps("settings.boards")}>
            <TabsContent value="marketplace" className="mt-0">
              <DisplayMarketplace onAdd={(output) => setAdding(output)} />
            </TabsContent>
            <TabsContent value="displays" className="mt-0">
              {displays.isLoading ? (
                <Grid gap="4" className="md:grid-cols-2">
                  <Skeleton className="h-48 w-full" />
                  <Skeleton className="h-48 w-full" />
                </Grid>
              ) : displays.boards.length === 0 ? (
                <Text tone="muted">{t("empty")}</Text>
              ) : (
                <Grid gap="4" className="md:grid-cols-2" role="list" aria-label={t("listLabel")}>
                  {displays.boards.map((board) => {
                    const name = board.name || t("unnamed");
                    const paused = board.paused === true;
                    return (
                      <Box
                        key={board.id}
                        role="listitem"
                        data-testid="display-card"
                        data-paused={paused ? "true" : undefined}
                        {...anchorProps(`displays.card.${board.id}`)}
                        className={`flex flex-col gap-3 rounded-lg border p-4 ${paused ? "border-amber-500/60 bg-amber-500/5" : ""}`}
                      >
                        <Flex justify="center" className="overflow-hidden" style={{ contain: "layout style paint" }}>
                          <DisplayLivePreview board={board} />
                        </Flex>
                        <Flex align="start" justify="between" gap="2">
                          <Stack gap="1" className="min-w-0">
                            <Text weight="medium" className="truncate">
                              {name}
                            </Text>
                            <Text size="xs" tone="muted" data-testid="display-output">
                              {outputName(board)}
                            </Text>
                            <BoardSummary board={board} />
                          </Stack>
                          <BoardStatusBadges board={board} status={displays.statusFor(board.id)} />
                        </Flex>
                        <Flex gap="2" wrap>
                          <Button asChild variant="outline" size="sm">
                            <Link
                              href={`/displays/${encodeURIComponent(board.id)}`}
                              aria-label={t("openSettingsLabel", { name })}
                            >
                              <Settings2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                              {t("openSettings")}
                            </Link>
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => displays.setPaused(board.id, !paused)}
                            disabled={displays.pausePending}
                            aria-label={paused ? t("resumeLabel", { name }) : t("pauseLabel", { name })}
                          >
                            {paused ? (
                              <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                            ) : (
                              <Pause className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                            )}
                            {paused ? t("resume") : t("pause")}
                          </Button>
                        </Flex>
                      </Box>
                    );
                  })}
                </Grid>
              )}
            </TabsContent>
          </PageSection>
        </PageCard>
      </Tabs>

      <Dialog open={open !== false} onOpenChange={(isOpen) => !isOpen && close()}>
        {open !== false && (
          <AddDisplayDialog
            key={open === true ? "choose" : open.id}
            initialOutput={open === true ? undefined : open}
            onCancel={close}
            onCreated={(boardId) => {
              setAdding(false);
              router.push(`/displays/${encodeURIComponent(boardId)}`);
            }}
          />
        )}
      </Dialog>
    </PageLayout>
  );
}

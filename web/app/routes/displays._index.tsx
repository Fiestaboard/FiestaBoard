import {
  Badge,
  Box,
  Button,
  Flex,
  Grid,
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
import { useState } from "react";

import { useAddDisplay } from "@/components/displays/add-display-context";
import { DisplayList } from "@/components/displays/display-list";
import { DisplayMarketplace } from "@/components/displays/display-marketplace";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { AVAILABLE_OUTPUTS_QUERY_KEY, useOutputs } from "@/components/settings/output-boards";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { BoardInstance } from "@/lib/api";
import { api } from "@/lib/api";

type Tab = "displays" | "marketplace";

/**
 * Displays (plan D21): every display FiestaBoard shows on — its live
 * preview, name, output and state, with a way into its settings and a
 * pause / resume. Rendered inside the Displays section (displays.tsx), which
 * owns the page header, "Add a display" and the add flow.
 *
 * The Marketplace tab lists every display FiestaBoard can drive, installed
 * or not, the way Integrations → Marketplace lists plugins. A card's "Add
 * display" (or a `?add=<output id>` link, handled by the section) opens the
 * add flow at that display's setup.
 */
export default function DisplaysPage() {
  const t = useTranslations("displays");
  const phone = useBelowRail();
  const searchParams = useSearchParams();
  const openAdd = useAddDisplay();
  const displays = useDisplayBoards();
  const { data: outputs } = useOutputs();
  const [tab, setTab] = useState<Tab>(() => (searchParams.get("tab") === "marketplace" ? "marketplace" : "displays"));
  const outputName = (board: BoardInstance) => {
    const id = board.output ?? "vestaboard";
    return outputs?.find((o) => o.id === id)?.name ?? id;
  };

  // Shared with the marketplace and the section (same key): the tab's count.
  const available = useQuery({
    queryKey: AVAILABLE_OUTPUTS_QUERY_KEY,
    queryFn: () => api.listAvailableOutputs(),
    staleTime: 60_000,
  });
  const toInstall = (available.data ?? []).filter((o) => !o.installed).length;

  return (
    // Tabs wraps the toolbar, so the toolbar is no longer a direct child of
    // PageCard and takes the block padding PageCard would have given it (as
    // on Integrations).
    <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
      {/* 07d `320:17086` draws no tabs on a phone: Add display reaches the
          outputs there (Marketplace stays at ?tab=marketplace). */}
      {!phone && (
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
      )}

      <PageSection {...anchorProps("settings.boards")}>
        <TabsContent value="marketplace" className="mt-0">
          <DisplayMarketplace onAdd={(output) => openAdd(output)} />
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
            <DisplayList outputName={outputName} />
          )}
        </TabsContent>
      </PageSection>
    </Tabs>
  );
}

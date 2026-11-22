import {
  Box,
  Button,
  Card,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Flex,
  Grid,
  PageSection,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@fiestaboard/ui";
import { ChevronDown, Eye } from "lucide-react";
import { useEffect, useState } from "react";

import { BoardOutOfSyncBanner } from "@/components/board-out-of-sync-banner";
import { DisplayDiagnostics } from "@/components/displays/display-diagnostics";
import { DisplayEditor } from "@/components/displays/display-editor";
import { DisplayChangePageButton, DisplayPauseButton } from "@/components/displays/display-header-actions";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayOverview } from "@/components/displays/display-overview";
import { DisplayTransition } from "@/components/displays/display-transition";
import { SectionAction } from "@/components/section-shell";
import { BoardEditor, BoardNameField, useDisplayBoards } from "@/components/settings/display-settings";
import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import { isVirtualBoard } from "@/components/settings/output-boards";
import { ScheduleBehavior } from "@/components/settings/schedule-behavior";
import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";
import { LastKnownBoard } from "@/components/status-banners/last-known-board";
import { StatusBannerHost } from "@/components/status-banners/status-banner-host";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/**
 * One display (plan D21): what it shows now, its settings — the output's own
 * screen (plan D13) for any display — its transition from the device's menu,
 * and, for a FiestaPanel, the panel's TV size and viewer address. The Displays
 * section (displays.tsx) names it in the breadcrumb and heading above this.
 */
export function DisplayDetail({ boardId, embedded = false }: { boardId: string; embedded?: boolean }) {
  const t = useTranslations("displays");
  const tf = useTranslations("displays.fleet");
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedSection = searchParams.get("section");
  const resolvedSection =
    requestedSection === "settings" || requestedSection === "playback" || requestedSection === "diagnostics"
      ? requestedSection
      : "overview";
  const [section, setSection] = useState(resolvedSection);
  const [previousRequestedSection, setPreviousRequestedSection] = useState(requestedSection);
  // A choreography navigation can change only the query on this mounted route.
  if (requestedSection !== previousRequestedSection) {
    setPreviousRequestedSection(requestedSection);
    setSection(resolvedSection);
  }
  const changeSection = (next: string) => {
    if (embedded && next !== "overview") {
      router.push(`/displays/${encodeURIComponent(boardId)}?section=${next}`);
      return;
    }
    setSection(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set("section", next);
    if (!embedded) router.replace(`/displays/${encodeURIComponent(boardId)}?${params.toString()}`, { scroll: false });
  };
  const displays = useDisplayBoards();
  // 07d `328:27519`: on a phone the section shell draws "‹ Displays" and the
  // name; the page drops its own back link and section title, and the board
  // runs edge to edge (BB-A-19).
  const phone = useBelowRail();
  const board = displays.boards.find((b) => b.id === boardId);
  const backToList = () => router.push("/displays");

  useEffect(() => {
    if (!board || section !== "playback" || window.location.hash !== "#silence-schedule") return;
    document.getElementById("silence-schedule")?.scrollIntoView({ block: "start" });
  }, [board, section]);

  if (!board) return <DisplayEditor boardId={boardId} onRemoved={backToList} />;

  return (
    <Tabs value={section} onValueChange={changeSection}>
      <PageSection className={embedded ? "px-0 py-0" : undefined}>
        {/* 07d `320:18175`: the header row carries the display's Pause and
            Change Page…; the trail above is the way back, so no back button
            stacks over the tabs (BB-FH-5). The phone keeps Overview's. */}
        {!embedded && !phone && (
          <SectionAction>
            <Flex gap="2">
              <DisplayPauseButton board={board} />
              <DisplayChangePageButton board={board} />
            </Flex>
          </SectionAction>
        )}
        <TabsList aria-label={t("tabsLabel")} className="w-full sm:w-fit">
          <TabsTrigger value="overview">{t("tabOverview")}</TabsTrigger>
          <TabsTrigger value="settings">{t("tabSettings")}</TabsTrigger>
          <TabsTrigger value="playback">{t("tabPlayback")}</TabsTrigger>
          {section === "diagnostics" && <TabsTrigger value="diagnostics">{tf("diagnostics")}</TabsTrigger>}
        </TabsList>
        {/* Slice 2.3: this display's one status banner, under the header and
            tabs (07a "under the header"), on every tab. */}
        <StatusBannerHost boardId={board.id} className="mt-3" />
      </PageSection>
      <TabsContent keepMounted value="overview" className="mt-0">
        {board && (
          <PageSection
            icon={embedded || phone ? undefined : <Eye />}
            title={embedded || phone ? undefined : t("previewTitle")}
            className={embedded ? "border-0 px-0 py-3" : undefined}
          >
            {/* Another app wrote to this display (issue #1945) — the banner Home
              shows, for this board. It reads the board-state query the
              preview below already polls, so it costs no extra request; a
              FiestaPanel always shows what was sent, so it never appears there. */}
            <Box className="mb-4 empty:hidden">
              <BoardOutOfSyncBanner
                boardId={board.id}
                geometry={{
                  deviceType: board.device_type,
                  notesWide: board.notes_wide ?? 1,
                  notesTall: board.notes_tall ?? 1,
                  gridRows: board.grid_rows ?? undefined,
                  gridCols: board.grid_cols ?? undefined,
                }}
                paused={board.paused === true}
              />
            </Box>
            {/* Keep the inherited offline wrapper's preview slot inside this
                pane; otherwise its intrinsic board width hides viewport controls.
                Dim the viewport's board only so its controls and indicator retain
                contrast. Non-viewport previews retain the wrapper's offline dim.
                Shared LastKnownBoard behavior belongs to the status-banner slice. */}
            <Flex
              justify="center"
              className="w-full min-w-0 overflow-x-hidden max-md:-mx-4 max-md:w-[calc(100%+2rem)] md:px-2 [&_[data-slot=last-known-board-preview]]:w-full [&_[data-slot=last-known-board-preview]]:min-w-0 [&_[data-slot=last-known-board-preview]:has([data-slot=board-viewport])]:opacity-100 [&_[data-slot=last-known-board-preview]_[data-slot=board-viewport-bezel]]:opacity-60"
              style={{ contain: "layout style paint" }}
            >
              <LastKnownBoard boardId={board.id}>
                <DisplayLivePreview board={board} size="md" layout={phone ? "phone-hero" : undefined} />
              </LastKnownBoard>
            </Flex>
            <DisplayOverview
              board={board}
              onPlayback={() => changeSection("playback")}
              onDiagnostics={() => changeSection("diagnostics")}
              // On wider screens Change Page… is in the header (07d).
              showChangePage={phone}
            />
          </PageSection>
        )}
      </TabsContent>
      <TabsContent value="diagnostics">
        <BoardOutOfSyncBanner
          boardId={board.id}
          geometry={{
            deviceType: board.device_type,
            notesWide: board.notes_wide ?? 1,
            notesTall: board.notes_tall ?? 1,
            gridRows: board.grid_rows ?? undefined,
            gridCols: board.grid_cols ?? undefined,
          }}
          paused={board.paused === true}
        />
        <DisplayDiagnostics board={board} />
      </TabsContent>
      <TabsContent keepMounted value="settings" className="mt-0">
        {!isVirtualBoard(board) && <DisplayEditor boardId={boardId} onRemoved={backToList} />}

        {/* A FiestaPanel's own controls: TV size and fit, viewer URL / QR,
          live TV preview, the FiestaPi HDMI kiosk. */}
        {board && isVirtualBoard(board) && (
          <Box data-testid="display-panel-settings">
            <FiestaPanelSettings
              boardId={board.id}
              onDeleted={backToList}
              preview={<DisplayLivePreview board={board} size="md" />}
              displayNameField={(pending) => (
                <BoardNameField
                  board={board}
                  disabled={pending || displays.saving}
                  onRename={(name) => displays.updateBoard(board.id, { name })}
                />
              )}
            />
            <Card className="mt-5 gap-0 p-4">
              <Collapsible>
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="touch" className="w-full justify-between">
                    {tf("advanced")}
                    <ChevronDown className="size-4" aria-hidden="true" />
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent className="pt-4">
                  <BoardEditor board={board} displays={displays} hideName onRemoved={backToList} />
                </CollapsibleContent>
              </Collapsible>
            </Card>
          </Box>
        )}
      </TabsContent>
      {/* 07d `320:18175`: the Playback cards' titles carry no icons (BB-FH-6). */}
      <TabsContent keepMounted value="playback" className="mt-0">
        <Grid
          role="region"
          aria-label={t("tabPlayback")}
          gap="5"
          className="lg:grid-cols-[minmax(0,1.54fr)_minmax(0,1fr)]"
        >
          <Stack gap="5" className="min-w-0">
            <Card className="gap-0 py-0">
              <SilenceSchedule key={board.id} boardId={board.id} showIcon={false} />
            </Card>
            <Card className="gap-0 py-0">
              <ScheduleBehavior key={`behavior-${board.id}`} board={board} showIcon={false} />
            </Card>
          </Stack>
          <Stack gap="5" className="min-w-0">
            <Card className="gap-0 py-0">
              <DisplayTransition
                board={board}
                disabled={displays.saving}
                onChange={(updates) => displays.updateBoard(board.id, updates)}
                showIcon={false}
              />
            </Card>
            <Card className="gap-0 py-0">
              <UpdateIntervals key={`intervals-${board.id}`} board={board} showIcon={false} />
            </Card>
          </Stack>
        </Grid>
      </TabsContent>
    </Tabs>
  );
}

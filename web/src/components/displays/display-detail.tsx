import {
  Box,
  Button,
  Card,
  Flex,
  Grid,
  PageSection,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@fiestaboard/ui";
import { Eye } from "lucide-react";
import { useEffect, useState } from "react";

import { BoardOutOfSyncBanner } from "@/components/board-out-of-sync-banner";
import { DisplayDiagnostics } from "@/components/displays/display-diagnostics";
import { DisplayEditor } from "@/components/displays/display-editor";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayOverview } from "@/components/displays/display-overview";
import { DisplayTransition } from "@/components/displays/display-transition";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import { isVirtualBoard } from "@/components/settings/output-boards";
import { ScheduleBehavior } from "@/components/settings/schedule-behavior";
import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";
import Link from "@/components/smart-link";
import { LastKnownBoard } from "@/components/status-banners/last-known-board";
import { StatusBannerHost } from "@/components/status-banners/status-banner-host";
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
    if (embedded && (next === "settings" || next === "playback")) {
      router.push(`/displays/${encodeURIComponent(boardId)}?section=${next}`);
      return;
    }
    setSection(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set("section", next);
    if (!embedded) router.replace(`/displays/${encodeURIComponent(boardId)}?${params.toString()}`, { scroll: false });
  };
  const displays = useDisplayBoards();
  const board = displays.boards.find((b) => b.id === boardId);
  const backToList = () => router.push("/displays");

  useEffect(() => {
    if (!board || section !== "playback" || window.location.hash !== "#silence-schedule") return;
    document.getElementById("silence-schedule")?.scrollIntoView({ block: "start" });
  }, [board, section]);

  if (!board) return <DisplayEditor boardId={boardId} onRemoved={backToList} />;

  return (
    <Tabs value={section} onValueChange={changeSection}>
      <PageSection className={embedded ? "px-0 py-0" : "py-3"}>
        {!embedded && (
          <Button asChild variant="ghost" className="mb-3">
            <Link href="/displays">{tf("back")}</Link>
          </Button>
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
            icon={embedded ? undefined : <Eye />}
            title={embedded ? undefined : t("previewTitle")}
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
            <Flex justify="center" className="overflow-x-hidden px-2" style={{ contain: "layout style paint" }}>
              <LastKnownBoard boardId={board.id}>
                <DisplayLivePreview board={board} size="md" />
              </LastKnownBoard>
            </Flex>
            <DisplayOverview
              board={board}
              onPlayback={() => changeSection("playback")}
              onDiagnostics={() => changeSection("diagnostics")}
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
        <DisplayEditor boardId={boardId} onRemoved={backToList} />

        {/* A FiestaPanel's own controls: TV size and fit, viewer URL / QR,
          live TV preview, the FiestaPi HDMI kiosk. */}
        {board && isVirtualBoard(board) && (
          <Box data-testid="display-panel-settings">
            <FiestaPanelSettings boardId={board.id} onDeleted={backToList} />
          </Box>
        )}
      </TabsContent>
      <TabsContent keepMounted value="playback" className="mt-0">
        <Grid
          role="region"
          aria-label={t("tabPlayback")}
          gap="5"
          className="p-4 lg:grid-cols-[minmax(0,1.54fr)_minmax(0,1fr)]"
        >
          <Stack gap="5" className="min-w-0">
            <Card className="gap-0 py-0">
              <SilenceSchedule key={board.id} boardId={board.id} />
            </Card>
            <Card className="gap-0 py-0">
              <ScheduleBehavior key={`behavior-${board.id}`} board={board} />
            </Card>
          </Stack>
          <Stack gap="5" className="min-w-0">
            <Card className="gap-0 py-0">
              <DisplayTransition
                board={board}
                disabled={displays.saving}
                onChange={(updates) => displays.updateBoard(board.id, updates)}
              />
            </Card>
            <Card className="gap-0 py-0">
              <UpdateIntervals key={`intervals-${board.id}`} board={board} />
            </Card>
          </Stack>
        </Grid>
      </TabsContent>
    </Tabs>
  );
}

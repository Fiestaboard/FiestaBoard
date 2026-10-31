import { Box, Flex, PageSection, Tabs, TabsContent, TabsList, TabsTrigger } from "@fiestaboard/ui";
import { Eye } from "lucide-react";
import { useEffect, useState } from "react";

import { BoardOutOfSyncBanner } from "@/components/board-out-of-sync-banner";
import { DisplayEditor } from "@/components/displays/display-editor";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayTransition } from "@/components/displays/display-transition";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import { isVirtualBoard } from "@/components/settings/output-boards";
import { ScheduleBehavior } from "@/components/settings/schedule-behavior";
import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";
import { useParams, useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/**
 * One display (plan D21): what it shows now, its settings — the output's own
 * screen (plan D13) for any display — its transition from the device's menu,
 * and, for a FiestaPanel, the panel's TV size and viewer address. The Displays
 * section (displays.tsx) names it in the breadcrumb and heading above this.
 */
export default function DisplayPage() {
  const t = useTranslations("displays");
  const router = useRouter();
  const { boardId = "" } = useParams<{ boardId: string }>();
  const searchParams = useSearchParams();
  const requestedSection = searchParams.get("section");
  const resolvedSection =
    requestedSection === "settings" || requestedSection === "playback" ? requestedSection : "overview";
  const [section, setSection] = useState(resolvedSection);
  const [previousRequestedSection, setPreviousRequestedSection] = useState(requestedSection);
  // A choreography navigation can change only the query on this mounted route.
  if (requestedSection !== previousRequestedSection) {
    setPreviousRequestedSection(requestedSection);
    setSection(resolvedSection);
  }
  const changeSection = (next: string) => {
    setSection(next);
    const params = new URLSearchParams(searchParams.toString());
    params.set("section", next);
    router.replace(`/displays/${encodeURIComponent(boardId)}?${params.toString()}`, { scroll: false });
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
      <PageSection className="py-3">
        <TabsList aria-label={t("tabsLabel")} className="w-full sm:w-fit">
          <TabsTrigger value="overview">{t("tabOverview")}</TabsTrigger>
          <TabsTrigger value="settings">{t("tabSettings")}</TabsTrigger>
          <TabsTrigger value="playback">{t("tabPlayback")}</TabsTrigger>
        </TabsList>
      </PageSection>
      <TabsContent keepMounted value="overview" className="mt-0">
        {board && (
          <PageSection icon={<Eye />} title={t("previewTitle")}>
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
              <DisplayLivePreview board={board} size="md" />
            </Flex>
          </PageSection>
        )}
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
        {board && (
          <DisplayTransition
            board={board}
            disabled={displays.saving}
            onChange={(updates) => displays.updateBoard(board.id, updates)}
          />
        )}

        <SilenceSchedule key={board.id} boardId={board.id} />
        <ScheduleBehavior key={`behavior-${board.id}`} board={board} />
        <UpdateIntervals key={`intervals-${board.id}`} board={board} />
      </TabsContent>
    </Tabs>
  );
}

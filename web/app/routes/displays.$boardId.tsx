import { Box, Flex, PageSection } from "@fiestaboard/ui";
import { Eye } from "lucide-react";

import { BoardOutOfSyncBanner } from "@/components/board-out-of-sync-banner";
import { DisplayEditor } from "@/components/displays/display-editor";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayTransition } from "@/components/displays/display-transition";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import { isVirtualBoard } from "@/components/settings/output-boards";
import { useParams, useRouter } from "@/hooks/use-router";
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
  const displays = useDisplayBoards();
  const board = displays.boards.find((b) => b.id === boardId);
  const backToList = () => router.push("/displays");

  return (
    <>
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
              multiBoard={displays.boards.length > 1}
              isPrimary={displays.boards[0]?.id === board.id}
            />
          </Box>
          <Flex justify="center" className="overflow-x-hidden px-2" style={{ contain: "layout style paint" }}>
            <DisplayLivePreview board={board} size="md" />
          </Flex>
        </PageSection>
      )}

      <DisplayEditor boardId={boardId} onRemoved={backToList} />

      {board && (
        <DisplayTransition
          board={board}
          disabled={displays.saving}
          onChange={(updates) => displays.updateBoard(board.id, updates)}
        />
      )}

      {/* A FiestaPanel's own controls: TV size and fit, viewer URL / QR,
          live TV preview, the FiestaPi HDMI kiosk. */}
      {board && isVirtualBoard(board) && (
        <Box data-testid="display-panel-settings">
          <FiestaPanelSettings boardId={board.id} onDeleted={backToList} />
        </Box>
      )}
    </>
  );
}

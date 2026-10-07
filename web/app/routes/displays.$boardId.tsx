import { Box, Button, Flex, PageCard, PageHeader, PageLayout, PageSection } from "@fiestaboard/ui";
import { ArrowLeft, Eye, Monitor } from "lucide-react";

import { DisplayEditor } from "@/components/displays/display-editor";
import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import { DisplayTransition } from "@/components/displays/display-transition";
import { useDisplayBoards } from "@/components/settings/display-settings";
import { FiestaPanelSettings } from "@/components/settings/fiestapanel-settings";
import { isVirtualBoard, useOutputs } from "@/components/settings/output-boards";
import Link from "@/components/smart-link";
import { useParams, useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/**
 * One display (plan D21): what it shows now, its settings — the output's own
 * screen (plan D13) for any display — its transition from the device's menu,
 * and, for a FiestaPanel, the panel's TV size and viewer address.
 */
export default function DisplayPage() {
  const t = useTranslations("displays");
  const router = useRouter();
  const { boardId = "" } = useParams<{ boardId: string }>();
  const displays = useDisplayBoards();
  const { data: outputs } = useOutputs();
  const board = displays.boards.find((b) => b.id === boardId);
  const backToList = () => router.push("/displays");
  const outputId = board?.output ?? "vestaboard";
  const outputName = outputs?.find((o) => o.id === outputId)?.name ?? outputId;

  return (
    <PageLayout>
      <PageCard>
        <PageHeader
          icon={Monitor}
          title={board ? board.name || t("unnamed") : t("title")}
          description={board ? outputName : t("description")}
        >
          <Button asChild variant="ghost" size="sm">
            <Link href="/displays">
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
              {t("back")}
            </Link>
          </Button>
        </PageHeader>

        {board && (
          <PageSection icon={<Eye />} title={t("previewTitle")}>
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
      </PageCard>
    </PageLayout>
  );
}

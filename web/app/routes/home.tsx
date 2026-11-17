import {
  Alert,
  AlertDescription,
  AlertTitle,
  Box,
  Button,
  Dialog,
  EmptyState,
  PageHeader,
  PageLayout,
  Stack,
} from "@fiestaboard/ui";
import { Home as HomeIcon, Info, Monitor, PencilLine } from "lucide-react";
import { useEffect, useState } from "react";

import { ActivePageDisplay } from "@/components/active-page-display";
import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { HomeCompose } from "@/components/home/home-compose";
import { StatusBannerHost } from "@/components/status-banners/status-banner-host";
import { isUntouchedPlaceholder } from "@/components/wizard/default-board";
import { useWizard } from "@/components/wizard-provider";
import { RAIL_BREAKPOINT } from "@/hooks/use-below-rail";
import { useBoardSettings } from "@/hooks/use-board";
import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { getSetupStatus } from "@/lib/setup-detection";

/**
 * Home (03 `33:10`, 07a §3). The PageHeader holds the ONE Compose entry
 * (CANON: Compose has exactly one entry point per platform); Change Page is
 * the Now showing card's in-content secondary action. Layout only: the shell
 * (nav, rail, bottom nav) is slice 2.1's.
 */
export default function Home() {
  const [boardNotConfigured, setBoardNotConfigured] = useState(false);
  const [composeOpen, setComposeOpen] = useState(false);
  const [addingDisplay, setAddingDisplay] = useState(false);
  const { data: boardSettings } = useBoardSettings();
  const noDisplays = !!boardSettings && boardSettings.boards.every(isUntouchedPlaceholder);
  const router = useRouter();
  const { triggerWizard } = useWizard();
  const t = useTranslations("home");
  const td = useTranslations("displays");
  const tw = useTranslations("wizard.noDisplays");

  useEffect(() => {
    getSetupStatus()
      .then((status) => {
        if (status && !status.valid) {
          setBoardNotConfigured(true);
        }
      })
      .catch(() => {
        // Silently ignore - getSetupStatus already logs errors
      });
  }, []);

  return (
    <PageLayout outerClassName="relative" className="relative z-10" railBreakpoint={RAIL_BREAKPOINT}>
      <PageHeader icon={HomeIcon} title={t("title")} description={t("description")} hue="orange">
        {!noDisplays && (
          <Button variant="brand" onClick={() => setComposeOpen(true)} className="gap-2 max-md:h-11">
            <PencilLine className="size-4" aria-hidden="true" />
            {t("compose")}
          </Button>
        )}
      </PageHeader>

      <Stack gap="4" className="mt-6">
        {noDisplays ? (
          <EmptyState
            icon={Monitor}
            title={tw("title")}
            description={tw("description")}
            className="min-h-[319px] rounded-[var(--radius-card)] border bg-card px-5 py-10 md:min-h-[335px] md:px-6 md:py-16 [&_h3]:text-xl [&_[data-slot=empty-state-action]]:max-md:w-full"
            action={
              <Box className="flex w-full flex-col gap-3 md:w-auto md:flex-row md:gap-2">
                <Button onClick={() => setAddingDisplay(true)} className="max-md:min-h-11 max-md:w-full">
                  {tw("add")}
                </Button>
                <Button variant="outline" onClick={triggerWizard} className="max-md:min-h-11 max-md:w-full">
                  {tw("rerun")}
                </Button>
              </Box>
            }
          />
        ) : (
          <>
            {boardNotConfigured && (
              <Alert className="border-info/50 bg-info/10 flex flex-col sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3">
                <Info className="h-4 w-4 text-info" />
                <Box className="flex-1 min-w-0">
                  <AlertTitle>{t("noBoardConfigured")}</AlertTitle>
                  <AlertDescription>{t("noBoardDescription")}</AlertDescription>
                </Box>
                <Button
                  variant="brand"
                  size="sm"
                  onClick={() => router.push("/displays")}
                  className="w-fit btn-lift shrink-0 self-center sm:self-center"
                >
                  {td("title")}
                </Button>
              </Alert>
            )}

            {/* Slice 2.3b owns the standing silenced notice and remaining Home banner hand-offs. */}
            <StatusBannerHost fleet exclude={["silenced"]} />
            <ActivePageDisplay onCompose={() => setComposeOpen(true)} />
          </>
        )}
      </Stack>

      <HomeCompose open={composeOpen} onOpenChange={setComposeOpen} />
      <Dialog open={addingDisplay} onOpenChange={setAddingDisplay}>
        {addingDisplay && (
          <AddDisplayDialog
            onCancel={() => setAddingDisplay(false)}
            onCreated={(id) => {
              setAddingDisplay(false);
              router.push(`/displays/${encodeURIComponent(id)}`);
            }}
          />
        )}
      </Dialog>
    </PageLayout>
  );
}

import {
  Alert,
  AlertDescription,
  AlertTitle,
  BoardIcon,
  Box,
  Button,
  Dialog,
  EmptyState,
  Heading,
  PageHeader,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Home as HomeIcon, Info, Monitor, PencilLine, Plus, RotateCw } from "lucide-react";
import { useEffect, useState } from "react";

import { ActivePageDisplay } from "@/components/active-page-display";
import { AddDisplayDialog } from "@/components/displays/add-display-dialog";
import { HomeCompose } from "@/components/home/home-compose";
import { FlatPage } from "@/components/section-shell";
import { StatusBannerHost } from "@/components/status-banners/status-banner-host";
import { isUntouchedPlaceholder } from "@/components/wizard/default-board";
import { useWizard } from "@/components/wizard-provider";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useBoardSettings } from "@/hooks/use-board";
import { useHubConnection } from "@/hooks/use-hub-connection";
import { useHubIdentity } from "@/hooks/use-hub-identity";
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
  const connection = useHubConnection();
  const sendsDisabled = !connection.deviceOnline || !connection.hubReachable;
  const td = useTranslations("displays");
  const tw = useTranslations("wizard.noDisplays");
  const phone = useBelowRail();
  const hub = useHubIdentity({ enabled: noDisplays });
  // 07e `343:65200`: "Maya's FiestaPi is running, but no display is
  // connected. Add your Vestaboard…"; a phone keeps the first sentence.
  const running = hub.name ? tw("running", { hub: hub.name }) : tw("runningNoName");
  const emptyDescription = phone ? running : `${running} ${tw("addHint")}`;

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
    <FlatPage outerClassName="relative" className="relative z-10">
      {noDisplays && phone ? (
        // 07e `343:66216`: with no display, a phone's header is just "Home"
        // (no icon, no subtitle), as on the other phone section pages.
        <Heading level={1} size="2xl">
          {t("title")}
        </Heading>
      ) : (
        <PageHeader
          icon={HomeIcon}
          title={t("title")}
          // 07a `306:53086`: one line on a phone (BB-FH-9).
          description={phone ? t("descriptionPhone") : t("description")}
          hue="orange"
        >
          {!noDisplays && (
            <Button
              variant="brand"
              disabled={sendsDisabled}
              onClick={() => {
                if (!sendsDisabled) setComposeOpen(true);
              }}
              className="gap-2 max-md:h-11"
            >
              <PencilLine className="size-4" aria-hidden="true" />
              {t("compose")}
            </Button>
          )}
        </PageHeader>
      )}

      <Stack gap="4">
        {noDisplays ? (
          <EmptyState
            icon={Monitor}
            illustration={<BoardIcon className="size-8" />}
            title={tw("title")}
            description={emptyDescription}
            // 07e: a 20 px semibold title over a ~480 px body column.
            className="min-h-[319px] rounded-[var(--radius-card)] border bg-card px-5 py-10 md:min-h-[335px] md:px-6 md:py-16 [&_h3]:text-xl [&_h3]:font-semibold [&_[data-slot=empty-state-description]]:max-w-[30rem] [&_[data-slot=empty-state-media]_svg]:text-brand [&_[data-slot=empty-state-action]]:max-md:w-full"
            action={
              <Stack gap="4" align="center" className="w-full md:w-auto">
                <Box className="flex w-full flex-col gap-3 md:w-auto md:flex-row md:gap-2">
                  <Button onClick={() => setAddingDisplay(true)} className="max-md:min-h-11 max-md:w-full">
                    <Plus className="size-4" aria-hidden="true" />
                    {tw("add")}
                  </Button>
                  <Button variant="outline" onClick={triggerWizard} className="max-md:min-h-11 max-md:w-full">
                    <RotateCw className="size-4" aria-hidden="true" />
                    {tw("rerun")}
                  </Button>
                </Box>
                {/* 07e's footnote under the actions; the phone frame has none. */}
                {!phone && (
                  <Text as="p" size="xs" tone="muted">
                    {tw("footnote")}
                  </Text>
                )}
              </Stack>
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

            <StatusBannerHost fleet />
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
    </FlatPage>
  );
}

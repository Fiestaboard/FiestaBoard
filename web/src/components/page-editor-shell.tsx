"use client";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Flex,
  Stack,
} from "@fiestaboard/ui";
import { useCallback, useEffect, useRef } from "react";
import { type BlockerFunction, useBlocker } from "react-router";

import { PageBuilder, type PageBuilderHandle } from "@/components/page-builder";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";

export interface PageEditorShellProps {
  pageId?: string;
  /** Device type for new pages (ignored when pageId is set). */
  deviceType?: DeviceType;
  /** If true, ignore and clear any saved draft for a new page. */
  skipDraft?: boolean;
  onClose: () => void;
  onSave: () => void;
}

/**
 * Hosts the page builder and registers it with the global AI panel bridge
 * so the AI assistant can read and edit the current page from anywhere
 * in the app.
 */
export function PageEditorShell({ pageId, deviceType, skipDraft, onClose, onSave }: PageEditorShellProps) {
  const builderRef = useRef<PageBuilderHandle>(null);
  const { register, unregister } = usePageEditorBridge();
  const t = useTranslations("pageBuilder");
  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) => {
      // Query/hash updates within this editor do not discard its form state.
      const staysOnPage =
        currentLocation.pathname === nextLocation.pathname &&
        new URLSearchParams(currentLocation.search).get("id") === new URLSearchParams(nextLocation.search).get("id");
      return !staysOnPage && !!pageId && (builderRef.current?.hasUnsavedChanges() ?? false);
    },
    [pageId],
  );
  const blocker = useBlocker(shouldBlock);

  const call = <K extends keyof PageBuilderHandle>(key: K): PageBuilderHandle[K] | undefined =>
    builderRef.current?.[key];

  useEffect(() => {
    register({
      getSnapshot: () => call("getCurrentPage")?.() ?? null,
      getPageId: () => pageId,
      hasUnsavedChanges: () => call("hasUnsavedChanges")?.() ?? false,
      beginStaging: () => call("beginStaging")?.(),
      stageName: (value) => call("stageName")?.(value),
      stageLine: (index, value) => call("stageLine")?.(index, value),
      stageDeviceType: (value) => call("stageDeviceType")?.(value),
      discardStaging: () => call("discardStaging")?.(),
      reloadFromServer: () => call("reloadFromServer")?.() ?? Promise.resolve(),
    });
    return () => unregister();
  }, [register, unregister, pageId]);

  return (
    <>
      <AlertDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("discardChangesTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("discardChangesDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepEditing")}</AlertDialogCancel>
            <Button
              onClick={() => {
                // Let the router close/unmount the dialog; resetting it here can
                // cancel a history POP that is still proceeding.
                if (blocker.state === "blocked") blocker.proceed();
              }}
            >
              {t("discardAndLeave")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <Flex className="flex-1 min-h-0 w-full overflow-hidden">
        {/* No padding of its own: it sits in the Pages section's card, which
          already puts the editor on the content column. */}
        <Stack className="h-full w-full min-w-0 flex-1 overflow-y-auto">
          <PageBuilder
            embedded
            ref={builderRef}
            pageId={pageId}
            deviceType={deviceType}
            skipDraft={skipDraft}
            onClose={onClose}
            onSave={onSave}
          />
        </Stack>
      </Flex>
    </>
  );
}

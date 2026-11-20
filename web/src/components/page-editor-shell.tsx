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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Stack,
} from "@fiestaboard/ui";
import { lazy, type ReactNode, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { type BlockerFunction, useBlocker } from "react-router";

import { PageBuilder, type PageBuilderHandle, type PageBuilderSaveActions } from "@/components/page-builder";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";

// The Creator IDE (web 2.11) only exists for a saved page; its chunk loads
// with the editor route instead of the app shell.
const CreatorIde = lazy(() => import("@/components/ide/creator-ide"));

export type SaveActionsRenderer = (actions: PageBuilderSaveActions) => ReactNode;

export interface PageEditorShellProps {
  pageId?: string;
  /** Device type for new pages (ignored when pageId is set). */
  deviceType?: DeviceType;
  /** Display selected in the Pages filter for a new page. */
  targetBoardId?: string;
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
export function PageEditorShell({
  pageId,
  deviceType,
  targetBoardId,
  skipDraft,
  onClose,
  onSave,
}: PageEditorShellProps) {
  const builderRef = useRef<PageBuilderHandle>(null);
  const { register, unregister } = usePageEditorBridge();
  const t = useTranslations("pageBuilder");
  const shouldBlock = useCallback<BlockerFunction>(({ currentLocation, nextLocation }) => {
    // Query/hash updates within this editor do not discard its form state.
    const staysOnPage =
      currentLocation.pathname === nextLocation.pathname &&
      new URLSearchParams(currentLocation.search).get("id") === new URLSearchParams(nextLocation.search).get("id");
    return !staysOnPage && (builderRef.current?.hasUnsavedChanges() ?? false);
  }, []);
  const blocker = useBlocker(shouldBlock);
  const phone = useMediaQuery("(max-width: 639px)");
  const keepEditingRef = useRef<HTMLButtonElement>(null);
  const resetBlockedNavigation = () => {
    if (blocker.state === "blocked") blocker.reset();
  };
  const discardAndLeave = () => {
    // Let the router unmount the confirmation; resetting here can cancel a POP.
    if (blocker.state === "blocked") blocker.proceed();
  };

  const [explorerSlot, setExplorerSlot] = useState<HTMLElement | null>(null);
  const [saveActions, setSaveActions] = useState<SaveActionsRenderer | undefined>(undefined);
  const [savedTick, setSavedTick] = useState(0);
  const handleSave = () => {
    setSavedTick((tick) => tick + 1);
    onSave();
  };

  const call = <K extends keyof PageBuilderHandle>(key: K): PageBuilderHandle[K] | undefined =>
    builderRef.current?.[key];

  useEffect(() => {
    register({
      getSnapshot: () => call("getCurrentPage")?.() ?? null,
      getPageId: () => call("getPageId")?.() ?? pageId,
      hasUnsavedChanges: () => call("hasUnsavedChanges")?.() ?? false,
      revealText: () => call("revealText")?.(),
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
      {phone ? (
        <Sheet
          modal
          open={blocker.state === "blocked"}
          onOpenChange={(open) => {
            if (!open) resetBlockedNavigation();
          }}
        >
          <SheetContent side="bottom" role="alertdialog" grabber scrim initialFocus={keepEditingRef}>
            <SheetHeader>
              <SheetTitle>{t("discardChangesTitle")}</SheetTitle>
              <SheetDescription>{t("discardChangesDescription")}</SheetDescription>
            </SheetHeader>
            <SheetFooter className="flex-col gap-2">
              <Button
                ref={keepEditingRef}
                variant="outline"
                size="touch"
                className="w-full"
                onClick={resetBlockedNavigation}
              >
                {t("keepEditing")}
              </Button>
              <Button variant="destructive" size="touch" className="w-full" onClick={discardAndLeave}>
                {t("discardAndLeave")}
              </Button>
            </SheetFooter>
          </SheetContent>
        </Sheet>
      ) : (
        <AlertDialog
          open={blocker.state === "blocked"}
          onOpenChange={(open) => {
            if (!open) resetBlockedNavigation();
          }}
        >
          <AlertDialogContent initialFocus={keepEditingRef}>
            <AlertDialogHeader>
              <AlertDialogTitle>{t("discardChangesTitle")}</AlertDialogTitle>
              <AlertDialogDescription>{t("discardChangesDescription")}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel ref={keepEditingRef}>{t("keepEditing")}</AlertDialogCancel>
              <Button variant="destructive" onClick={discardAndLeave}>
                {t("discardAndLeave")}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
      <Flex className="flex-1 min-h-0 w-full overflow-hidden">
        {/* Creator IDE Explorer column (>= 1024 px); the IDE portals into it. */}
        {pageId && <aside ref={setExplorerSlot} data-slot="ide-explorer-slot" className="contents" />}
        {/* No padding of its own: it sits in the Pages section's card, which
          already puts the editor on the content column. */}
        <Stack data-slot="page-editor-scroll" className="h-full w-full min-w-0 flex-1 overflow-y-auto">
          <PageBuilder
            embedded
            ref={builderRef}
            pageId={pageId}
            deviceType={deviceType}
            targetBoardId={targetBoardId}
            skipDraft={skipDraft}
            onClose={onClose}
            onSave={handleSave}
            saveActions={saveActions}
          />
          {pageId && (
            <Suspense fallback={null}>
              <CreatorIde
                pageId={pageId}
                builderRef={builderRef}
                explorerSlot={explorerSlot}
                savedTick={savedTick}
                onSaveActionsChange={setSaveActions}
              />
            </Suspense>
          )}
        </Stack>
      </Flex>
    </>
  );
}

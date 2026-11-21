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
import { useQuery } from "@tanstack/react-query";
import { lazy, type ReactNode, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { type BlockerFunction, useBlocker } from "react-router";

import { IdeExplorerPlaceholder, useExplorerToggle } from "@/components/ide/ide-explorer";
import {
  PageBuilder,
  type PageBuilderHandle,
  type PageBuilderSaveActions,
  type PageBuilderWorkspaceSlots,
} from "@/components/page-builder";
import { usePageEditorBridge } from "@/components/page-editor-bridge-context";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { IDE_DESKTOP_QUERY } from "@/lib/ide/inspector-tabs";
import { cn } from "@/lib/utils";

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
  /** A new page was created by its first save (BB-B-9). */
  onCreated?: (pageId: string) => void;
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
  onCreated,
}: PageEditorShellProps) {
  const builderRef = useRef<PageBuilderHandle>(null);
  const { register, unregister } = usePageEditorBridge();
  const t = useTranslations("pageBuilder");
  const [blockedName, setBlockedName] = useState<string | null>(null);
  const shouldBlock = useCallback<BlockerFunction>(({ currentLocation, nextLocation }) => {
    // Query/hash updates within this editor do not discard its form state.
    const staysOnPage =
      currentLocation.pathname === nextLocation.pathname &&
      new URLSearchParams(currentLocation.search).get("id") === new URLSearchParams(nextLocation.search).get("id");
    const block = !staysOnPage && (builderRef.current?.hasUnsavedChanges() ?? false);
    // The phone sheet names the page it would discard (BB-B-22).
    if (block) setBlockedName(builderRef.current?.getCurrentPage?.()?.name?.trim() || null);
    return block;
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

  // Reads the builder's page query without fetching it itself (the builder
  // owns the fetch): the Creator IDE mounts only around a page that loaded,
  // never under "This page doesn't exist" or a page just deleted (BB-B-16, -27).
  // A new page's first save gives it an id without a route change (BB-B-9);
  // from then on it has the saved page's Creator IDE in the same frame (BB-E-11).
  const [createdId, setCreatedId] = useState<string>();
  const editorPageId = pageId ?? createdId;
  const handleCreated = (id: string) => {
    setCreatedId(id);
    onCreated?.(id);
  };
  const { data: loadedPage } = useQuery({
    queryKey: ["page", editorPageId],
    queryFn: () => api.getPage(editorPageId!),
    enabled: false,
  });
  // The workspace columns' slots (page-builder.tsx): the IDE portals into them.
  const [explorerSlot, setExplorerSlot] = useState<HTMLElement | null>(null);
  const [templateSlot, setTemplateSlot] = useState<HTMLElement | null>(null);
  const [previewSlot, setPreviewSlot] = useState<HTMLElement | null>(null);
  const workspaceSlots = useMemo<PageBuilderWorkspaceSlots>(
    () => ({ explorer: setExplorerSlot, template: setTemplateSlot, preview: setPreviewSlot }),
    [],
  );
  // The Explorer's open state lives here, so the column is the same before
  // the first save (a placeholder) and after it (the IDE's Explorer).
  // Keyed on the kind the builder actually edits: a new page adopts the
  // selected display's kind before its first save (BB-E-11).
  const [builderKind, setBuilderKind] = useState<DeviceType>();
  const explorer = useExplorerToggle(builderKind ?? loadedPage?.device_type ?? deviceType ?? "flagship");
  const desktop = useMediaQuery(IDE_DESKTOP_QUERY);
  const ideMounted = Boolean(editorPageId && loadedPage);
  const explorerPlaceholder =
    explorerSlot && desktop
      ? createPortal(<IdeExplorerPlaceholder toggle={explorer} saved={Boolean(editorPageId)} />, explorerSlot)
      : null;
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
            {/* 316:91801: the page by name, the saved version stays on the
                board; the text keeps clear of the close button (BB-B-22). */}
            <SheetHeader className="pr-12">
              <SheetTitle>
                {blockedName ? t("discardChangesTitleNamed", { name: blockedName }) : t("discardChangesTitle")}
              </SheetTitle>
              <SheetDescription>{t("discardChangesSavedVersion")}</SheetDescription>
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
                {t("discardChanges")}
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
        {/* No padding of its own: it sits in the Pages section's card, which
          already puts the editor on the content column. */}
        {/* The end of the scroll area clears the fixed touch toolbar (BB-B-29).
            With the IDE in the workspace, its own bottom padding already does. */}
        <Stack
          data-slot="page-editor-scroll"
          className={cn(
            "h-full w-full min-w-0 flex-1 overflow-y-auto",
            !editorPageId && "max-md:pb-20 pointer-coarse:pb-20",
          )}
        >
          <PageBuilder
            embedded
            ref={builderRef}
            pageId={pageId}
            deviceType={deviceType}
            targetBoardId={targetBoardId}
            skipDraft={skipDraft}
            onClose={onClose}
            onSave={handleSave}
            onCreated={handleCreated}
            saveActions={saveActions}
            workspaceSlots={workspaceSlots}
            onDeviceTypeChange={setBuilderKind}
          />
          {/* Until the IDE is up (a new page, or its chunk still loading), the
              Explorer column keeps its frame so nothing moves (BB-E-11). */}
          {!ideMounted && explorerPlaceholder}
          {editorPageId && loadedPage && (
            <Suspense fallback={explorerPlaceholder}>
              <CreatorIde
                pageId={editorPageId}
                builderRef={builderRef}
                explorerSlot={explorerSlot}
                templateSlot={templateSlot}
                previewSlot={previewSlot}
                explorer={explorer}
                boardKind={loadedPage.device_type}
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

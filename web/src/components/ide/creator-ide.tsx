"use client";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Button,
  Card,
  CardContent,
  InspectorTabs,
  InspectorTabsContent,
  PreviewStatus,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { type ReactNode, type RefObject, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import type { PageBuilderDraftState, PageBuilderHandle } from "@/components/page-builder";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useRouter } from "@/hooks/use-router";
import { useLocale, useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { offersDraft } from "@/lib/ide/edit-state";
import { IDE_DESKTOP_QUERY, type IdeTabId, inspectorTabIds, resolveInspectorTab } from "@/lib/ide/inspector-tabs";
import { templateReferences } from "@/lib/ide/references";

import { type ConsoleTab, IdeConsole, IdeProblemList, IdeSentPanel } from "./ide-console";
import { type ExplorerToggle, IdeExplorer, IdeExplorerShow, useExplorerToggle } from "./ide-explorer";
import { formatWallTime } from "./ide-format";
import { IdeHistory } from "./ide-history";
import { DuplicateDialog, IdePageTab } from "./ide-page-tab";
import { IdeReferences } from "./ide-references";
import { IdeShowsOn } from "./ide-shows-on";
import { IdeWeek } from "./ide-timeline";
import { type CreatorIdeState, useCreatorIde } from "./use-creator-ide";

export interface CreatorIdeProps {
  pageId: string;
  builderRef: RefObject<PageBuilderHandle | null>;
  /** The workspace's Explorer column (page-builder.tsx `workspaceSlots`). */
  explorerSlot: HTMLElement | null;
  /** The end of the template column: Console and Timeline go there (BB-E-7). Omitted: rendered in place. */
  templateSlot?: HTMLElement | null;
  /** The end of the preview column: the status row and Inspector go there. Omitted: rendered in place. */
  previewSlot?: HTMLElement | null;
  /** The preview card's foot (≥ 768 px, UX-6-2): the status line goes there. Null: it heads the Inspector stack. */
  statusSlot?: HTMLElement | null;
  /**
   * The toolbar row's left end (≥ 1024 px, UX-5-1): the Explorer toggle's one
   * place, open or closed. Unused until the toggle moves there (FP-2).
   */
  toolbarStartSlot?: HTMLElement | null;
  /** The Explorer's open state when the shell owns it (it draws the same column before the first save). */
  explorer?: ExplorerToggle;
  /** The saved page's board kind: whether the Explorer starts open, and whose remembered choice applies (D2). */
  boardKind?: DeviceType;
  /** Increments after each successful header Save. */
  savedTick: number;
  /**
   * D4/D6: the hub draft's state for the header meta ("Draft restored · Discard", "Draft saved 7:44 AM"),
   * and the header's Save draft while a display shows the page.
   */
  onDraftStateChange?: (state: PageBuilderDraftState | undefined) => void;
  /** UX-6-1: the displays that show the page, for the editor's preview target (page-builder.tsx `pageDisplayIds`). */
  onPageDisplaysChange?: (ids: readonly string[]) => void;
}

/** Portals into a workspace slot when the shell gives one; otherwise renders in place. */
function inSlot(slot: HTMLElement | null | undefined, node: ReactNode) {
  if (slot === undefined) return node;
  return slot ? createPortal(node, slot) : null;
}

function useStatusMessage(ide: CreatorIdeState) {
  const t = useTranslations("creatorIde");
  const locale = useLocale();
  const showing = ide.showsOn.showingNow[0];
  if (showing) {
    const until = formatWallTime(showing.until, locale);
    return until
      ? t("showingUntil", { board: showing.boardName, time: until })
      : t("showingNow", { board: showing.boardName });
  }
  const next = ide.showsOn.entries.find((entry) => entry.schedule.enabled);
  if (next) return t("scheduledOn", { board: next.boardName });
  // The "Not scheduled" chip already says it; a sentence repeating it was a
  // second report of the same state (BB-E-26).
  return "";
}

/**
 * The Creator IDE (web 2.11, Figma 04d 4.3 `184:159319`): Explorer beside the
 * editor, then under it the docked console and week timeline (template
 * column) and the preview status row with the Inspector (preview column).
 * Below 1024 px the console folds into the Inspector as a sixth Problems tab
 * (Jev desktop_console_two_option) and the week moves into Shows on.
 */
export default function CreatorIde({
  pageId,
  builderRef,
  explorerSlot,
  templateSlot,
  previewSlot,
  statusSlot,
  explorer: explorerProp,
  boardKind = "flagship",
  savedTick,
  onDraftStateChange,
  onPageDisplaysChange,
}: CreatorIdeProps) {
  const t = useTranslations("creatorIde");
  const router = useRouter();
  const ide = useCreatorIde(pageId, builderRef, savedTick);
  const desktop = useMediaQuery(IDE_DESKTOP_QUERY);
  const [tab, setTab] = useState<IdeTabId>("page");
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("problems");
  const [copyOpen, setCopyOpen] = useState(false);
  const ownExplorer = useExplorerToggle(boardKind);
  const explorer = explorerProp ?? ownExplorer;
  const activeTab = resolveInspectorTab(tab, desktop);
  const references = useMemo(() => templateReferences(ide.builder.snapshot?.template ?? []), [ide.builder.snapshot]);
  const { pageDisplays } = ide;
  useEffect(() => {
    onPageDisplaysChange?.(pageDisplays);
    // Another page, or no IDE (a new page): its displays no longer apply.
    return () => onPageDisplaysChange?.([]);
  }, [onPageDisplaysChange, pageDisplays]);

  // D4: what the header meta says about the hub draft, and (D6) where the page is
  // live, which is why Save reads "Save draft / Save & update board".
  const restoredDraft = ide.restoredDraft;
  // "Draft saved" only when the draft holds exactly these edits; a draft from
  // elsewhere that autosave leaves alone says so instead (FABLE-2583).
  const draftSavedAt = ide.draft && ide.builder.unsaved && ide.draftInStep ? ide.draft.saved_at : null;
  const autosavePaused = ide.autosavePaused;
  // D6: Save draft lives in the header (page-builder); the IDE supplies its action.
  const draftOffered = offersDraft(ide.display);
  const { mutate: saveDraftMutate, isPending: savingDraft } = ide.saveDraft;
  const liveBoard = ide.showsOn.showingNow[0]?.boardName ?? null;
  const { discardRestored, discardOwnedDraft } = ide;
  useEffect(() => {
    if (!onDraftStateChange) return;
    const live = liveBoard ? t("liveOn", { board: liveBoard }) : undefined;
    const label = restoredDraft
      ? restoredDraft.stale
        ? t("draftRestoredStale")
        : t("draftRestored")
      : autosavePaused
        ? t("autosavePaused")
        : undefined;
    onDraftStateChange({
      live,
      liveBoard: liveBoard ?? undefined,
      label,
      draftSavedAt: draftSavedAt ?? undefined,
      savingDraft,
      saveDraft: draftOffered ? () => saveDraftMutate({}) : undefined,
      onDiscard: restoredDraft ? () => void discardRestored() : undefined,
      discardDraft: discardOwnedDraft,
    });
  }, [
    onDraftStateChange,
    restoredDraft,
    draftSavedAt,
    autosavePaused,
    liveBoard,
    discardRestored,
    discardOwnedDraft,
    draftOffered,
    savingDraft,
    saveDraftMutate,
    t,
  ]);
  useEffect(() => () => onDraftStateChange?.(undefined), [onDraftStateChange]);

  const problemCount = ide.problems.length;
  const openProblems = () => {
    if (desktop) {
      setConsoleTab("problems");
      document.getElementById("ide-console")?.scrollIntoView({ block: "nearest" });
      return;
    }
    setTab("problems");
    document.getElementById("ide-inspector")?.scrollIntoView({ block: "nearest" });
  };

  const tabs = inspectorTabIds(desktop).map((id) => ({ value: id, label: t(`tab.${id}`) }));
  const statusMessage = useStatusMessage(ide);

  // Console and Timeline: the foot of the template column (184:159319).
  const consoleRegions = (
    <Stack gap="3" data-slot="ide-template-regions" className="min-w-0">
      <Card className="gap-0 py-0">
        <CardContent className="p-3.5">
          <IdeConsole ide={ide} tab={consoleTab} onTabChange={setConsoleTab} />
        </CardContent>
      </Card>
      <Card className="gap-0 py-0" data-slot="ide-timeline">
        <CardContent className="flex flex-col gap-1.5 p-3.5">
          <Text as="p" size="xs" tone="muted" className="font-mono uppercase tracking-wide">
            {t("timelineLabel", { page: ide.builder.snapshot?.name ?? "", board: ide.pageBoard?.name ?? "" })}
          </Text>
          <IdeWeek ide={ide} />
        </CardContent>
      </Card>
    </Stack>
  );
  const status = (
    <PreviewStatus
      data-slot="ide-preview-status"
      display={ide.display}
      displayLabel={t(`display.${ide.display}`)}
      message={statusMessage}
      // The header meta is the one place for the save state (D6, UX-1-1): no
      // Saved, Unsaved or Draft chip here. Testing (mirroring) is not a save state.
      editState={ide.editState === "testing" ? ide.editState : undefined}
      editStateLabel={t(`edit.${ide.editState}`)}
      problems={problemCount}
      onOpenProblems={openProblems}
      problemsLabel={(count) => t("problemsLink", { count })}
      problemsDirection={desktop ? "down" : "right"}
    />
  );
  // The Inspector (and the status line on a phone): the foot of the preview
  // column. Below 1024 px the stack under the template and the preview.
  const previewRegions = (
    <Box
      as="section"
      aria-label={t("regionLabel")}
      data-slot="creator-ide"
      data-layout={desktop ? "desktop" : "compact"}
      className="flex min-w-0 flex-col gap-3 px-2 pb-24 lg:px-0 lg:pb-0"
    >
      {!statusSlot && status}
      <Card className="gap-0 py-0" id="ide-inspector">
        <CardContent className="p-3.5">
          <InspectorTabs
            aria-label={t("inspector")}
            tabs={tabs}
            value={activeTab}
            onValueChange={(value) => value && setTab(value as IdeTabId)}
            counts={desktop ? undefined : { problems: problemCount }}
          >
            <InspectorTabsContent value="data" className="pt-2">
              <IdeReferences references={references.variables} emptyLabel={t("noData")} mono />
            </InspectorTabsContent>
            <InspectorTabsContent value="logic" className="pt-2">
              <IdeReferences references={references.formulas} emptyLabel={t("noLogic")} mono />
            </InspectorTabsContent>
            {/* Panels that always hold rows are not a Tab stop of their own (BB-E-22): the
              first row is, so Page duration isn't announced twice. */}
            <InspectorTabsContent value="page" className="pt-2" tabIndex={-1}>
              <IdePageTab ide={ide} pageId={pageId} builderRef={builderRef} onMakeCopy={() => setCopyOpen(true)} />
            </InspectorTabsContent>
            <InspectorTabsContent value="shows-on" className="pt-2" tabIndex={-1}>
              <IdeShowsOn
                ide={ide}
                pageId={pageId}
                showWeek={!desktop}
                onNavigate={(href) => router.push(href)}
                onMakeCopy={() => setCopyOpen(true)}
              />
            </InspectorTabsContent>
            {!desktop && (
              <InspectorTabsContent value="problems" className="pt-2">
                <Stack gap="3">
                  <IdeProblemList
                    problems={[...ide.problems, ...ide.warnings]}
                    emptyLabel={t("noProblems")}
                    layout="stacked"
                    size="touch"
                  />
                  <IdeSentPanel ide={ide} size="touch" />
                </Stack>
              </InspectorTabsContent>
            )}
            <InspectorTabsContent value="history" className="pt-2">
              <IdeHistory ide={ide} pageId={pageId} />
            </InspectorTabsContent>
          </InspectorTabs>
        </CardContent>
      </Card>
    </Box>
  );

  return (
    <>
      {explorerSlot &&
        desktop &&
        createPortal(
          explorer.open ? (
            <IdeExplorer
              ide={ide}
              pageId={pageId}
              references={references}
              onHide={explorer.hide}
              hideRef={explorer.hideRef}
            />
          ) : (
            <IdeExplorerShow onShow={explorer.show} buttonRef={explorer.showRef} />
          ),
          explorerSlot,
        )}
      {desktop && inSlot(templateSlot, consoleRegions)}
      {inSlot(previewSlot, previewRegions)}
      {statusSlot && createPortal(status, statusSlot)}
      <AlertDialog open={ide.draftConflict} onOpenChange={(open) => !open && ide.dismissDraftConflict()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("draftConflictTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("draftConflictDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepDraft")}</AlertDialogCancel>
            <Button variant="destructive" disabled={savingDraft} onClick={() => saveDraftMutate({ overwrite: true })}>
              {t("replaceDraft")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <DuplicateDialog open={copyOpen} onOpenChange={setCopyOpen} ide={ide} pageId={pageId} />
    </>
  );
}

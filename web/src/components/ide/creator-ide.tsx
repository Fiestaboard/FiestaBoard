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
import { Save, Send } from "lucide-react";
import {
  type Dispatch,
  type ReactNode,
  type RefObject,
  type SetStateAction,
  useEffect,
  useMemo,
  useState,
} from "react";
import { createPortal } from "react-dom";

import type { PageBuilderDraftState, PageBuilderHandle, PageBuilderSaveActions } from "@/components/page-builder";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useRouter } from "@/hooks/use-router";
import { useLocale, useTranslations } from "@/i18n/translations";
import { offersDraft } from "@/lib/ide/edit-state";
import { IDE_DESKTOP_QUERY, type IdeTabId, inspectorTabIds, resolveInspectorTab } from "@/lib/ide/inspector-tabs";
import { templateReferences } from "@/lib/ide/references";

import { type ConsoleTab, IdeConsole, IdeProblemList, IdeSentPanel } from "./ide-console";
import { IdeExplorer } from "./ide-explorer";
import { formatClock, formatSavedAt, formatWallTime } from "./ide-format";
import { IdeHistory } from "./ide-history";
import { DuplicateDialog, IdePageTab } from "./ide-page-tab";
import { IdeReferences } from "./ide-references";
import { IdeShowsOn } from "./ide-shows-on";
import { IdeWeek } from "./ide-timeline";
import { type CreatorIdeState, useCreatorIde } from "./use-creator-ide";

export interface CreatorIdeProps {
  pageId: string;
  builderRef: RefObject<PageBuilderHandle | null>;
  /** Where the Explorer column renders (beside the editor). */
  explorerSlot: HTMLElement | null;
  /** Increments after each successful header Save. */
  savedTick: number;
  /** Supplies the header's Save draft / Save & update board while a display shows the page (a state setter). */
  onSaveActionsChange: Dispatch<SetStateAction<((actions: PageBuilderSaveActions) => ReactNode) | undefined>>;
  /** D4: the hub draft's state for the header meta ("Draft restored · Discard", "Draft saved 7:44 AM"). */
  onDraftStateChange?: (state: PageBuilderDraftState | undefined) => void;
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
  return t("notScheduledMessage");
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
  savedTick,
  onSaveActionsChange,
  onDraftStateChange,
}: CreatorIdeProps) {
  const t = useTranslations("creatorIde");
  const locale = useLocale();
  const router = useRouter();
  const ide = useCreatorIde(pageId, builderRef, savedTick);
  const desktop = useMediaQuery(IDE_DESKTOP_QUERY);
  const phone = useMediaQuery("(max-width: 639px)");
  const [tab, setTab] = useState<IdeTabId>("page");
  const [consoleTab, setConsoleTab] = useState<ConsoleTab>("problems");
  const [copyOpen, setCopyOpen] = useState(false);
  const activeTab = resolveInspectorTab(tab, desktop);
  const references = useMemo(() => templateReferences(ide.builder.snapshot?.template ?? []), [ide.builder.snapshot]);

  // D4: what the header meta says about the hub draft, and (D6) where the page is
  // live, which is why Save reads "Save draft / Save & update board".
  const restoredDraft = ide.restoredDraft;
  const draftSavedAt = ide.draft && ide.builder.unsaved ? ide.draft.saved_at : null;
  const liveBoard = ide.showsOn.showingNow[0]?.boardName ?? null;
  const { discardRestored, discardOwnedDraft } = ide;
  useEffect(() => {
    if (!onDraftStateChange) return;
    const live = liveBoard ? t("liveOn", { board: liveBoard }) : undefined;
    const label = restoredDraft
      ? restoredDraft.stale
        ? t("draftRestoredStale")
        : t("draftRestored")
      : draftSavedAt
        ? t("draftSavedAt", { time: formatClock(draftSavedAt, locale) })
        : undefined;
    onDraftStateChange({
      live,
      label,
      onDiscard: restoredDraft ? () => void discardRestored() : undefined,
      discardDraft: discardOwnedDraft,
    });
  }, [onDraftStateChange, restoredDraft, draftSavedAt, liveBoard, discardRestored, discardOwnedDraft, t, locale]);
  useEffect(() => () => onDraftStateChange?.(undefined), [onDraftStateChange]);

  const draftOffered = offersDraft(ide.display);
  const { mutate: saveDraftMutate, isPending: savingDraft } = ide.saveDraft;
  useEffect(() => {
    if (!draftOffered) {
      onSaveActionsChange(undefined);
      return;
    }
    // A function value: wrapped so the shell's setState stores it rather than calling it.
    onSaveActionsChange(() => (actions: PageBuilderSaveActions) => (
      <>
        {phone ? (
          // Phone header: the name keeps its room; Save draft is the icon (named for AT).
          <Button
            variant="secondary"
            size="icon-touch"
            className="shrink-0"
            aria-label={t("saveDraft")}
            disabled={actions.disabled || savingDraft}
            onClick={() => saveDraftMutate({})}
          >
            <Save className="size-4" aria-hidden="true" />
          </Button>
        ) : (
          <Button
            variant="secondary"
            size={actions.size}
            className="shrink-0 gap-1.5 px-3 text-sm"
            disabled={actions.disabled || savingDraft}
            onClick={() => saveDraftMutate({})}
          >
            <Save className="size-3.5" aria-hidden="true" />
            {savingDraft ? t("savingDraft") : t("saveDraft")}
          </Button>
        )}
        <Button
          variant="brand"
          size={actions.size}
          className="shrink-0 gap-1.5 px-3 text-sm"
          disabled={actions.disabled}
          onClick={actions.save}
          // Phone: a short label so the page name keeps two readable lines (BB-B-3).
          aria-label={phone && !actions.saving ? t("saveAndUpdate") : undefined}
          {...actions.anchor}
        >
          <Send className="size-4" aria-hidden="true" />
          {actions.saving ? t("saving") : phone ? t("updateBoardShort") : t("saveAndUpdate")}
        </Button>
      </>
    ));
  }, [draftOffered, phone, savingDraft, saveDraftMutate, onSaveActionsChange, t]);
  useEffect(() => () => onSaveActionsChange(undefined), [onSaveActionsChange]);

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
  const draftLabel = ide.draft ? t("draftAt", { time: formatSavedAt(ide.draft.saved_at, locale) }) : undefined;

  return (
    <>
      {explorerSlot && desktop && createPortal(<IdeExplorer ide={ide} pageId={pageId} />, explorerSlot)}
      <Box
        as="section"
        aria-label={t("regionLabel")}
        data-slot="creator-ide"
        data-layout={desktop ? "desktop" : "compact"}
        // The same two equal columns as the builder above (page-builder.tsx):
        // Console and Timeline under the template, the Inspector under the
        // preview. At 2fr the console was ~300px at 1440 and wrapped each
        // problem onto four lines (BB-B-19).
        className="grid min-w-0 grid-cols-1 items-start gap-4 px-2 pb-24 lg:grid-cols-2 lg:gap-6 lg:px-4"
      >
        {desktop && (
          <Stack gap="3" className="min-w-0">
            <Card className="gap-0 py-0">
              <CardContent className="p-3.5">
                <IdeConsole ide={ide} tab={consoleTab} onTabChange={setConsoleTab} />
              </CardContent>
            </Card>
            <Card className="gap-0 py-0" data-slot="ide-timeline">
              <CardContent className="flex flex-col gap-1.5 p-3.5">
                <Text as="p" size="xs" tone="muted" className="font-mono uppercase tracking-wide">
                  {t("timelineLabel", { page: ide.builder.snapshot?.name ?? "", board: ide.currentBoard?.name ?? "" })}
                </Text>
                <IdeWeek ide={ide} />
              </CardContent>
            </Card>
          </Stack>
        )}
        <Stack gap="3" className="min-w-0">
          <PreviewStatus
            data-slot="ide-preview-status"
            display={ide.display}
            displayLabel={t(`display.${ide.display}`)}
            message={statusMessage}
            editState={ide.editState}
            editStateLabel={ide.editState === "draft" && draftLabel ? draftLabel : t(`edit.${ide.editState}`)}
            problems={problemCount}
            onOpenProblems={openProblems}
            problemsLabel={(count) => t("problemsLink", { count })}
            problemsDirection={desktop ? "down" : "right"}
          />
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
                <InspectorTabsContent value="page" className="pt-2">
                  <IdePageTab ide={ide} pageId={pageId} builderRef={builderRef} onMakeCopy={() => setCopyOpen(true)} />
                </InspectorTabsContent>
                <InspectorTabsContent value="shows-on" className="pt-2">
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
        </Stack>
      </Box>
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

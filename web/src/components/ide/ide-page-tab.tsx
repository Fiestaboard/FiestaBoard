"use client";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  InspectorRow,
  List,
  ListItem,
  ListRow,
  ListRowGroup,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ComponentProps, Fragment, type MouseEventHandler, type RefObject, useState } from "react";
import { Link } from "react-router";

import type { PageBuilderHandle } from "@/components/page-builder";
import { queryKeys } from "@/hooks/use-board";
import { useMediaQuery } from "@/hooks/use-media-query";
import { usePluginSettings } from "@/hooks/use-plugin-settings";
import { useTransitionPlugins } from "@/hooks/use-transition-plugins";
import { useTranslations } from "@/i18n/translations";
import { type PageDuplicateResponse, pageHistoryApi } from "@/lib/api/page-history";
import { jumpToTemplateLine } from "@/lib/ide/jump-to-line";
import { templateReferences } from "@/lib/ide/references";

import type { CreatorIdeState } from "./use-creator-ide";

/** Page durations the hub accepts (10 s – 1 h), as drawn in 04d 1.6. */
export const DURATION_CHOICES = [10, 30, 60, 300, 900, 3600] as const;

/** The built-in transitions, keyed to the shared transitionSettings labels. */
export const TRANSITIONS: { value: string; labelKey: string }[] = [
  { value: "column", labelKey: "column" },
  { value: "reverse-column", labelKey: "reverseColumn" },
  { value: "edges-to-center", labelKey: "edgesToCenter" },
  { value: "row", labelKey: "row" },
  { value: "diagonal", labelKey: "diagonal" },
  { value: "random", labelKey: "random" },
];
const INHERIT = "__inherit__";

export function formatDuration(seconds: number, t: (key: string, params?: Record<string, unknown>) => string) {
  if (seconds >= 3600 && seconds % 3600 === 0) return t("hours", { count: seconds / 3600 });
  if (seconds >= 60 && seconds % 60 === 0) return t("minutes", { count: seconds / 60 });
  return t("seconds", { count: seconds });
}

const PLUGIN_PREFIX = "plugin:";

/**
 * Transition plugins (beta, deprecated) for the Page tab, as the editor's
 * header picker offered them before D6 moved that picker here: installed
 * ones while the beta is on, and a page's existing `plugin:<id>` override by
 * name (or raw id when its plugin is gone), so it is never shown as the
 * display's default.
 */
function usePageTransitionPlugins(strategy: string | null | undefined) {
  const { data: settings } = usePluginSettings();
  const plugins = useTransitionPlugins(settings?.transition_plugins_enabled ?? false);
  const pluginId = strategy?.startsWith(PLUGIN_PREFIX) ? strategy.slice(PLUGIN_PREFIX.length) : null;
  const current = pluginId ? (plugins.find((plugin) => plugin.id === pluginId)?.name ?? pluginId) : null;
  return { plugins, current, pluginId };
}

/**
 * An Inspector row that opens a menu (UX-7-1): Base UI's trigger hands the row
 * its press handler as `onClick`; InspectorRow calls it `onPress`.
 */
function MenuRow({
  onClick,
  ...props
}: Omit<ComponentProps<typeof InspectorRow>, "onPress"> & { onClick?: MouseEventHandler<HTMLButtonElement> }) {
  return <InspectorRow {...props} onPress={(event) => onClick?.(event)} />;
}

/**
 * A Page-tab setting as an inline menu on its row (UX-7-1, Photoshop's
 * properties panel): the choice is staged in the editor like any other edit,
 * so it joins the unsaved changes, shows in the discard list and Save writes it.
 */
function PageSettingMenu({
  row,
  label,
  value,
  options,
  onChange,
}: {
  row: Omit<ComponentProps<typeof InspectorRow>, "onPress">;
  label: string;
  value: string;
  options: { value: string; label: string; group?: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <MenuRow {...row} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="text-xs font-medium">{label}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup value={value} onValueChange={(next) => onChange(String(next))}>
          {options.map((option, index) => {
            const heading = option.group && option.group !== options[index - 1]?.group ? option.group : null;
            return (
              <Fragment key={option.value}>
                {heading && (
                  <DropdownMenuLabel className="text-[11px] text-muted-foreground">{heading}</DropdownMenuLabel>
                )}
                {/* Base UI's radio items stay open by default; a pick is one-shot. */}
                <DropdownMenuRadioItem value={option.value} className="text-xs" closeOnClick>
                  {option.label}
                </DropdownMenuRadioItem>
              </Fragment>
            );
          })}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * "Make a copy for another display…" (04d 1.6b, H9c): the copy is made at
 * the chosen display's size and opens with the hub's crop report.
 */
export function DuplicateDialog({
  open,
  onOpenChange,
  ide,
  pageId,
  boardId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ide: CreatorIdeState;
  pageId: string;
  /** D3: "Make a copy sized for X" from Shows on, for one display of another size. */
  boardId?: string | null;
}) {
  const tq = useTranslations("ideQuiet");
  const sizedFor = boardId ? ide.boards.find((board) => board.id === boardId) : undefined;
  const t = useTranslations("creatorIde");
  const queryClient = useQueryClient();
  const [result, setResult] = useState<PageDuplicateResponse | null>(null);
  const duplicate = useMutation({
    mutationFn: (boardId: string) => pageHistoryApi.duplicatePage(pageId, { board_id: boardId }),
    onSuccess: (response) => {
      setResult(response);
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages });
    },
  });
  const close = (next: boolean) => {
    if (!next) {
      setResult(null);
      duplicate.reset();
    }
    onOpenChange(next);
  };
  const report = result?.report;
  // A sheet on a phone, like the rest of the phone UI; the dialog elsewhere.
  // Its title keeps clear of the close button (BB-B-23).
  const phone = useMediaQuery("(max-width: 639px)");
  const Root = phone ? Sheet : Dialog;
  const Content = phone ? SheetContent : DialogContent;
  const Header = phone ? SheetHeader : DialogHeader;
  const Title = phone ? SheetTitle : DialogTitle;
  const Description = phone ? SheetDescription : DialogDescription;
  const Footer = phone ? SheetFooter : DialogFooter;
  const contentProps = phone ? { side: "bottom" as const, grabber: true } : {};
  return (
    <Root open={open} onOpenChange={close}>
      <Content {...contentProps}>
        <Header className="pr-12 text-start">
          <Title>
            {result
              ? t("copyMade", { name: result.page.name })
              : sizedFor
                ? tq("copySizedFor", { board: sizedFor.name })
                : t("makeCopy")}
          </Title>
          <Description>{result || sizedFor ? t("cropReport") : t("pickDisplay")}</Description>
        </Header>
        {report ? (
          <Stack gap="1" data-slot="ide-crop-report">
            <Text size="sm">
              {t("copySize", {
                cols: report.cols,
                rows: report.rows,
                fromCols: report.from_cols,
                fromRows: report.from_rows,
              })}
            </Text>
            {report.lines_too_long.length > 0 && (
              <Text size="sm">{t("cropTooLong", { count: report.lines_too_long.length })}</Text>
            )}
            {report.rows_dropped.length > 0 && (
              <Text size="sm">{t("cropRowsDropped", { count: report.rows_dropped.length })}</Text>
            )}
            {report.canvases_scaled > 0 && (
              <Text size="sm">{t("cropCanvases", { count: report.canvases_scaled })}</Text>
            )}
            {report.drawing?.source === "baseline" && <Text size="sm">{t("cropUnknownDrawing")}</Text>}
            {!report.lines_too_long.length && !report.rows_dropped.length && (
              <Text size="sm" tone="muted">
                {t("cropNothingLost")}
              </Text>
            )}
          </Stack>
        ) : sizedFor ? null : ide.boards.length ? (
          <ListRowGroup>
            {ide.boards.map((board) => (
              <ListRow
                key={board.id}
                title={board.name}
                description={board.id === ide.pageBoardId ? t("thisDisplay") : undefined}
                render={<button type="button" disabled={duplicate.isPending} />}
                onClick={() => duplicate.mutate(board.id)}
              />
            ))}
          </ListRowGroup>
        ) : (
          <Text size="sm" tone="muted">
            {t("noDisplays")}
          </Text>
        )}
        {duplicate.isError && (
          <Text size="sm" tone="destructive" role="alert">
            {t("copyFailed")}
          </Text>
        )}
        <Footer>
          {result ? (
            // The X closes; a second Close button beside it was one too many.
            <Button asChild onClick={() => close(false)}>
              <Link to={`/pages/edit/${encodeURIComponent(result.page.id)}`}>{t("openCopy")}</Link>
            </Button>
          ) : (
            <>
              <Button variant="outline" onClick={() => close(false)}>
                {t("cancel")}
              </Button>
              {sizedFor && (
                <Button disabled={duplicate.isPending} onClick={() => duplicate.mutate(sizedFor.id)}>
                  {tq("makeTheCopy")}
                </Button>
              )}
            </>
          )}
        </Footer>
      </Content>
    </Root>
  );
}

/** The Page tab (04d 4.3 Inspector, drawn): duration, transition, missing-data fallback, copy. */
export function IdePageTab({
  ide,
  builderRef,
  onMakeCopy,
}: {
  ide: CreatorIdeState;
  pageId: string;
  builderRef: RefObject<PageBuilderHandle | null>;
  onMakeCopy: () => void;
}) {
  const t = useTranslations("creatorIde");
  const tq = useTranslations("ideQuiet");
  const tTransitions = useTranslations("transitionSettings");
  const tBuilder = useTranslations("pageBuilder");
  const snapshot = ide.builder.snapshot;
  const references = templateReferences(snapshot?.template ?? []);
  const fallbacks = references.fallbacks;
  const boardName = ide.pageBoard?.name ?? t("aDisplay");
  const strategy = snapshot?.transition_strategy ?? null;
  const transitionKey = TRANSITIONS.find((option) => option.value === strategy)?.labelKey;
  const transitionPlugins = usePageTransitionPlugins(strategy);
  const stage = (settings: { duration_seconds?: number; transition_strategy?: string | null }) =>
    builderRef.current?.setPageSettings(settings);
  const transitionOptions = [
    { value: INHERIT, label: tBuilder("transitionUseDisplayTransition") },
    ...TRANSITIONS.map((option) => ({
      value: option.value,
      label: tTransitions(`strategies.${option.labelKey}.label`),
      group: tBuilder("transitionBuiltInGroup"),
    })),
    ...transitionPlugins.plugins.map((plugin) => ({ value: `${PLUGIN_PREFIX}${plugin.id}`, label: plugin.name })),
    ...(transitionPlugins.pluginId &&
    !transitionPlugins.plugins.some((plugin) => plugin.id === transitionPlugins.pluginId)
      ? [{ value: `${PLUGIN_PREFIX}${transitionPlugins.pluginId}`, label: transitionPlugins.current ?? "" }]
      : []),
  ];
  return (
    <List gap="0" role="list" data-slot="ide-page-tab">
      <ListItem>
        <PageSettingMenu
          label={t("pageDuration")}
          row={{
            title: t("pageDuration"),
            detail: t("pageDurationDetail"),
            value: formatDuration(snapshot?.duration_seconds ?? 300, t),
            chevron: true,
          }}
          value={String(snapshot?.duration_seconds ?? 300)}
          options={DURATION_CHOICES.map((seconds) => ({ value: String(seconds), label: formatDuration(seconds, t) }))}
          onChange={(value) => stage({ duration_seconds: Number(value) })}
        />
      </ListItem>
      <ListItem>
        <PageSettingMenu
          label={t("transition")}
          row={{
            title: t("transition"),
            detail: strategy
              ? t("transitionOverrides", { board: boardName })
              : t("transitionInherits", { board: boardName }),
            value: transitionKey
              ? tTransitions(`strategies.${transitionKey}.label`)
              : (transitionPlugins.current ?? t("displayDefault")),
            chevron: true,
          }}
          value={strategy ?? INHERIT}
          options={transitionOptions}
          onChange={(value) => stage({ transition_strategy: value === INHERIT ? null : value })}
        />
      </ListItem>
      <ListItem>
        <InspectorRow
          title={t("whenMissing")}
          // UX-7-2: a disabled row says what to do, not that nothing is there.
          detail={fallbacks.length ? t("fallbackCount", { count: fallbacks.length }) : tq("fallbackHint")}
          value={fallbacks.length ? t("fallbackText") : undefined}
          chevron={fallbacks.length > 0}
          disabled={!fallbacks.length}
          onPress={() => fallbacks[0] && jumpToTemplateLine(fallbacks[0].line)}
        />
      </ListItem>
      <ListItem>
        <InspectorRow title={t("makeCopy")} detail={t("makeCopyDetail")} chevron onPress={onMakeCopy} />
      </ListItem>
      {/* D6: Delete lives here, not beside the title; the editor confirms first. */}
      <ListItem>
        <InspectorRow
          title={
            <Text as="span" tone="destructive">
              {t("deletePage")}
            </Text>
          }
          detail={t("deletePageDetail")}
          onPress={() => builderRef.current?.requestDelete()}
        />
      </ListItem>
    </List>
  );
}

import {
  type BoardCellGrid,
  Box,
  Button,
  Heading,
  Input,
  List,
  ListItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
  Textarea,
  TextLink,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { DevicePreview } from "@/components/device-preview";
import { useTranslations } from "@/i18n/translations";
import {
  api,
  ApiError,
  type BoardInstance,
  type FlexibleBlock,
  type Page,
  type PageCreate,
  type PageUpdate,
} from "@/lib/api";
import { appUrl } from "@/lib/base-path";
import { dimensionsOf } from "@/lib/board-dimensions";
import { resolveBoardModel } from "@/lib/device-preview";

import { CanvasBlockEditor, type CanvasBlockEditorHandle } from "./canvas-block-editor";
import { Choice, StyleFields } from "./style-fields";
import { TargetFields } from "./target-fields";

export type FlexibleEditorPage = PageCreate &
  Pick<Partial<Page>, "id" | "revision" | "document_protocol" | "edit_protocol">;

export interface FlexiblePageEditorProps {
  initialPage: FlexibleEditorPage;
  boards: BoardInstance[];
  targetBoardId?: string;
  onClose: () => void;
  onSave: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}

/** The edit payload deliberately excludes server identity and legacy grid fields. */
function contentOf(page: FlexibleEditorPage): PageCreate {
  return {
    name: page.name,
    type: "flexible",
    duration_seconds: page.duration_seconds ?? 300,
    blocks: page.blocks ?? [],
    style: page.style ?? null,
    layout: page.layout ?? { kind: "stack" },
    targets: page.targets ?? null,
    transition_strategy: page.transition_strategy,
    transition_interval_ms: page.transition_interval_ms,
    transition_step_size: page.transition_step_size,
  };
}

export function FlexiblePageEditor({
  initialPage,
  boards,
  targetBoardId,
  onClose,
  onSave,
  onDirtyChange,
}: FlexiblePageEditorProps) {
  const t = useTranslations("flexibleEditor");
  const client = useQueryClient();
  const [history, setHistory] = useState(() => ({
    past: [] as PageCreate[],
    present: contentOf(initialPage),
    future: [] as PageCreate[],
  }));
  const draft = history.present;
  // Revision belongs to the loaded draft, never a later query refresh.
  const [baseRevision, setBaseRevision] = useState(initialPage.revision);
  const [original, setOriginal] = useState(() => JSON.stringify(contentOf(initialPage)));
  const [persisted, setPersisted] = useState(!!initialPage.id);
  const repairRefs = useRef(new Map<string, CanvasBlockEditorHandle>());
  const [localDrafts, setLocalDrafts] = useState<Record<string, boolean>>({});
  const [pendingDrafts, setPendingDrafts] = useState<Record<string, boolean>>({});
  const hasPendingDraft = (draft.blocks ?? []).some((block) => pendingDrafts[block.id]);
  const dirty =
    hasPendingDraft ||
    (draft.blocks ?? []).some((block) => localDrafts[block.id]) ||
    JSON.stringify(draft) !== original;
  const durationValid =
    Number.isInteger(draft.duration_seconds) &&
    (draft.duration_seconds ?? 0) >= 10 &&
    (draft.duration_seconds ?? 0) <= 3600;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const authRequests = useRef({ started: 0, settled: 0 });
  const recordAuthentication = (requestId: number, cause?: unknown) => {
    // Only confirmed authentication outcomes replace the notice. Request order
    // keeps a late preview from undoing the result of a newer save or preview.
    if (cause !== undefined && !(cause instanceof ApiError && [400, 401, 403, 404, 412, 422].includes(cause.status)))
      return;
    if (requestId < authRequests.current.settled) return;
    authRequests.current.settled = requestId;
    setNeedsSignIn(cause instanceof ApiError && cause.status === 401);
  };
  const [previewId, setPreviewId] = useState(targetBoardId ?? boards[0]?.id ?? "");
  const board = boards.find((b) => b.id === previewId) ?? boards[0];
  const [previewDraft, setPreviewDraft] = useState(draft);
  const nextId = useRef(1);
  const editorRef = useRef<HTMLDivElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const blockRefs = useRef(new Map<string, HTMLElement>());
  const previewRef = useRef<HTMLElement>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const revealElement = (element: HTMLElement | null | undefined) => {
    if (!element) return;
    element.scrollIntoView({ block: "start", behavior: "instant" });
    const clearance = (actionsRef.current?.getBoundingClientRect().bottom ?? 0) + 12;
    const offset = element.getBoundingClientRect().top - clearance;
    const workspace = editorRef.current?.closest<HTMLElement>("[data-flexible-workspace]");
    if (workspace) workspace.scrollBy({ top: offset, behavior: "instant" });
    else window.scrollBy({ top: offset, behavior: "instant" });
    element.focus({ preventScroll: true });
  };
  const revealBlock = (id: string) => revealElement(blockRefs.current.get(id));

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    const timer = window.setTimeout(() => setPreviewDraft(draft), 250);
    return () => window.clearTimeout(timer);
  }, [draft]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const preview = useQuery({
    queryKey: ["flexible-preview", board?.id, previewDraft],
    queryFn: async () => {
      const requestId = ++authRequests.current.started;
      try {
        const rendered = await api.previewFlexiblePage(previewDraft, board?.id, { skipAuthRedirect: true });
        recordAuthentication(requestId);
        return rendered;
      } catch (cause) {
        recordAuthentication(requestId, cause);
        throw cause;
      }
    },
    enabled: !!board,
    retry: false,
  });
  const change = (next: PageCreate) =>
    setHistory((h) => ({ past: [...h.past.slice(-99), h.present], present: next, future: [] }));
  const blocks = draft.blocks ?? [];
  const replace = (index: number, block: FlexibleBlock) =>
    change({ ...draft, blocks: blocks.map((b, i) => (i === index ? block : b)) });
  const add = (kind: string) => {
    let id: string;
    do {
      id = `block_${nextId.current++}`;
    } while (blocks.some((b) => b.id === id));
    const block: FlexibleBlock = { id, kind };
    if (kind === "text") block.text = "";
    if (kind === "spacer") block.style = { height: 1 };
    if (kind === "canvas") {
      block.canvas = { content: { size: [8, 8], shapes: [] } };
      block.style = { height: 8 };
    }
    change({ ...draft, blocks: [...blocks, block] });
  };
  const move = (index: number, direction: number) => {
    const next = [...blocks];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    change({ ...draft, blocks: next });
  };
  const save = async () => {
    if (hasPendingDraft || !durationValid) return;
    const requestId = ++authRequests.current.started;
    setError(null);
    setSaving(true);
    try {
      if (initialPage.id) {
        const { type: _type, ...fields } = draft;
        const saved = await api.updatePage(
          initialPage.id,
          {
            ...fields,
            expected_revision: baseRevision,
          } satisfies PageUpdate,
          { skipAuthRedirect: true },
        );
        setBaseRevision(saved.page.revision);
        client.setQueryData(["page", initialPage.id], saved.page);
        if (saved.incompatible_references.length) {
          toast.warning(
            t("targetWarning", {
              list: [...new Set(saved.incompatible_references.map((ref) => ref.board_name))].join(", "),
            }),
            { duration: 10000 },
          );
        }
      } else await api.createPage(draft, { skipAuthRedirect: true });
      recordAuthentication(requestId);
      setPersisted(true);
      setOriginal(JSON.stringify(draft));
      onDirtyChange?.(false);
      await client.invalidateQueries({ queryKey: ["pages"] });
      onSave();
    } catch (cause) {
      recordAuthentication(requestId, cause);
      if (!(cause instanceof ApiError && cause.status === 401)) {
        setError(cause instanceof Error ? cause.message : t("saveFailed"));
      }
    } finally {
      setSaving(false);
    }
  };
  const dims = board ? dimensionsOf(board) : null;
  const pixelFrame =
    preview.data?.raw?.text_representation === "cell_projection" ? preview.data.layers?.[0] : undefined;
  return (
    <Stack ref={editorRef} gap="4" className="p-4">
      <Heading level={2} className="text-lg font-semibold">
        {t("title")}
      </Heading>
      <Text className="text-sm text-muted-foreground">{t("description")}</Text>
      <Box
        ref={actionsRef}
        role="group"
        aria-label={t("actions")}
        className="sticky top-0 z-20 space-y-2 border-b bg-card py-2"
      >
        {needsSignIn && (
          <Box role="alert" className="space-y-1 text-sm">
            <Text>{t("signInRecovery")}</Text>
            <TextLink href={appUrl("/login")} target="_blank" rel="noopener noreferrer">
              {t("signInAnotherTab")}
            </TextLink>
          </Box>
        )}
        {error && (
          <Text role="alert" className="text-sm text-destructive">
            {error}
          </Text>
        )}
        <Box className="flex flex-wrap items-center gap-2">
          <Button onClick={onClose} variant="outline" disabled={saving}>
            {t("close")}
          </Button>
          <Button
            onClick={() =>
              setHistory((h) => ({
                past: h.past.slice(0, -1),
                present: h.past.at(-1)!,
                future: [h.present, ...h.future],
              }))
            }
            variant="outline"
            disabled={saving || hasPendingDraft || !history.past.length}
          >
            {t("undo")}
          </Button>
          <Button
            onClick={() =>
              setHistory((h) => ({ past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) }))
            }
            variant="outline"
            disabled={saving || hasPendingDraft || !history.future.length}
          >
            {t("redo")}
          </Button>
          <Button
            onClick={() => void save()}
            disabled={saving || hasPendingDraft || !durationValid || !draft.name.trim()}
          >
            {saving ? t("saving") : t("save")}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setPreviewOpen(true);
              requestAnimationFrame(() => {
                revealElement(previewRef.current);
              });
            }}
          >
            {t("preview")}
            {preview.data?.layout_issues?.length ? ` (${preview.data.layout_issues.length})` : ""}
          </Button>
          <Text as="span" role="status" className="text-sm text-muted-foreground">
            {!persisted ? t("notSaved") : dirty ? t("unsaved") : t("saved")}
          </Text>
        </Box>
        {hasPendingDraft && (
          <Box role="alert" className="space-y-1 text-sm text-destructive">
            <Text>{t("repairDrafts")}</Text>
            {blocks
              .filter((block) => pendingDrafts[block.id])
              .map((block) => (
                <Button
                  key={block.id}
                  variant="link"
                  onClick={() => {
                    repairRefs.current.get(block.id)?.focusInvalid();
                    if (document.activeElement instanceof HTMLElement) revealElement(document.activeElement);
                  }}
                >
                  {t("fixBlock", { number: blocks.findIndex((candidate) => candidate.id === block.id) + 1 })}
                </Button>
              ))}
          </Box>
        )}
      </Box>
      <Box className="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,22rem)]">
        <fieldset disabled={saving} className="order-2 min-w-0 space-y-4 lg:order-1">
          <Box className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_9rem]">
            <label className="block">
              {t("name")}
              <Input
                aria-label="Name"
                value={draft.name}
                maxLength={100}
                onChange={(e) => change({ ...draft, name: e.target.value })}
              />
            </label>
            <label className="block">
              {t("duration")}
              <Input
                aria-label="Duration (seconds)"
                aria-invalid={!durationValid || undefined}
                type="number"
                min={10}
                max={3600}
                value={draft.duration_seconds}
                onChange={(e) => change({ ...draft, duration_seconds: Number(e.target.value) })}
              />
              {!durationValid && (
                <Text role="alert" className="text-sm text-destructive">
                  {t("durationInvalid")}
                </Text>
              )}
            </label>
          </Box>
          <TargetFields targets={draft.targets} boards={boards} onChange={(targets) => change({ ...draft, targets })} />
          <details>
            <summary>{t("pageStyle")}</summary>
            <Box className="space-y-3 pt-3">
              <Text className="text-sm">{t("styleHelp")}</Text>
              <StyleFields label={t("page")} style={draft.style} onChange={(style) => change({ ...draft, style })} />
              <Choice
                label={t("verticalAlignment")}
                value={String(draft.layout?.valign ?? "top")}
                values={["top", "middle", "bottom", "spread"]}
                onChange={(valign) => change({ ...draft, layout: { ...draft.layout, valign: valign || "top" } })}
              />
              <Choice
                label={t("gap")}
                value={String(draft.layout?.gap ?? "small")}
                values={["none", "small", "medium", "large"]}
                onChange={(gap) => change({ ...draft, layout: { ...draft.layout, gap: gap || "small" } })}
              />
            </Box>
          </details>
          {blocks.map((block, index) => {
            const label = t("block", { number: index + 1 });
            return (
              <Box
                as="section"
                key={block.id}
                aria-label={`${label} (${block.kind})`}
                ref={(element: HTMLElement | null) => {
                  if (element) blockRefs.current.set(block.id, element);
                  else blockRefs.current.delete(block.id);
                }}
                tabIndex={-1}
                className="space-y-3 border-t pt-4 outline-offset-4 scroll-mt-40"
              >
                <Box className="flex flex-wrap items-center gap-2">
                  <Heading level={3} className="mr-auto font-medium">
                    {label}: {block.kind}
                  </Heading>
                  <Box className="flex flex-wrap gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Move block ${index + 1} up`}
                      disabled={index === 0}
                      onClick={() => move(index, -1)}
                    >
                      {t("up")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Move block ${index + 1} down`}
                      disabled={index === blocks.length - 1}
                      onClick={() => move(index, 1)}
                    >
                      {t("down")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Remove block ${index + 1}`}
                      onClick={() => {
                        setPendingDrafts((previous) => {
                          const next = { ...previous };
                          delete next[block.id];
                          return next;
                        });
                        change({ ...draft, blocks: blocks.filter((_, i) => i !== index) });
                      }}
                    >
                      {t("remove")}
                    </Button>
                  </Box>
                </Box>
                {block.kind === "text" && (
                  <Textarea
                    aria-label={`${label} text`}
                    value={block.text ?? ""}
                    onChange={(e) => replace(index, { ...block, text: e.target.value })}
                  />
                )}
                {block.kind === "canvas" && (
                  <CanvasBlockEditor
                    ref={(handle) => {
                      if (handle) repairRefs.current.set(block.id, handle);
                      else repairRefs.current.delete(block.id);
                    }}
                    block={block}
                    label={label}
                    onChange={(next) => replace(index, next)}
                    onPendingChange={(pending) =>
                      setPendingDrafts((previous) =>
                        previous[block.id] === pending ? previous : { ...previous, [block.id]: pending },
                      )
                    }
                    onDraftChange={(dirty) =>
                      setLocalDrafts((previous) =>
                        previous[block.id] === dirty ? previous : { ...previous, [block.id]: dirty },
                      )
                    }
                  />
                )}
                {!["text", "canvas", "spacer"].includes(block.kind) && <Text>{t("unknownBlock")}</Text>}
                <details>
                  <summary>{t("blockStyle", { label })}</summary>
                  <Box className="space-y-3 pt-3">
                    <StyleFields
                      label={label}
                      style={block.style}
                      onChange={(style) => replace(index, { ...block, style })}
                    />
                    <label className="block">
                      {t("showWhen")}
                      <Input
                        aria-label={`${label} condition`}
                        value={block.if ?? ""}
                        onChange={(e) => replace(index, { ...block, if: e.target.value || null })}
                      />
                    </label>
                    <label className="block">
                      {t("priority")}
                      <Input
                        aria-label={`${label} priority`}
                        type="number"
                        min={0}
                        max={1000}
                        value={block.priority ?? ""}
                        onChange={(e) =>
                          replace(index, { ...block, priority: e.target.value === "" ? null : Number(e.target.value) })
                        }
                      />
                    </label>
                  </Box>
                </details>
              </Box>
            );
          })}
          <Box className="flex flex-wrap gap-2">
            {["text", "canvas", "spacer"].map((kind) => (
              <Button key={kind} variant="outline" disabled={blocks.length >= 32} onClick={() => add(kind)}>
                {t("add", { kind })}
              </Button>
            ))}
          </Box>
        </fieldset>
        <Box
          as="section"
          ref={previewRef}
          tabIndex={-1}
          aria-label="Display preview"
          className={`${previewOpen ? "block" : "hidden"} order-1 min-w-0 space-y-3 outline-offset-4 scroll-mt-40 lg:order-2 lg:block`}
        >
          <Button
            className="lg:hidden"
            variant="outline"
            onClick={() => {
              setPreviewOpen(false);
              if (blocks[0]) revealBlock(blocks[0].id);
            }}
          >
            {t("backToEditing")}
          </Button>
          <Heading level={3} className="font-medium">
            {t("preview")}
          </Heading>
          {!board ? (
            <Text>{t("noDisplay")}</Text>
          ) : (
            <>
              <label>
                {t("previewDisplay")}
                <Select value={board.id} onValueChange={setPreviewId}>
                  <SelectTrigger aria-label={t("previewDisplay")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {boards.map((b) => (
                      <SelectItem key={b.id} value={b.id}>
                        {b.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <Text className="text-sm">
                {pixelFrame
                  ? t("previewPixelDescription", { width: pixelFrame.width, height: pixelFrame.height })
                  : t("previewDescription", { cols: dims?.cols ?? 0, rows: dims?.rows ?? 0 })}
              </Text>
              {pixelFrame && <Text className="text-sm text-muted-foreground">{t("projectionHelp")}</Text>}
              {preview.isFetching && <Text role="status">{t("rendering")}</Text>}
              {preview.error && (
                <Box className="space-y-2">
                  {!(preview.error instanceof ApiError && preview.error.status === 401) && (
                    <Text role="alert" className="text-sm text-destructive">
                      {preview.error.message}
                    </Text>
                  )}
                  <Button variant="outline" onClick={() => void preview.refetch()}>
                    {t("retryPreview")}
                  </Button>
                </Box>
              )}
              {preview.data && (
                <DevicePreview
                  model={resolveBoardModel(board)}
                  message={preview.data.message}
                  cells={preview.data.cells as BoardCellGrid | undefined}
                  layers={preview.data.layers}
                  ledLayout={board.led_layout}
                  previewLabel={t("computedPreview", { name: board.name })}
                >
                  <pre aria-label={t("characterPreview", { name: board.name })} className="overflow-auto font-mono">
                    {preview.data.lines.join("\n")}
                  </pre>
                </DevicePreview>
              )}
              {!!preview.data?.layout_issues?.length && (
                <List aria-label="Layout issues">
                  {preview.data.layout_issues.map((issue, i) => {
                    const index =
                      issue.path[0] === "blocks" ? blocks.findIndex((block) => block.id === issue.path[1]) : -1;
                    const label =
                      index >= 0 ? `${t("block", { number: index + 1 })} (${blocks[index].kind})` : t("page");
                    return (
                      <ListItem key={i} className="space-y-1 text-sm">
                        <Text className={issue.severity === "warning" ? "font-medium" : "text-muted-foreground"}>
                          {t(issue.severity === "warning" ? "warning" : "information")}: {issue.message}
                        </Text>
                        {index >= 0 && (
                          <Button variant="link" size="sm" onClick={() => revealBlock(blocks[index].id)}>
                            {t("goToBlock", { label })}
                          </Button>
                        )}
                      </ListItem>
                    );
                  })}
                </List>
              )}
            </>
          )}
        </Box>
      </Box>
    </Stack>
  );
}

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
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { DevicePreview } from "@/components/device-preview";
import { useTranslations } from "@/i18n/translations";
import { api, type BoardInstance, type FlexibleBlock, type Page, type PageCreate, type PageUpdate } from "@/lib/api";
import { dimensionsOf } from "@/lib/board-dimensions";
import { resolveBoardModel } from "@/lib/device-preview";

import { CanvasBlockEditor } from "./canvas-block-editor";
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
  const [pendingDrafts, setPendingDrafts] = useState<Record<string, boolean>>({});
  const hasPendingDraft = (draft.blocks ?? []).some((block) => pendingDrafts[block.id]);
  const dirty = hasPendingDraft || JSON.stringify(draft) !== original;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState(targetBoardId ?? boards[0]?.id ?? "");
  const board = boards.find((b) => b.id === previewId) ?? boards[0];
  const [previewDraft, setPreviewDraft] = useState(draft);
  const nextId = useRef(1);
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
    queryFn: () => api.previewFlexiblePage(previewDraft, board?.id),
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
    if (hasPendingDraft) return;
    setError(null);
    setSaving(true);
    try {
      if (initialPage.id) {
        const { type: _type, ...fields } = draft;
        const saved = await api.updatePage(initialPage.id, {
          ...fields,
          expected_revision: baseRevision,
        } satisfies PageUpdate);
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
      } else await api.createPage(draft);
      setOriginal(JSON.stringify(draft));
      onDirtyChange?.(false);
      await client.invalidateQueries({ queryKey: ["pages"] });
      onSave();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t("saveFailed"));
    } finally {
      setSaving(false);
    }
  };
  const dims = board ? dimensionsOf(board) : null;
  return (
    <Stack gap="4" className="p-4">
      <Heading level={2} className="text-lg font-semibold">
        {t("title")}
      </Heading>
      <Text className="text-sm text-muted-foreground">{t("description")}</Text>
      {error && <Text role="alert">{error}</Text>}
      <fieldset disabled={saving} className="space-y-4">
        <Box className="flex flex-wrap gap-2">
          <Button onClick={onClose} variant="outline">
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
            disabled={hasPendingDraft || !history.past.length}
          >
            {t("undo")}
          </Button>
          <Button
            onClick={() =>
              setHistory((h) => ({ past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1) }))
            }
            disabled={hasPendingDraft || !history.future.length}
          >
            {t("redo")}
          </Button>
          <Button onClick={() => void save()} disabled={hasPendingDraft || !draft.name.trim()}>
            {saving ? t("saving") : t("save")}
          </Button>
          <Text as="span" role="status">
            {dirty ? t("unsaved") : t("saved")}
          </Text>
        </Box>
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
            type="number"
            min={10}
            max={3600}
            value={draft.duration_seconds}
            onChange={(e) => change({ ...draft, duration_seconds: Number(e.target.value) })}
          />
        </label>
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
              className="space-y-3 rounded-md border p-3"
            >
              <Box className="flex flex-wrap items-center gap-2">
                <Heading level={3} className="mr-auto font-medium">
                  {label}: {block.kind}
                </Heading>
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
              {block.kind === "text" && (
                <Textarea
                  aria-label={`${label} text`}
                  value={block.text ?? ""}
                  onChange={(e) => replace(index, { ...block, text: e.target.value })}
                />
              )}
              {block.kind === "canvas" && (
                <CanvasBlockEditor
                  block={block}
                  label={label}
                  onChange={(next) => replace(index, next)}
                  onPendingChange={(pending) => setPendingDrafts((previous) => ({ ...previous, [block.id]: pending }))}
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
        <Box className="flex gap-2">
          {["text", "canvas", "spacer"].map((kind) => (
            <Button key={kind} variant="outline" disabled={blocks.length >= 32} onClick={() => add(kind)}>
              {t("add", { kind })}
            </Button>
          ))}
        </Box>
      </fieldset>
      <Box as="section" aria-label="Display preview" className="space-y-3 border-t pt-4">
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
            <Text className="text-sm">{t("previewDescription", { cols: dims?.cols ?? 0, rows: dims?.rows ?? 0 })}</Text>
            {preview.isFetching && <Text role="status">{t("rendering")}</Text>}
            {preview.error && <Text role="alert">{preview.error.message}</Text>}
            {preview.data && (
              <DevicePreview
                model={resolveBoardModel(board)}
                message={preview.data.message}
                cells={preview.data.cells as BoardCellGrid | undefined}
                layers={preview.data.layers}
                ledLayout={board.led_layout}
                previewLabel={`${board.name} computed preview`}
              >
                <pre aria-label={`${board.name} character preview`} className="overflow-auto font-mono">
                  {preview.data.lines.join("\n")}
                </pre>
              </DevicePreview>
            )}
            {!!preview.data?.layout_issues?.length && (
              <List aria-label="Layout issues">
                {preview.data.layout_issues.map((issue, i) => (
                  <ListItem key={i}>
                    {issue.path.join(" / ")}: {issue.message}
                  </ListItem>
                ))}
              </List>
            )}
          </>
        )}
      </Box>
    </Stack>
  );
}

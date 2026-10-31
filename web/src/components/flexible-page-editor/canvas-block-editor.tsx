import { Box, Input, Tabs, TabsContent, TabsList, TabsTrigger, Text } from "@fiestaboard/ui";
import { type Ref, useEffect, useImperativeHandle, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { CanvasDrawTab } from "@/components/canvas-editor/canvas-draw-tab";
import { CanvasShapesEditor, type CanvasShapesEditorHandle } from "@/components/canvas-editor/canvas-shapes-editor";
import { CanvasSourcePicker } from "@/components/canvas-editor/canvas-source-picker";
import { useTranslations } from "@/i18n/translations";
import type { FlexibleBlock } from "@/lib/api";

export interface CanvasBlockEditorHandle {
  focusInvalid: () => void;
}

export function CanvasBlockEditor({
  block,
  label,
  onChange,
  onPendingChange,
  onDraftChange,
  ref,
}: {
  ref?: Ref<CanvasBlockEditorHandle>;
  block: FlexibleBlock;
  label: string;
  onChange: (block: FlexibleBlock) => void;
  onPendingChange?: (pending: boolean) => void;
  onDraftChange?: (dirty: boolean) => void;
}) {
  const t = useTranslations("flexibleEditor");
  const body = block.canvas ?? {};
  const content = body.content ?? {};
  const [sizeDraft, setSizeDraft] = useState<[string, string] | null>(null);
  const [invalidJson, setInvalidJson] = useState(false);
  const [tab, setTab] = useState(body.source ? "source" : "draw");
  const shapesRef = useRef<CanvasShapesEditorHandle>(null);
  const sizeFields = useRef<HTMLDivElement>(null);
  const sizeKey = JSON.stringify(content.size ?? null);
  const [seenSize, setSeenSize] = useState(sizeKey);
  if (seenSize !== sizeKey) {
    setSeenSize(sizeKey);
    setSizeDraft(null);
  }
  const [width, height] = content.size ?? [8, 8];
  const values = sizeDraft ?? (content.size ? [String(width), String(height)] : ["", ""]);
  const validSize = values.every(
    (value) => value !== "" && Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 128,
  );
  const invalidSize = sizeDraft !== null && !validSize;
  useEffect(() => {
    onPendingChange?.(invalidSize || invalidJson);
    onDraftChange?.(sizeDraft !== null);
  }, [invalidSize, invalidJson, sizeDraft, onPendingChange, onDraftChange]);
  const update = (next: typeof content) => onChange({ ...block, canvas: { ...body, content: next } });
  const commitSize = () => {
    if (sizeDraft && validSize) {
      update({ ...content, size: [Number(values[0]), Number(values[1])] });
      setSizeDraft(null);
    }
  };
  useImperativeHandle(ref, () => ({
    focusInvalid() {
      if (invalidSize) sizeFields.current?.querySelector<HTMLInputElement>('input[aria-invalid="true"]')?.focus();
      else if (invalidJson) {
        flushSync(() => setTab("shapes"));
        shapesRef.current?.focusJson();
      }
    },
  }));
  return (
    <Box className="space-y-3">
      <Box ref={sizeFields} className="flex gap-3">
        {["width", "height"].map((axis, index) => (
          <label key={axis}>
            <Text as="span" className="text-sm">
              {t("canvasDimension", { label, axis })}
            </Text>
            <Input
              type="number"
              min={1}
              max={128}
              aria-label={`${label} canvas ${axis}`}
              value={values[index]}
              aria-invalid={
                (invalidSize &&
                  (values[index] === "" ||
                    !Number.isInteger(Number(values[index])) ||
                    Number(values[index]) < 1 ||
                    Number(values[index]) > 128)) ||
                undefined
              }
              onBlur={commitSize}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitSize();
                }
              }}
              onChange={(event) => {
                const next: [string, string] = [values[0], values[1]];
                next[index] = event.target.value;
                setSizeDraft(next);
                // Automatic-size canvases need both dimensions before a draw surface exists.
                if (
                  !content.size &&
                  next.every(
                    (value) =>
                      value !== "" && Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 128,
                  )
                ) {
                  update({ ...content, size: [Number(next[0]), Number(next[1])] });
                  setSizeDraft(null);
                }
              }}
            />
          </label>
        ))}
      </Box>
      {invalidSize && (
        <Text role="alert" className="text-sm text-destructive">
          {t("sizeInvalid")}
        </Text>
      )}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="draw">{t("draw")}</TabsTrigger>
          <TabsTrigger value="shapes">{t("shapes")}</TabsTrigger>
          <TabsTrigger value="source">{t("source")}</TabsTrigger>
        </TabsList>
        <TabsContent value="draw">
          {content.size ? (
            <CanvasDrawTab
              content={content}
              source={body.source}
              width={width}
              height={height}
              onContentChange={(next) => update({ ...content, ...next })}
            />
          ) : (
            <Text>{t("canvasSizeRequired")}</Text>
          )}
        </TabsContent>
        <TabsContent value="shapes" keepMounted>
          <CanvasShapesEditor
            ref={shapesRef}
            shapes={content.shapes ?? []}
            onChange={(shapes) => update({ ...content, shapes })}
            onInvalidChange={(invalid) => {
              setInvalidJson(invalid);
            }}
          />
        </TabsContent>
        <TabsContent value="source">
          <CanvasSourcePicker
            source={body.source}
            onChange={(source) => onChange({ ...block, canvas: { ...body, source } })}
          />
          <Text className="text-sm text-muted-foreground">{t("fallbackHelp")}</Text>
        </TabsContent>
      </Tabs>
    </Box>
  );
}

import { Box, Input, Tabs, TabsContent, TabsList, TabsTrigger, Text } from "@fiestaboard/ui";
import { useState } from "react";

import { CanvasDrawTab } from "@/components/canvas-editor/canvas-draw-tab";
import { CanvasShapesEditor } from "@/components/canvas-editor/canvas-shapes-editor";
import { CanvasSourcePicker } from "@/components/canvas-editor/canvas-source-picker";
import { useTranslations } from "@/i18n/translations";
import type { FlexibleBlock } from "@/lib/api";

export function CanvasBlockEditor({
  block,
  label,
  onChange,
  onPendingChange,
}: {
  block: FlexibleBlock;
  label: string;
  onChange: (block: FlexibleBlock) => void;
  onPendingChange?: (pending: boolean) => void;
}) {
  const t = useTranslations("flexibleEditor");
  const body = block.canvas ?? {};
  const content = body.content ?? {};
  const [sizeDraft, setSizeDraft] = useState<[string, string]>(["", ""]);
  const [invalidJson, setInvalidJson] = useState(false);
  const [pendingSize, setPendingSize] = useState(false);
  const [width, height] = content.size ?? [8, 8];
  const update = (next: typeof content) => onChange({ ...block, canvas: { ...body, content: next } });
  return (
    <Box className="space-y-3">
      <Box className="flex gap-3">
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
              value={content.size ? (index === 0 ? width : height) : sizeDraft[index]}
              onChange={(e) => {
                if (!content.size) {
                  const next: [string, string] = [...sizeDraft];
                  next[index] = e.target.value;
                  setSizeDraft(next);
                  const valid = next.every(
                    (value) =>
                      value !== "" && Number.isInteger(Number(value)) && Number(value) >= 1 && Number(value) <= 128,
                  );
                  const pending = !valid && next.some(Boolean);
                  setPendingSize(pending);
                  onPendingChange?.(pending || invalidJson);
                  if (valid) {
                    update({ ...content, size: [Number(next[0]), Number(next[1])] });
                    setSizeDraft(["", ""]);
                  }
                  return;
                }
                const value = Number(e.target.value);
                if (Number.isInteger(value) && value >= 1 && value <= 128)
                  update({ ...content, size: index === 0 ? [value, height] : [width, value] });
              }}
            />
          </label>
        ))}
      </Box>
      <Tabs defaultValue={body.source ? "source" : "draw"}>
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
            shapes={content.shapes ?? []}
            onChange={(shapes) => update({ ...content, shapes })}
            onInvalidChange={(invalid) => {
              setInvalidJson(invalid);
              onPendingChange?.(invalid || pendingSize);
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

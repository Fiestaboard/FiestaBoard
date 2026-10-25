"use client";

// The Source tab of the page editor's canvas panel: a plugin variable whose
// manifest format is "canvas" (it yields a content object), or any
// expression. When the source yields content it replaces the canvas's own.

import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { useId, useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { canvasSourceVariables } from "@/lib/canvas-editing";

const NONE = "__none__";

interface CanvasSourcePickerProps {
  source: string | null | undefined;
  onChange: (source: string | null) => void;
}

export function CanvasSourcePicker({ source, onChange }: CanvasSourcePickerProps) {
  const t = useTranslations("canvasEditor");
  const selectId = useId();
  const exprId = useId();
  const { data } = useQuery({
    queryKey: ["template-variables"],
    queryFn: () => api.getTemplateVariables(),
    staleTime: 60_000,
  });
  const variables = useMemo(() => canvasSourceVariables(data), [data]);
  const selected = variables.find((v) => source?.trim() === `{{${v.token}}}`)?.token ?? NONE;

  return (
    <Stack gap="3">
      <Text size="xs" tone="muted">
        {t("sourceHint")}
      </Text>
      <Stack gap="1">
        <Label htmlFor={selectId} className="text-xs">
          {t("sourceVariable")}
        </Label>
        {variables.length === 0 ? (
          <Text size="sm" tone="muted" data-testid="canvas-source-empty">
            {t("sourceNoVariables")}
          </Text>
        ) : (
          <Select
            value={selected}
            onValueChange={(value) => onChange(!value || value === NONE ? null : `{{${value}}}`)}
          >
            <SelectTrigger id={selectId} className="h-8 text-xs" aria-label={t("sourceVariable")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE} className="text-xs">
                {t("sourceNone")}
              </SelectItem>
              {variables.map((v) => (
                <SelectItem key={v.token} value={v.token} className="text-xs">
                  {v.description ? `${v.token} — ${v.description}` : v.token}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Stack>
      <Stack gap="1">
        <Label htmlFor={exprId} className="text-xs">
          {t("sourceExpression")}
        </Label>
        <Input
          id={exprId}
          value={source ?? ""}
          placeholder="{{generative_ai_art.canvas}}"
          spellCheck={false}
          className="h-8 font-mono text-xs"
          onChange={(e) => onChange(e.target.value.trim() ? e.target.value : null)}
        />
      </Stack>
      {source && (
        <Button size="sm" variant="ghost" className="self-start" onClick={() => onChange(null)}>
          {t("sourceClear")}
        </Button>
      )}
    </Stack>
  );
}

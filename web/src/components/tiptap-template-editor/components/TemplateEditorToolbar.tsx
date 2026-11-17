"use client";

import {
  type ColorPickerLabels,
  DEFAULT_TEMPLATE_EDITOR_TOOLBAR_LABELS,
  TemplateEditorToolbar as KitToolbar,
  type TemplateEditorToolbarProps,
  type ToolbarTemplateVariables,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { createPortal } from "react-dom";

import { EditorTabletTools } from "@/components/editor-tablet-tools";
import { HomeAssistantEntityPicker } from "@/components/home-assistant-entity-picker";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

import type { DrawBrush } from "../utils/draw-mode";

const VariablePickerContent = lazy(() =>
  import("./VariablePickerContent").then((m) => ({ default: m.VariablePickerContent })),
);

/** Host data and translations; all toolbar presentation belongs to the kit. */
export function TemplateEditorToolbar(
  props: Omit<TemplateEditorToolbarProps, "drawBrush" | "onDrawBrushChange"> & {
    drawBrush?: DrawBrush;
    onDrawBrushChange?: (brush: DrawBrush) => void;
  },
) {
  const t = useTranslations("templateEditor");
  const tFormatting = useTranslations("formattingPicker");
  const touch = useMediaQuery("(max-width: 767px), (pointer: coarse)");
  const sheets = useMediaQuery("(max-width: 639px)");
  const { data, isLoading } = useQuery({ queryKey: ["template-variables"], queryFn: api.getTemplateVariables });
  const labels = Object.fromEntries(
    Object.keys(DEFAULT_TEMPLATE_EDITOR_TOOLBAR_LABELS).map((key) => [key, key === "drawColors" ? t.raw(key) : t(key)]),
  );
  const toolbarProps: TemplateEditorToolbarProps = {
    ...props,
    drawBrush:
      props.drawBrush?.kind === "color"
        ? { kind: "color", color: props.drawBrush.color === "filled" ? "black" : props.drawBrush.color }
        : props.drawBrush,
    onDrawBrushChange: (brush) => {
      if (brush.kind !== "icon") props.onDrawBrushChange?.(brush);
    },
    templateVariables: data as ToolbarTemplateVariables | undefined,
    isLoadingVariables: isLoading,
    renderVariablePicker: ({ onInsert }) => (
      <Suspense fallback={null}>
        <VariablePickerContent onInsert={onInsert} />
      </Suspense>
    ),
    entityPickerSlot: data?.variables?.home_assistant
      ? ({ open, onClose, onSelect }) => <HomeAssistantEntityPicker open={open} onClose={onClose} onSelect={onSelect} />
      : undefined,
    labels,
    colorPickerLabels: {
      colorNames: t.raw("drawColors") as ColorPickerLabels["colorNames"],
      colorPickerAriaLabel: t("colorPickerAriaLabel"),
      colorOptionLabel: (name) => t("colorOptionLabel", { color: name }),
      heartCharacterAriaLabel: t("heartCharacterAriaLabel"),
      heartLabel: t("heartLabel"),
      insertHeartTooltip: t("insertHeartTooltip"),
    },
    formattingPickerLabels: {
      noFormattingAvailable: tFormatting("noFormattingAvailable"),
      back: tFormatting("back"),
      selectColor: tFormatting("selectColor"),
      orCustomPattern: tFormatting("orCustomPattern"),
      use: tFormatting("use"),
      colorNames: t.raw("drawColors") as ColorPickerLabels["colorNames"],
      colorOptionLabel: (color) => t("colorOptionLabel", { color }),
    },
    drawCharPickerLabels: {
      characters: t("drawCharacter"),
      degree: t("degreeCharacterAriaLabel"),
      heart: t("heartCharacterAriaLabel"),
      icons: t("icons"),
      iconLabel: (icon) => t("iconOptionLabel", { icon }),
    },
    container: touch && typeof document !== "undefined" ? document.body : props.container,
    size: touch ? "touch" : "default",
    layout: touch ? "docked" : "row",
    pickerPresentation: sheets ? "sheet" : "popover",
  };
  const toolbar = touch && !sheets ? <EditorTabletTools {...toolbarProps} /> : <KitToolbar {...toolbarProps} />;
  return !touch && props.container ? createPortal(toolbar, props.container) : toolbar;
}

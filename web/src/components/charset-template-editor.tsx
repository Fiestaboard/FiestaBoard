"use client";

/**
 * The page editor's rich editor for a board whose character set draws more
 * than split-flap tiles — an LED matrix (an output plugin's board, such as a
 * Divoom Pixoo, or a FiestaPanel drawn as LEDs).
 *
 * It is FiestaUI's `TemplateEditor` given that board's character set, which
 * is what turns the extended markup on: it reads and writes colour spans
 * (`{{red:HOT}}`), block spans (`{{black/white:OPEN}}`) and icons
 * (`{{icon:sun}}`), offers through its toolbar ONLY the forms the set
 * supports, keeps typed lowercase when the set draws it (`mixedCase`), and
 * underlines every cell the set cannot draw as written. A split-flap board
 * never gets here: the page builder keeps its own editor for those, byte for
 * byte, so nothing about a Vestaboard page changes.
 *
 * This file only wires the app in — its catalog (the `templateEditor`
 * namespace, whose keys FiestaUI mirrors 1:1), the template variables, the
 * app's own variable picker and Home Assistant entity picker.
 */
import {
  type CharacterSet,
  type ColorPickerLabels,
  type LineAlignment,
  TemplateEditor,
  type TemplateEditorHandle,
  type TemplateEditorLabels,
  type TemplateEditorToolbarLabels,
  type ToolbarTemplateVariables,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { forwardRef, lazy, Suspense, useMemo } from "react";

import { HomeAssistantEntityPicker } from "@/components/home-assistant-entity-picker";
import { useTranslations } from "@/i18n/translations";
import type { Code62Glyph, DeviceType } from "@/lib/api";
import { api } from "@/lib/api";

// The app's variable picker, lazily — the same chunk the app editor uses, so
// lucide's icon barrel stays out of the editor until the dropdown opens.
const VariablePickerContent = lazy(() =>
  import("@/components/tiptap-template-editor/components/VariablePickerContent").then((m) => ({
    default: m.VariablePickerContent,
  })),
);

/** The toolbar's string labels, every one of which the app's catalog carries under the same key. */
const TOOLBAR_STRING_KEYS = [
  "drawMode",
  "drawModeActive",
  "undo",
  "undoAriaLabel",
  "redo",
  "redoAriaLabel",
  "drawEraser",
  "drawCharacter",
  "cut",
  "cutAriaLabel",
  "copy",
  "copyAriaLabel",
  "paste",
  "pasteAriaLabel",
  "variables",
  "variablesNoVarsAvailable",
  "noVariablesAvailable",
  "homeAssistantEntities",
  "colors",
  "formatting",
  "insertFormula",
  "toggleWrap",
  "enableWrap",
  "disableWrap",
  "alignLeft",
  "alignCenter",
  "alignRight",
  "syncFromBoard",
  "syncFromBoardTooltip",
] as const satisfies readonly (keyof TemplateEditorToolbarLabels)[];

export interface CharsetTemplateEditorProps {
  /** The target board's character set (resolved; an output plugin's own set included). */
  charset: CharacterSet;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  lineAlignments?: LineAlignment[];
  lineWrapEnabled?: boolean[];
  onLineAlignmentChange?: (lineIndex: number, alignment: LineAlignment) => void;
  onLineWrapChange?: (lineIndex: number, wrapEnabled: boolean) => void;
  boardWidth: number;
  boardLines: number;
  deviceType?: DeviceType;
  code62Glyph?: Code62Glyph;
  onSyncFromBoard?: () => void;
  syncFromBoardPending?: boolean;
}

export const CharsetTemplateEditor = forwardRef<TemplateEditorHandle, CharsetTemplateEditorProps>(
  function CharsetTemplateEditor(
    {
      charset,
      value,
      onChange,
      placeholder,
      lineAlignments,
      lineWrapEnabled,
      onLineAlignmentChange,
      onLineWrapChange,
      boardWidth,
      boardLines,
      deviceType,
      code62Glyph,
      onSyncFromBoard,
      syncFromBoardPending,
    },
    ref,
  ) {
    const t = useTranslations("templateEditor");
    const { data: templateVars, isLoading } = useQuery({
      queryKey: ["template-variables"],
      queryFn: api.getTemplateVariables,
    });

    const labels = useMemo<Partial<TemplateEditorLabels>>(
      () => ({
        lineCount: (used, max) => t("lineCount", { used, max }),
        overLineLimit: (max) => t("overLineLimit", { max }),
        currentLine: (line) => t("currentLine", { line }),
        alignment: t("alignment"),
        alignLeft: t("alignLeft"),
        alignCenter: t("alignCenter"),
        alignRight: t("alignRight"),
        editorAriaLabel: t("editorAriaLabel"),
        charsetWarningsSummary: (count) => t("charsetWarningsSummary", { count }),
      }),
      [t],
    );

    const toolbarLabels = useMemo<Partial<TemplateEditorToolbarLabels>>(() => {
      const out: Partial<TemplateEditorToolbarLabels> = {};
      for (const key of TOOLBAR_STRING_KEYS) out[key] = t(key);
      const drawColors = t.raw("drawColors");
      if (drawColors && typeof drawColors === "object") {
        out.drawColors = drawColors as TemplateEditorToolbarLabels["drawColors"];
      }
      return out;
    }, [t]);

    const colorPickerLabels = useMemo<Partial<ColorPickerLabels>>(() => {
      const colorNames = t.raw("drawColors");
      return {
        ...(colorNames && typeof colorNames === "object"
          ? { colorNames: colorNames as ColorPickerLabels["colorNames"] }
          : {}),
        colorPickerAriaLabel: t("colorPickerAriaLabel"),
        colorOptionLabel: (name) => t("colorOptionLabel", { color: name }),
        heartCharacterAriaLabel: t("heartCharacterAriaLabel"),
        heartLabel: t("heartLabel"),
        insertHeartTooltip: t("insertHeartTooltip"),
        degreeCharacterAriaLabel: t("degreeCharacterAriaLabel"),
        degreeLabel: t("degreeLabel"),
        insertDegreeTooltip: t("insertDegreeTooltip"),
        textColors: t("textColors"),
        textColorOptionLabel: (name) => t("textColorOptionLabel", { color: name }),
        unlitTextColor: t("unlitTextColor"),
        blockColors: t("blockColors"),
        blockColorOptionLabel: (name) => t("blockColorOptionLabel", { color: name }),
        icons: t("icons"),
        iconOptionLabel: (icon) => t("iconOptionLabel", { icon }),
      };
    }, [t]);

    const hasHomeAssistant = Boolean(templateVars?.variables?.home_assistant);

    return (
      <TemplateEditor
        ref={ref}
        charset={charset}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        showAlignmentControls
        showToolbar
        lineAlignments={lineAlignments}
        lineWrapEnabled={lineWrapEnabled}
        onLineAlignmentChange={onLineAlignmentChange}
        onLineWrapChange={onLineWrapChange}
        boardWidth={boardWidth}
        boardLines={boardLines}
        deviceType={deviceType}
        code62Glyph={code62Glyph}
        onSyncFromBoard={onSyncFromBoard}
        syncFromBoardPending={syncFromBoardPending}
        labels={labels}
        toolbarProps={{
          templateVariables: templateVars as ToolbarTemplateVariables | undefined,
          isLoadingVariables: isLoading,
          renderVariablePicker: ({ onInsert }) => (
            <Suspense fallback={null}>
              <VariablePickerContent onInsert={onInsert} />
            </Suspense>
          ),
          entityPickerSlot: hasHomeAssistant
            ? ({ open, onClose, onSelect }) => (
                <HomeAssistantEntityPicker open={open} onClose={onClose} onSelect={onSelect} />
              )
            : undefined,
          labels: toolbarLabels,
          colorPickerLabels,
        }}
      />
    );
  },
);

"use client";

import {
  AVAILABLE_COLORS,
  Box,
  Button,
  COLOR_SPAN_MARK,
  ColorPickerContent,
  DEFAULT_TEMPLATE_EDITOR_TOOLBAR_LABELS,
  DrawCharPickerContent,
  EditorTool,
  FormattingPickerContent,
  insertTemplateContent,
  resolveCharacterSet,
  SegmentedControl,
  SegmentedControlItem,
  Switch,
  type TemplateEditorToolbarProps,
  ToolbarDropdown,
  VariablePickerContent,
} from "@fiestaboard/ui";
import {
  Check,
  ClipboardPaste,
  Copy,
  Download,
  Ellipsis,
  Eraser,
  Paintbrush,
  Palette,
  Pencil,
  Redo2,
  Scissors,
  Sigma,
  Sparkles,
  Type,
  Undo2,
  Variable,
} from "lucide-react";
import { type ReactNode, Suspense, useEffect, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/utils";

function subscribeViewport(callback: () => void) {
  const viewport = window.visualViewport;
  viewport?.addEventListener("resize", callback);
  viewport?.addEventListener("scroll", callback);
  return () => {
    viewport?.removeEventListener("resize", callback);
    viewport?.removeEventListener("scroll", callback);
  };
}
function keyboardInset() {
  const viewport = window.visualViewport;
  return viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
}

/** The kit touch bar fixes every picker to a sheet. At >=640px the web
 * design instead pairs the same kit tools with anchored kit dropdowns. */
export function EditorTabletTools(props: TemplateEditorToolbarProps) {
  const { editor, templateVariables, charset, drawMode, onDrawModeToggle, onDrawBrushChange } = props;
  const labels = { ...DEFAULT_TEMPLATE_EDITOR_TOOLBAR_LABELS, ...props.labels };
  const set = charset ? resolveCharacterSet(charset) : null;
  const led = (props.capabilities ?? (set?.colorSpans || set?.font ? "led-text" : "split-flap")) === "led-text";
  const [entityOpen, setEntityOpen] = useState(false);
  const [history, setHistory] = useState({ undo: false, redo: false, selection: false });
  const bottom = useSyncExternalStore(subscribeViewport, keyboardInset, () => 0);
  useEffect(() => {
    if (!editor) return;
    const update = () =>
      setHistory({
        undo: editor.can().undo(),
        redo: editor.can().redo(),
        selection: editor.state.selection.from !== editor.state.selection.to,
      });
    update();
    editor.on("update", update);
    editor.on("selectionUpdate", update);
    return () => {
      editor.off("update", update);
      editor.off("selectionUpdate", update);
    };
  }, [editor]);
  const insert = (value: string) => {
    if (editor) insertTemplateContent(editor, value);
  };
  const undo = () => {
    if (history.undo) editor?.chain().focus().undo().run();
  };
  const redo = () => {
    if (history.redo) editor?.chain().focus().redo().run();
  };
  const dropdown = (label: string, icon: ReactNode, body: (close: () => void) => ReactNode, disabled = false) => (
    <ToolbarDropdown label={label} icon={icon} size="touch" presentation="popover" disabled={disabled}>
      {body}
    </ToolbarDropdown>
  );
  const colors = (kind: "colors" | "text" | "icon") =>
    dropdown(
      kind === "icon" ? labels.icon : kind === "text" ? labels.textColor : labels.colors,
      kind === "icon" ? <Sparkles /> : <Palette />,
      (close) => (
        <ColorPickerContent
          size="touch"
          deviceType={props.deviceType}
          code62Glyph={props.code62Glyph}
          charset={charset}
          labels={props.colorPickerLabels}
          sections={kind === "icon" ? ["icons"] : kind === "text" ? ["tiles", "textColors", "blockColors"] : undefined}
          onInsert={(value) => {
            insert(value);
            close();
          }}
          onInsertTextColor={
            set?.colorSpans
              ? (color) => {
                  editor?.chain().focus().toggleMark(COLOR_SPAN_MARK, { color, background: null }).run();
                  close();
                }
              : undefined
          }
          onInsertBlockColor={
            set?.blockSpans
              ? ({ color, background }) => {
                  editor?.chain().focus().toggleMark(COLOR_SPAN_MARK, { color, background }).run();
                  close();
                }
              : undefined
          }
          onInsertIcon={(icon) => {
            if (editor) insertTemplateContent(editor, `{{icon:${icon}}}`, { extendedMarkup: true });
            close();
          }}
        />
      ),
      kind === "icon"
        ? !set?.icons?.length
        : !(Object.keys(templateVariables?.colors ?? {}).length || set?.colorSpans || set?.blockSpans),
    );
  const clipboard = async (operation: "cut" | "copy" | "paste") => {
    if (!editor) return;
    editor.view.focus();
    try {
      if (operation === "paste") {
        const value = await navigator.clipboard.readText();
        if (value) insert(value);
      } else {
        const { from, to } = editor.state.selection;
        await navigator.clipboard.writeText(editor.state.doc.textBetween(from, to, "\n"));
        if (operation === "cut") editor.chain().focus().deleteSelection().run();
      }
    } catch {
      if (operation !== "paste") document.execCommand(operation);
    }
  };
  const historyTools = (
    <>
      <EditorTool icon={<Undo2 />} label={labels.undoAriaLabel} disabled={!history.undo} onClick={undo} />
      <EditorTool icon={<Redo2 />} label={labels.redoAriaLabel} disabled={!history.redo} onClick={redo} />
    </>
  );
  const entityAvailable = !!props.entityPickerSlot && !!templateVariables?.variables?.home_assistant;
  const tools = (
    <Box
      role="group"
      aria-label={labels.tools}
      data-slot="editor-toolbar"
      data-size="touch"
      data-capabilities={led ? "led-text" : "split-flap"}
      data-layout={props.layout ?? "docked"}
      className={cn(
        "flex w-full items-center border-t border-border bg-card px-1 py-1 [&_[data-testid=toolbar-dropdown-panel]]:top-auto [&_[data-testid=toolbar-dropdown-panel]]:bottom-full [&_[data-testid=toolbar-dropdown-panel]]:mb-1 [&_[data-testid=toolbar-dropdown-panel]]:max-h-[60dvh] [&_[data-testid=toolbar-dropdown-panel]]:overflow-y-auto",
        props.layout !== "row" && "fixed inset-x-0 z-[var(--z-mobile-menu)]",
        props.className,
      )}
      style={props.layout !== "row" ? { bottom } : undefined}
    >
      {drawMode ? (
        <>
          {dropdown(labels.brush, <Paintbrush />, (close) => (
            <Box className="flex flex-col gap-3">
              {(!set || set.tiles) && (
                <Box className="grid grid-cols-4 gap-2">
                  {AVAILABLE_COLORS.map((color) => (
                    <Button
                      key={color}
                      size="touch"
                      variant="outline"
                      onClick={() => {
                        onDrawBrushChange?.({ kind: "color", color });
                        close();
                      }}
                    >
                      {labels.drawColors[color]}
                    </Button>
                  ))}
                </Box>
              )}
              <Button
                size="touch"
                variant="outline"
                onClick={() => {
                  onDrawBrushChange?.({ kind: "eraser" });
                  close();
                }}
              >
                <Eraser />
                {labels.drawEraser}
              </Button>
              <DrawCharPickerContent
                size="touch"
                current={props.drawBrush ?? { kind: "color", color: "red" }}
                deviceType={props.deviceType}
                code62Glyph={props.code62Glyph}
                charset={charset}
                labels={props.drawCharPickerLabels}
                onSelect={(brush) => {
                  onDrawBrushChange?.(brush);
                  close();
                }}
              />
            </Box>
          ))}
          {historyTools}
          <EditorTool icon={<Check />} label={labels.drawDone} onClick={onDrawModeToggle} />
        </>
      ) : (
        <>
          {dropdown(
            labels.variables,
            <Variable />,
            (close) => (
              <Suspense fallback={null}>
                {props.renderVariablePicker ? (
                  props.renderVariablePicker({
                    onInsert: (value) => {
                      insert(value);
                      close();
                    },
                  })
                ) : (
                  <VariablePickerContent
                    templateVariables={templateVariables}
                    isLoadingVariables={props.isLoadingVariables}
                    pluginManifests={props.pluginManifests}
                    isLoadingManifests={props.isLoadingManifests}
                    pluginDisplayData={props.pluginDisplayData}
                    resolveIcon={props.resolveIcon}
                    labels={props.variablePickerLabels}
                    onInsert={(value) => {
                      insert(value);
                      close();
                    }}
                  />
                )}
              </Suspense>
            ),
            !Object.keys(templateVariables?.variables ?? {}).length,
          )}
          {led ? (
            <>
              {colors("text")}
              {colors("icon")}
              {dropdown(labels.size, <Type />, (close) => props.renderSizePicker?.({ close }), !props.renderSizePicker)}
            </>
          ) : (
            <>
              {colors("colors")}
              {dropdown(labels.formatting, <Type />, (close) => (
                <Box className="flex flex-col gap-3">
                  {templateVariables?.formatting && (
                    <FormattingPickerContent
                      formatting={templateVariables.formatting}
                      labels={props.formattingPickerLabels}
                      onInsert={(value) => {
                        insert(value);
                        close();
                      }}
                    />
                  )}
                  <SegmentedControl
                    size="touch"
                    aria-label={labels.align}
                    value={props.currentAlignment ?? "left"}
                    onValueChange={(value) => props.onAlignmentChange?.(value as "left" | "center" | "right")}
                  >
                    <SegmentedControlItem value="left">{labels.alignLeftShort}</SegmentedControlItem>
                    <SegmentedControlItem value="center">{labels.alignCenterShort}</SegmentedControlItem>
                    <SegmentedControlItem value="right">{labels.alignRightShort}</SegmentedControlItem>
                  </SegmentedControl>
                </Box>
              ))}
            </>
          )}
          <EditorTool
            icon={<Sigma />}
            label={labels.formula}
            onClick={() =>
              editor
                ?.chain()
                .focus()
                .insertContent({ type: "formula", attrs: { expression: "", autoOpen: true } })
                .run()
            }
          />
          {!led && historyTools}
          {dropdown(labels.more, <Ellipsis />, (close) => (
            <Box className="flex flex-col gap-3">
              {led && historyTools}
              <Box role="group" aria-label={labels.clipboard} className="flex gap-2">
                <Button variant="outline" size="touch" disabled={!history.selection} onClick={() => clipboard("cut")}>
                  <Scissors />
                  {labels.cutAriaLabel}
                </Button>
                <Button variant="outline" size="touch" disabled={!history.selection} onClick={() => clipboard("copy")}>
                  <Copy />
                  {labels.copyAriaLabel}
                </Button>
                <Button variant="outline" size="touch" disabled={!editor} onClick={() => clipboard("paste")}>
                  <ClipboardPaste />
                  {labels.pasteAriaLabel}
                </Button>
              </Box>
              {onDrawModeToggle && (
                <Button
                  variant="outline"
                  size="touch"
                  onClick={() => {
                    close();
                    onDrawModeToggle();
                  }}
                >
                  <Pencil />
                  {labels.drawMode}
                </Button>
              )}
              {props.onSyncFromBoard && (
                <Button
                  variant="outline"
                  size="touch"
                  loading={props.syncFromBoardPending}
                  onClick={props.onSyncFromBoard}
                >
                  <Download />
                  {labels.syncFromBoard}
                </Button>
              )}
              {entityAvailable && (
                <Button
                  variant="outline"
                  size="touch"
                  onClick={() => {
                    close();
                    setEntityOpen(true);
                  }}
                >
                  {labels.homeAssistantEntities}
                </Button>
              )}
              <label className="flex min-h-12 items-center justify-between gap-3">
                {labels.wrapLine}
                <Switch
                  size="touch"
                  aria-label={labels.wrapLine}
                  checked={props.currentWrapEnabled ?? false}
                  disabled={!props.onWrapToggle}
                  onCheckedChange={() => props.onWrapToggle?.()}
                />
              </label>
              {props.moreContent}
            </Box>
          ))}
        </>
      )}
      {props.trailing}
    </Box>
  );
  return (
    <>
      {typeof document !== "undefined" ? createPortal(tools, props.container ?? document.body) : tools}
      {entityAvailable &&
        props.entityPickerSlot?.({
          open: entityOpen,
          onClose: () => setEntityOpen(false),
          onSelect: (value) => requestAnimationFrame(() => insert(value)),
        })}
    </>
  );
}

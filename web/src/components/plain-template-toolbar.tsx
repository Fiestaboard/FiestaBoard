"use client";

import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  EditorTool,
  Flex,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  Stack,
  Text,
  ToolbarDropdown,
} from "@fiestaboard/ui";
import { Ellipsis, Palette, Redo2, Sigma, Type, Undo2, Variable } from "lucide-react";
import { lazy, type ReactElement, type ReactNode, Suspense, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { EditorAnchoredTool } from "@/components/editor-tablet-tools";
import { useEditorToolbarPortal } from "@/hooks/use-editor-toolbar-portal";
import { useMainContentLeft } from "@/hooks/use-main-content-left";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useVisualViewportBottom } from "@/hooks/use-visual-viewport-bottom";
import { useTranslations } from "@/i18n/translations";
import { cn } from "@/lib/utils";

const VariablePickerContent = lazy(() =>
  import("@/components/tiptap-template-editor/components/VariablePickerContent").then((m) => ({
    default: m.VariablePickerContent,
  })),
);
const FormulaEditorPanel = lazy(() =>
  import("@/components/tiptap-template-editor/components/FormulaEditorPanel").then((m) => ({
    default: m.FormulaEditorPanel,
  })),
);

/** Same host variable catalog and kit overlays for plain templates and starters. */
export function PlainTemplateVariablePicker({
  trigger,
  onInsert,
}: {
  trigger: ReactElement;
  onInsert: (text: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const inserted = useRef(false);
  const onOpenChange = (next: boolean) => {
    if (next) inserted.current = false;
    setOpen(next);
  };
  // Successful insertion owns the caret; ordinary dismissal returns to the opener.
  const finalFocus = () => (inserted.current ? false : triggerRef.current);
  const sheet = useMediaQuery("(max-width: 639px)");
  const touch = useMediaQuery("(max-width: 767px), (pointer: coarse)");
  const t = useTranslations("templateEditor");
  const content = (
    <Suspense fallback={null}>
      <VariablePickerContent
        autoFocusSearch={!touch}
        onInsert={(text) => {
          inserted.current = true;
          setOpen(false);
          onInsert(text);
        }}
      />
    </Suspense>
  );
  if (sheet)
    return (
      <Sheet open={open} onOpenChange={onOpenChange} modal={false}>
        <SheetTrigger asChild ref={triggerRef}>
          {trigger}
        </SheetTrigger>
        <SheetContent side="bottom" grabber scrim={false} detents={["half", "full"]} finalFocus={finalFocus}>
          <SheetHeader>
            <SheetTitle>{t("variables")}</SheetTitle>
          </SheetHeader>
          {content}
        </SheetContent>
      </Sheet>
    );
  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild ref={triggerRef}>
        {trigger}
      </PopoverTrigger>
      <PopoverContent label={t("variables")} finalFocus={finalFocus} className="max-h-[60dvh] overflow-y-auto p-3">
        {content}
      </PopoverContent>
    </Popover>
  );
}

/** H3 keeps template syntax tools while display-dependent tools explain why they disable. */
export function PlainTemplateToolbar({
  onInsert,
  moreContent,
  canUndo = false,
  canRedo = false,
  onUndo,
  onRedo,
}: {
  onInsert: (text: string) => void;
  moreContent: ReactNode;
  canUndo?: boolean;
  canRedo?: boolean;
  onUndo?: () => void;
  onRedo?: () => void;
}) {
  const t = useTranslations("templateEditor");
  const tTouch = useTranslations("editorTouch");
  const touch = useMediaQuery("(max-width: 767px), (pointer: coarse)");
  const sheets = useMediaQuery("(max-width: 639px)");
  const portal = useEditorToolbarPortal(touch, tTouch("editorTools"));
  const bottom = useVisualViewportBottom();
  const left = useMainContentLeft(touch);
  const reasonId = useId();
  const [formulaOpen, setFormulaOpen] = useState(false);
  const formulaTriggerRef = useRef<HTMLButtonElement>(null);
  const insertedFormula = useRef(false);
  const openFormula = () => {
    insertedFormula.current = false;
    setFormulaOpen(true);
  };
  const tool = (label: string, icon: ReactNode, disabled = false) =>
    touch ? (
      <EditorTool label={label} icon={icon} disabled={disabled} aria-describedby={disabled ? reasonId : undefined} />
    ) : (
      <Button size="sm" variant="ghost" disabled={disabled} aria-describedby={disabled ? reasonId : undefined}>
        {icon}
        {label}
      </Button>
    );
  const toolbar = (
    <Flex
      role="group"
      aria-label={tTouch("editorTools")}
      align="center"
      gap={touch ? "0" : "1"}
      data-slot="editor-toolbar"
      data-size={touch ? "touch" : "default"}
      data-capabilities="plain-text"
      className={cn(
        "w-full border-border bg-card p-1",
        touch ? "fixed inset-x-0 z-[var(--z-mobile-menu)] border-t" : "flex-wrap rounded-lg border",
      )}
      style={touch ? { bottom, left, width: "auto" } : undefined}
    >
      <PlainTemplateVariablePicker trigger={tool(t("variables"), <Variable />)} onInsert={onInsert} />
      {tool(t("colors"), <Palette />, true)}
      {tool(t("formatting"), <Type />, true)}
      {touch ? (
        <EditorTool ref={formulaTriggerRef} label={t("formula")} icon={<Sigma />} onClick={openFormula} />
      ) : (
        <Button ref={formulaTriggerRef} size="sm" variant="ghost" onClick={openFormula}>
          <Sigma />
          {t("formula")}
        </Button>
      )}
      {touch ? (
        <>
          <EditorTool label={t("undoAriaLabel")} icon={<Undo2 />} disabled={!canUndo} onClick={onUndo} />
          <EditorTool label={t("redoAriaLabel")} icon={<Redo2 />} disabled={!canRedo} onClick={onRedo} />
        </>
      ) : (
        <>
          <Button size="sm" variant="ghost" disabled={!canUndo} onClick={onUndo}>
            <Undo2 />
            {t("undoAriaLabel")}
          </Button>
          <Button size="sm" variant="ghost" disabled={!canRedo} onClick={onRedo}>
            <Redo2 />
            {t("redoAriaLabel")}
          </Button>
        </>
      )}
      {sheets ? (
        <ToolbarDropdown label={t("more")} icon={<Ellipsis />} size={touch ? "touch" : "default"} presentation="sheet">
          {moreContent}
        </ToolbarDropdown>
      ) : (
        <EditorAnchoredTool label={t("more")} icon={<Ellipsis />}>
          {() => moreContent}
        </EditorAnchoredTool>
      )}
      <Text id={reasonId} size="xs" tone="muted" className={touch ? "sr-only" : undefined}>
        {tTouch("displayToolsUnavailable")}
      </Text>
    </Flex>
  );
  return (
    <>
      {touch ? portal && createPortal(toolbar, portal) : toolbar}
      <Dialog open={formulaOpen} onOpenChange={setFormulaOpen}>
        <DialogContent
          finalFocus={() => (insertedFormula.current ? false : formulaTriggerRef.current)}
          className="max-h-[90dvh] overflow-y-auto"
        >
          <DialogHeader>
            <DialogTitle>{t("formula")}</DialogTitle>
          </DialogHeader>
          <Stack gap="2">
            <Suspense fallback={<Box />}>
              <FormulaEditorPanel
                mode="create"
                onConfirm={(expression) => {
                  insertedFormula.current = true;
                  setFormulaOpen(false);
                  onInsert(`{{= ${expression} }}`);
                }}
              />
            </Suspense>
          </Stack>
        </DialogContent>
      </Dialog>
    </>
  );
}

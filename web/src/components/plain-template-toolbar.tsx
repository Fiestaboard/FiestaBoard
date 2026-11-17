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
import { Ellipsis, Palette, Sigma, Type, Variable } from "lucide-react";
import { lazy, type ReactElement, type ReactNode, Suspense, useId, useState } from "react";
import { createPortal } from "react-dom";

import { useEditorToolbarPortal } from "@/hooks/use-editor-toolbar-portal";
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
  const sheet = useMediaQuery("(max-width: 639px)");
  const t = useTranslations("templateEditor");
  const content = (
    <Suspense fallback={null}>
      <VariablePickerContent
        onInsert={(text) => {
          setOpen(false);
          onInsert(text);
        }}
      />
    </Suspense>
  );
  if (sheet)
    return (
      <Sheet open={open} onOpenChange={setOpen} modal={false}>
        <SheetTrigger asChild>{trigger}</SheetTrigger>
        <SheetContent side="bottom" grabber scrim={false} detents={["half", "full"]} finalFocus={false}>
          <SheetHeader>
            <SheetTitle>{t("variables")}</SheetTitle>
          </SheetHeader>
          {content}
        </SheetContent>
      </Sheet>
    );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent label={t("variables")} finalFocus={false} className="max-h-[60dvh] overflow-y-auto p-3">
        {content}
      </PopoverContent>
    </Popover>
  );
}

/** H3 keeps template syntax tools while display-dependent tools explain why they disable. */
export function PlainTemplateToolbar({
  onInsert,
  moreContent,
}: {
  onInsert: (text: string) => void;
  moreContent: ReactNode;
}) {
  const t = useTranslations("templateEditor");
  const tTouch = useTranslations("editorTouch");
  const touch = useMediaQuery("(max-width: 767px), (pointer: coarse)");
  const sheets = useMediaQuery("(max-width: 639px)");
  const portal = useEditorToolbarPortal(touch, tTouch("editorTools"));
  const bottom = useVisualViewportBottom();
  const reasonId = useId();
  const [formulaOpen, setFormulaOpen] = useState(false);
  const tool = (label: string, icon: ReactNode, disabled = false, onClick?: () => void) =>
    touch ? (
      <EditorTool
        label={label}
        icon={icon}
        disabled={disabled}
        aria-describedby={disabled ? reasonId : undefined}
        onClick={onClick}
      />
    ) : (
      <Button
        size="sm"
        variant="ghost"
        disabled={disabled}
        aria-describedby={disabled ? reasonId : undefined}
        onClick={onClick}
      >
        {icon}
        {label}
      </Button>
    );
  const toolbar = (
    <Flex
      role="group"
      aria-label={tTouch("editorTools")}
      align="center"
      gap="1"
      data-slot="editor-toolbar"
      data-size={touch ? "touch" : "default"}
      data-capabilities="plain-text"
      className={cn(
        "w-full border-border bg-card p-1",
        touch ? "fixed inset-x-0 z-[var(--z-mobile-menu)] border-t" : "flex-wrap rounded-lg border",
      )}
      style={touch ? { bottom } : undefined}
    >
      <PlainTemplateVariablePicker trigger={tool(t("variables"), <Variable />)} onInsert={onInsert} />
      {tool(t("colors"), <Palette />, true)}
      {tool(t("formatting"), <Type />, true)}
      {tool(t("formula"), <Sigma />, false, () => setFormulaOpen(true))}
      <ToolbarDropdown
        label={t("more")}
        icon={<Ellipsis />}
        size={touch ? "touch" : "default"}
        presentation={sheets ? "sheet" : "popover"}
      >
        {moreContent}
      </ToolbarDropdown>
      <Text id={reasonId} size="xs" tone="muted" className={touch ? "sr-only" : undefined}>
        {tTouch("displayToolsUnavailable")}
      </Text>
    </Flex>
  );
  return (
    <>
      {touch ? portal && createPortal(toolbar, portal) : toolbar}
      <Dialog open={formulaOpen} onOpenChange={setFormulaOpen}>
        <DialogContent finalFocus={false} className="max-h-[90dvh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t("formula")}</DialogTitle>
          </DialogHeader>
          <Stack gap="2">
            <Suspense fallback={<Box />}>
              <FormulaEditorPanel
                mode="create"
                onConfirm={(expression) => {
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

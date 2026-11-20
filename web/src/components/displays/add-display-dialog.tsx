"use client";

import {
  Button,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  type BoardConfig,
  type BoardSetupHandle,
  type ExistingDisplayIntent,
  StepBoardSetup,
} from "@/components/wizard/step-board-setup";
import { StepChooseOutput } from "@/components/wizard/step-choose-output";
import {
  StepOutputPlugin,
  type WizardCreatedBoard,
  type WizardOutputChoice,
} from "@/components/wizard/step-output-plugin";
import { type PanelSetupHandle, StepPanelSetup } from "@/components/wizard/step-panel-setup";
import { useTranslations } from "@/i18n/translations";

type Step = "choose" | "setup";

/** Two steps at every width; never re-enters the first-run wizard. */
export function AddDisplayDialog({
  onCreated,
  onCancel,
  initialOutput,
}: {
  onCreated: (boardId: string) => void;
  onCancel: () => void;
  initialOutput?: WizardOutputChoice;
}) {
  const t = useTranslations("displays.add");
  const tc = useTranslations("common");
  const [step, setStep] = useState<Step>(initialOutput ? "setup" : "choose");
  const [chosen, setChosen] = useState<WizardOutputChoice | null>(initialOutput ?? null);
  const [canNext, setCanNext] = useState(false);
  const [busy, setBusy] = useState(false);
  // An already connected board (BB-C-16): the primary action keeps or updates it, never "Add display".
  const [existing, setExisting] = useState<ExistingDisplayIntent | null>(null);
  const [config, setConfig] = useState<BoardConfig>({
    output_config: { api_mode: "local" },
    connectionVerified: false,
    device_type: "flagship",
    board_color: "black",
    code62_glyph: "degree",
  });
  const boardStep = useRef<BoardSetupHandle>(null);
  const panelStep = useRef<PanelSetupHandle>(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const complete = (board: WizardCreatedBoard) => {
    if (!alive.current) return;
    toast.success(t("added", { name: board.name }));
    onCreated(board.boardId);
  };
  const add = async () => {
    const vestaboard = chosen?.id === "vestaboard";
    const kept = vestaboard ? existing : null;
    const board = vestaboard ? await boardStep.current?.save() : await panelStep.current?.save();
    if (!board || !alive.current) return;
    if (!kept) return complete(board);
    if (kept.choice === "keep") toast.info(t("kept", { name: board.name }));
    else toast.success(t("updated", { name: board.name }));
    onCreated(board.boardId);
  };
  const primaryLabel =
    chosen?.id === "vestaboard" && existing
      ? t(existing.choice === "keep" ? "goTo" : "updateExisting", { name: existing.name })
      : t("confirm");
  return (
    <DialogContent
      className="max-h-[90dvh] overflow-y-auto bg-popover sm:rounded-[var(--radius-card)] sm:max-w-[560px] max-sm:inset-x-0 max-sm:bottom-0 max-sm:top-auto max-sm:max-h-[92dvh] max-sm:w-screen max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-t-[var(--radius-chrome-mobile)] max-sm:rounded-b-none max-sm:p-5 max-sm:pb-4"
      data-testid="add-display-dialog"
    >
      <DialogHeader className={step === "choose" ? "text-left" : undefined}>
        <DialogTitle>{t("title")}</DialogTitle>
        <DialogDescription>{t(step === "choose" ? "chooseDescription" : "setupDescription")}</DialogDescription>
      </DialogHeader>
      <Text size="xs" tone="muted">
        {t("step", { current: step === "choose" ? 1 : 2 })}
      </Text>
      <Stack gap="4">
        {step === "choose" && (
          <StepChooseOutput
            columns="1"
            value={chosen?.id ?? null}
            onChange={(output) => setChosen({ id: output.id, name: output.name })}
            onValidChange={setCanNext}
          />
        )}
        {step === "setup" &&
          chosen &&
          (chosen.id === "vestaboard" ? (
            <StepBoardSetup
              ref={boardStep}
              replacePlaceholder={false}
              requireTest
              config={config}
              onConfigChange={setConfig}
              onValidChange={setCanNext}
              onExistingChange={setExisting}
              isLoading={busy}
              setIsLoading={setBusy}
            />
          ) : chosen.id === "fiestapanel" ? (
            <StepPanelSetup
              ref={panelStep}
              hideCreate
              created={null}
              onCreated={() => undefined}
              onValidChange={setCanNext}
              setIsLoading={setBusy}
              replacePlaceholder={false}
            />
          ) : (
            <StepOutputPlugin
              key={chosen.id}
              output={chosen}
              created={null}
              onCreated={complete}
              onValidChange={setCanNext}
              setIsLoading={setBusy}
              replacePlaceholder={false}
              createLabel={t("confirm")}
            />
          ))}
      </Stack>
      <DialogFooter className="gap-2 [&_button]:max-sm:min-h-11 [&_button]:max-sm:w-full">
        {step === "choose" ? (
          <>
            <Button variant="outline" onClick={onCancel}>
              {tc("cancel")}
            </Button>
            <Button
              disabled={!canNext || !chosen}
              onClick={() => {
                setCanNext(false);
                setStep("setup");
              }}
            >
              {tc("next")}
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setCanNext(false);
                setExisting(null);
                setStep("choose");
              }}
            >
              {tc("back")}
            </Button>
            {(chosen?.id === "vestaboard" || chosen?.id === "fiestapanel") && (
              <Button disabled={!canNext || busy} onClick={() => void add()}>
                {primaryLabel}
              </Button>
            )}
          </>
        )}
      </DialogFooter>
    </DialogContent>
  );
}

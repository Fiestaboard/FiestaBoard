"use client";

/**
 * Displays → Add a display (plan D21): the setup wizard's output-first flow
 * (plan D18) in a dialog.
 *
 * 1. Choose: search all installed, bundled and marketplace display plugins
 *    through the same catalog as onboarding.
 * 2. Set up, by output: a Vestaboard picks its shape and is added at once; a
 *    FiestaPanel takes a name and a TV size (`StepPanelSetup`); an output
 *    plugin installs (seed offline, else the registry) and shows its own
 *    settings screen with Find / Test on draft settings (`StepOutputPlugin`).
 * 3. The new display's page opens.
 *
 * Opened from a Displays → Marketplace card (`initialOutput`), it starts at
 * step 2 for that display; Back leads to step 1.
 *
 * Unlike the wizard, adding a display never removes the untouched
 * placeholder board: every board the user has stays where it is.
 */
import {
  Box,
  Button,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Stack,
} from "@fiestaboard/ui";
import { ChevronLeft } from "lucide-react";
import { useState } from "react";

import { useDisplayBoards, VestaboardTypeButtons } from "@/components/settings/display-settings";
import { StepChooseOutput } from "@/components/wizard/step-choose-output";
import { StepOutputPlugin, type WizardOutputChoice } from "@/components/wizard/step-output-plugin";
import { StepPanelSetup } from "@/components/wizard/step-panel-setup";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";

type Step = { kind: "choose" } | { kind: "setup"; output: WizardOutputChoice };

const ignore = () => undefined;

/** The dialog's content; render it inside a `<Dialog>`. `onCreated` gets the new display's board id. */
export function AddDisplayDialog({
  onCreated,
  onCancel,
  initialOutput,
}: {
  onCreated: (boardId: string) => void;
  onCancel: () => void;
  /** Start at this display's setup (a marketplace card's "Add display"). */
  initialOutput?: WizardOutputChoice;
}) {
  const t = useTranslations("displays.add");
  const tc = useTranslations("common");
  const [step, setStep] = useState<Step>(() =>
    initialOutput ? { kind: "setup", output: initialOutput } : { kind: "choose" },
  );
  const [chosen, setChosen] = useState<WizardOutputChoice | null>(initialOutput ?? null);
  const [canNext, setCanNext] = useState(false);
  const displays = useDisplayBoards();
  const [busy, setBusy] = useState(false);

  const addVestaboard = async (deviceType: DeviceType) => {
    const id = await displays.addVestaboard(deviceType);
    if (id) onCreated(id);
  };

  const title =
    step.kind === "setup"
      ? step.output.id === "vestaboard"
        ? t("vestaboardTitle")
        : step.output.id === "fiestapanel"
          ? t("panelTitle")
          : t("outputTitle", { name: step.output.name })
      : t("title");
  const description =
    step.kind === "setup"
      ? step.output.id === "vestaboard"
        ? t("vestaboardDescription")
        : t("setupDescription")
      : t("chooseDescription");

  return (
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg" data-testid="add-display-dialog">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>

      {/* Not a <form>: an output action's input dialog is a form of its own,
          and React bubbles its submit through the portal into any form
          around it (the wizard's step avoids one for the same reason). */}
      <Box className="py-2">
        {step.kind === "choose" && (
          <Stack gap="4">
            <StepChooseOutput
              value={chosen?.id ?? null}
              onChange={(output) => setChosen({ id: output.id, name: output.name })}
              onValidChange={setCanNext}
            />
          </Stack>
        )}

        {step.kind === "setup" &&
          (step.output.id === "vestaboard" ? (
            <VestaboardTypeButtons onAdd={(type) => void addVestaboard(type)} disabled={displays.adding} />
          ) : step.output.id === "fiestapanel" ? (
            <StepPanelSetup
              created={null}
              onCreated={(board) => onCreated(board.boardId)}
              onValidChange={ignore}
              setIsLoading={setBusy}
              replacePlaceholder={false}
            />
          ) : (
            <StepOutputPlugin
              key={step.output.id}
              output={step.output}
              created={null}
              onCreated={(board) => onCreated(board.boardId)}
              onValidChange={ignore}
              setIsLoading={setBusy}
              replacePlaceholder={false}
            />
          ))}
      </Box>

      <DialogFooter>
        {step.kind === "choose" ? (
          <>
            <Button type="button" variant="ghost" onClick={onCancel}>
              {tc("cancel")}
            </Button>
            <Button
              type="button"
              disabled={!canNext || !chosen}
              onClick={() => chosen && setStep({ kind: "setup", output: chosen })}
            >
              {tc("next")}
            </Button>
          </>
        ) : (
          <Button type="button" variant="ghost" disabled={busy} onClick={() => setStep({ kind: "choose" })}>
            <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
            {tc("back")}
          </Button>
        )}
      </DialogFooter>
    </DialogContent>
  );
}

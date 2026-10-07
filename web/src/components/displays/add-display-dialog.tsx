"use client";

/**
 * Displays → Add a display (plan D21): the setup wizard's output-first flow
 * (plan D18) in a dialog.
 *
 * 1. Choose: every output `GET /outputs/available` offers that is installed
 *    or bundled with this image (`StepChooseOutput`), plus "Find more
 *    displays" — the marketplace's output plugins (`GET /plugins/registry`,
 *    `plugin_type: "output"`).
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
  ActionCard,
  Alert,
  AlertDescription,
  Box,
  Button,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Grid,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, Search } from "lucide-react";
import { useState } from "react";

import { useDisplayBoards, VestaboardTypeButtons } from "@/components/settings/display-settings";
import { OutputIcon } from "@/components/settings/output-boards";
import { StepChooseOutput } from "@/components/wizard/step-choose-output";
import { StepOutputPlugin, type WizardOutputChoice } from "@/components/wizard/step-output-plugin";
import { StepPanelSetup } from "@/components/wizard/step-panel-setup";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { api } from "@/lib/api";

type Step =
  { kind: "choose" } | { kind: "more" } | { kind: "setup"; output: WizardOutputChoice; from: "choose" | "more" };

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
    initialOutput ? { kind: "setup", output: initialOutput, from: "choose" } : { kind: "choose" },
  );
  const [chosen, setChosen] = useState<WizardOutputChoice | null>(initialOutput ?? null);
  const [canNext, setCanNext] = useState(false);
  const displays = useDisplayBoards();

  const addVestaboard = async (deviceType: DeviceType) => {
    const id = await displays.addVestaboard(deviceType);
    if (id) onCreated(id);
  };

  const title =
    step.kind === "more"
      ? t("findMoreTitle")
      : step.kind === "setup"
        ? step.output.id === "vestaboard"
          ? t("vestaboardTitle")
          : step.output.id === "fiestapanel"
            ? t("panelTitle")
            : t("outputTitle", { name: step.output.name })
        : t("title");
  const description =
    step.kind === "more"
      ? t("findMoreDescription")
      : step.kind === "setup"
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
              // Registry outputs are "Find more displays", below.
              include={(output) => output.source !== "registry"}
            />
            <Flex>
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep({ kind: "more" })}
                data-testid="find-more-displays"
              >
                <Search className="mr-1 h-4 w-4" aria-hidden="true" />
                {t("findMore")}
              </Button>
            </Flex>
          </Stack>
        )}

        {step.kind === "more" && (
          <FindMoreDisplays onPick={(output) => setStep({ kind: "setup", output, from: "more" })} />
        )}

        {step.kind === "setup" &&
          (step.output.id === "vestaboard" ? (
            <VestaboardTypeButtons onAdd={(type) => void addVestaboard(type)} disabled={displays.adding} />
          ) : step.output.id === "fiestapanel" ? (
            <StepPanelSetup
              created={null}
              onCreated={(board) => onCreated(board.boardId)}
              onValidChange={ignore}
              setIsLoading={ignore}
              replacePlaceholder={false}
            />
          ) : (
            <StepOutputPlugin
              key={step.output.id}
              output={step.output}
              created={null}
              onCreated={(board) => onCreated(board.boardId)}
              onValidChange={ignore}
              setIsLoading={ignore}
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
              onClick={() => chosen && setStep({ kind: "setup", output: chosen, from: "choose" })}
            >
              {tc("next")}
            </Button>
          </>
        ) : (
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              setStep(step.kind === "setup" && step.from === "more" ? { kind: "more" } : { kind: "choose" })
            }
          >
            <ChevronLeft className="mr-1 h-4 w-4" aria-hidden="true" />
            {tc("back")}
          </Button>
        )}
      </DialogFooter>
    </DialogContent>
  );
}

/** The marketplace's display plugins (`plugin_type: "output"`) not installed yet. */
function FindMoreDisplays({ onPick }: { onPick: (output: WizardOutputChoice) => void }) {
  const t = useTranslations("displays.add");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: () => api.listRegistryPlugins(),
    staleTime: 5 * 60_000,
  });
  const entries = (data?.entries ?? []).filter((entry) => entry.plugin_type === "output" && !entry.installed);

  if (isLoading) {
    return (
      <Flex align="center" gap="2" role="status">
        <Spinner label={null} />
        <Text as="span" tone="muted">
          {t("findMoreLoading")}
        </Text>
      </Flex>
    );
  }
  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{t("findMoreFailed")}</AlertDescription>
      </Alert>
    );
  }
  if (entries.length === 0) {
    return (
      <Text tone="muted" data-testid="find-more-empty">
        {t("findMoreEmpty")}
      </Text>
    );
  }
  return (
    <Grid gap="2" role="list" aria-label={t("findMoreTitle")} data-testid="find-more-list">
      {entries.map((entry) => (
        <Box role="listitem" key={entry.id}>
          <ActionCard
            icon={<OutputIcon name={entry.icon} />}
            title={entry.name}
            description={entry.description}
            meta={entry.author ? t("byAuthor", { author: entry.author }) : undefined}
            onClick={() => onPick({ id: entry.id, name: entry.name })}
            data-testid={`find-more-${entry.id}`}
          />
        </Box>
      ))}
    </Grid>
  );
}

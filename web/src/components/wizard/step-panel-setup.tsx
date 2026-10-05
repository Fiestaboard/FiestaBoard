"use client";

/**
 * The setup wizard's board step for FiestaPanel (plan D18): a TV or any
 * browser. A name and the screen size are all it takes — `POST /panels`
 * creates the panel and its auto-fit board — then the step shows the address
 * to open on the TV. Everything else (aspect ratio, backdrop, calibration)
 * stays in Settings → FiestaPanel.
 */
import { Alert, AlertDescription, AlertTitle, Button, Grid, Input, Label, Stack, Text } from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { appUrl } from "@/lib/base-path";

import { removeUntouchedPlaceholder } from "./default-board";
import type { WizardCreatedBoard } from "./step-output-plugin";

const MIN_INCHES = 3;
const MAX_INCHES = 200;
const DEFAULT_INCHES = 55;

interface StepPanelSetupProps {
  created: WizardCreatedBoard | null;
  onCreated: (board: WizardCreatedBoard) => void;
  onValidChange: (valid: boolean) => void;
  setIsLoading: (loading: boolean) => void;
  /** Remove the untouched placeholder board once the panel's exists (the wizard's way; default). */
  replacePlaceholder?: boolean;
}

export function StepPanelSetup({
  created,
  onCreated,
  onValidChange,
  setIsLoading,
  replacePlaceholder = true,
}: StepPanelSetupProps) {
  const t = useTranslations("wizard.panelSetup");
  const queryClient = useQueryClient();
  const done = created?.outputId === "fiestapanel" ? created : null;
  const [name, setName] = useState(() => t("defaultName"));
  const [inches, setInches] = useState(String(DEFAULT_INCHES));
  const size = Number(inches);
  const sizeValid = Number.isFinite(size) && size >= MIN_INCHES && size <= MAX_INCHES;

  useEffect(() => {
    onValidChange(done !== null);
  }, [done, onValidChange]);

  const create = useMutation({
    mutationFn: async () => {
      setIsLoading(true);
      try {
        const panel = await api.createPanel({ name: name.trim(), screen_diagonal_inches: size });
        if (replacePlaceholder) await removeUntouchedPlaceholder(panel.board_id);
        return panel;
      } finally {
        setIsLoading(false);
      }
    },
    onSuccess: (panel) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      onCreated({
        outputId: "fiestapanel",
        boardId: panel.board_id,
        name: panel.name,
        viewerPath: panel.short_code > 0 ? `/p/${panel.short_code}` : `/panel/${panel.id}`,
      });
    },
  });

  if (done) {
    const url = done.viewerPath ? new URL(appUrl(done.viewerPath), window.location.origin).toString() : null;
    return (
      <Alert variant="success" data-testid="wizard-panel-created">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        <AlertTitle>{t("created", { name: done.name })}</AlertTitle>
        {url && (
          <AlertDescription>
            <Stack gap="1">
              <Text size="sm">{t("openOnTv")}</Text>
              <Text size="sm" className="font-mono break-all">
                {url}
              </Text>
            </Stack>
          </AlertDescription>
        )}
      </Alert>
    );
  }

  return (
    <Stack gap="4">
      <Grid gap="1.5">
        <Label htmlFor="wizard-panel-name">{t("nameLabel")}</Label>
        <Input
          id="wizard-panel-name"
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("defaultName")}
        />
      </Grid>
      <Grid gap="1.5">
        <Label htmlFor="wizard-panel-size">{t("sizeLabel")}</Label>
        <Input
          id="wizard-panel-size"
          type="number"
          inputMode="decimal"
          min={MIN_INCHES}
          max={MAX_INCHES}
          value={inches}
          onChange={(e) => setInches(e.target.value)}
          aria-describedby="wizard-panel-size-help"
          aria-invalid={!sizeValid}
        />
        <Text size="xs" tone="muted" id="wizard-panel-size-help">
          {t("sizeHelp", { min: MIN_INCHES, max: MAX_INCHES })}
        </Text>
      </Grid>
      {create.isError && (
        <Alert variant="destructive" data-testid="wizard-panel-error">
          <XCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>{t("failed")}</AlertTitle>
          <AlertDescription>{create.error.message}</AlertDescription>
        </Alert>
      )}
      <Button
        type="button"
        className="w-full"
        disabled={create.isPending || !name.trim() || !sizeValid}
        onClick={() => create.mutate()}
      >
        {create.isPending ? t("creating") : t("create")}
      </Button>
    </Stack>
  );
}

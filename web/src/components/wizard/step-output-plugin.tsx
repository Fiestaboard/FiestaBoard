"use client";

/**
 * The setup wizard's board step for an output plugin (plan D18): install it
 * (`POST /outputs/{id}/install` — from the image's seed with no network, or
 * from the registry), render its own board settings screen on draft settings
 * (`PluginBoardSettings`: discover, test and its other actions run on the
 * draft route), then name the board, pick the device model and save it with
 * `POST /outputs/{id}/boards`.
 *
 * The install's failure states are told apart, because each asks something
 * different of the user: the output plugins beta is off (409, third-party
 * outputs only: seeded first-party ones never need it — offered right
 * here), the repository could not be downloaded (503 — check the internet
 * connection), or the plugin cannot run on this FiestaBoard (400 — the
 * server's reason).
 */
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Box,
  Button,
  Flex,
  Grid,
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
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ShieldAlert, WifiOff, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DevicePreview } from "@/components/device-preview";
import { OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import { queryKeys } from "@/hooks/use-board";
import { PLUGIN_SETTINGS_QUERY_KEY } from "@/hooks/use-plugin-settings";
import { useTranslations } from "@/i18n/translations";
import type { OutputSummary } from "@/lib/api";
import { api, ApiError } from "@/lib/api";
import { MAX_BOARD_NAME_LENGTH } from "@/lib/board-dimensions";
import { isLedModel, resolveBoardModel } from "@/lib/device-preview";

import { removeUntouchedPlaceholder } from "./default-board";

/** The display chosen on the wizard's first step. */
export interface WizardOutputChoice {
  id: string;
  name: string;
}

/** The board the wizard created for a TV or an output plugin. */
export interface WizardCreatedBoard {
  outputId: string;
  boardId: string;
  name: string;
  /** A FiestaPanel's viewer address (`/p/{n}`), to open on the TV. */
  viewerPath?: string;
}

interface StepOutputPluginProps {
  output: WizardOutputChoice;
  created: WizardCreatedBoard | null;
  onCreated: (board: WizardCreatedBoard) => void;
  onValidChange: (valid: boolean) => void;
  setIsLoading: (loading: boolean) => void;
  /**
   * Remove the fresh install's untouched placeholder board once this one
   * exists (the wizard's way; default). Displays → Add a display leaves
   * every board the user has where it is.
   */
  replacePlaceholder?: boolean;
}

type InstallFailure = { kind: "beta" } | { kind: "offline"; message: string } | { kind: "refused"; message: string };

function classify(error: unknown): InstallFailure {
  if (error instanceof ApiError && error.status === 409) return { kind: "beta" };
  if (error instanceof ApiError && error.status === 503) return { kind: "offline", message: error.message };
  return { kind: "refused", message: error instanceof Error ? error.message : String(error) };
}

export function StepOutputPlugin({
  output: choice,
  created,
  onCreated,
  onValidChange,
  setIsLoading,
  replacePlaceholder = true,
}: StepOutputPluginProps) {
  const t = useTranslations("wizard.outputSetup");
  const tbs = useTranslations("boardSettingsScreen");
  const queryClient = useQueryClient();
  const done = created?.outputId === choice.id ? created : null;

  useEffect(() => {
    onValidChange(done !== null);
  }, [done, onValidChange]);

  const install = useMutation({
    mutationFn: () => api.installOutput(choice.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OUTPUTS_QUERY_KEY });
    },
  });
  const enableBeta = useMutation({
    mutationFn: () => api.updatePluginSettings({ output_plugins_enabled: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLUGIN_SETTINGS_QUERY_KEY });
      install.mutate();
    },
  });

  // Install as soon as the step opens (choosing an output installs it, plan
  // D18). Once per step: the server answers an installed output as it is.
  const started = useRef(false);
  useEffect(() => {
    if (done || started.current) return;
    started.current = true;
    install.mutate();
  }, [done, install]);

  if (done) {
    return (
      <Alert variant="success" data-testid="wizard-output-created">
        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
        <AlertDescription>{t("created", { board: done.name })}</AlertDescription>
      </Alert>
    );
  }

  if (install.isPending || enableBeta.isPending) {
    return (
      <Flex align="center" gap="2" role="status" data-testid="wizard-output-installing">
        <Spinner label={null} />
        <Text as="span" tone="muted">
          {t("installing", { name: choice.name })}
        </Text>
      </Flex>
    );
  }

  if (install.isError) {
    const failure = classify(install.error);
    return (
      <Stack gap="3" data-testid="wizard-output-install-error" data-kind={failure.kind}>
        {failure.kind === "beta" ? (
          <Alert variant="warning">
            <ShieldAlert className="h-4 w-4" aria-hidden="true" />
            <AlertTitle>{t("betaTitle", { name: choice.name })}</AlertTitle>
            <AlertDescription>
              <Stack gap="2">
                <Text size="sm">{t("betaBody")}</Text>
                {enableBeta.isError && <Text size="sm">{t("enableBetaFailed")}</Text>}
                <Flex>
                  <Button type="button" size="sm" onClick={() => enableBeta.mutate()}>
                    {t("enableBeta")}
                  </Button>
                </Flex>
              </Stack>
            </AlertDescription>
          </Alert>
        ) : (
          <Alert variant="destructive">
            {failure.kind === "offline" ? (
              <WifiOff className="h-4 w-4" aria-hidden="true" />
            ) : (
              <XCircle className="h-4 w-4" aria-hidden="true" />
            )}
            <AlertTitle>{t("installFailed", { name: choice.name })}</AlertTitle>
            <AlertDescription>
              <Stack gap="2">
                <Text size="sm">
                  {failure.kind === "offline" ? t("offline", { name: choice.name }) : failure.message}
                </Text>
                <Flex>
                  <Button type="button" size="sm" variant="outline" onClick={() => install.mutate()}>
                    {t("retry")}
                  </Button>
                </Flex>
              </Stack>
            </AlertDescription>
          </Alert>
        )}
      </Stack>
    );
  }

  if (!install.data) return null;
  return (
    <OutputBoardForm
      output={install.data}
      setIsLoading={setIsLoading}
      onCreated={onCreated}
      createLabel={tbs("createBoard")}
      replacePlaceholder={replacePlaceholder}
    />
  );
}

function OutputBoardForm({
  output,
  onCreated,
  setIsLoading,
  createLabel,
  replacePlaceholder,
}: {
  output: OutputSummary;
  onCreated: (board: WizardCreatedBoard) => void;
  setIsLoading: (loading: boolean) => void;
  createLabel: string;
  replacePlaceholder: boolean;
}) {
  const t = useTranslations("wizard.outputSetup");
  const tbs = useTranslations("boardSettingsScreen");
  const queryClient = useQueryClient();
  const [name, setName] = useState(output.name);
  const [deviceModel, setDeviceModel] = useState(output.device_models[0]?.id ?? "");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  // What the chosen LED device looks like, showing the board's name: FiestaUI
  // draws a model it builds in as its matrix; a plugin's own model is only
  // known once the board exists, so it shows no preview here (nor does a
  // split-flap one, whose shape the rest of the wizard already shows).
  const resolvedModel = resolveBoardModel({ device_model: deviceModel });
  const previewModel = isLedModel(resolvedModel) ? resolvedModel : null;

  const create = useMutation({
    mutationFn: async () => {
      setIsLoading(true);
      try {
        const board = await api.createOutputBoard(output.id, {
          device_model: deviceModel,
          output_config: config,
          ...(name.trim() ? { name: name.trim() } : {}),
        });
        if (replacePlaceholder) await removeUntouchedPlaceholder(board.id);
        return board;
      } finally {
        setIsLoading(false);
      }
    },
    onSuccess: (board) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      onCreated({ outputId: output.id, boardId: board.id, name: board.name });
    },
  });

  return (
    // Not a <form>: an action's input dialog is a form of its own, and React
    // bubbles its submit through the portal into any form around it.
    <Stack gap="4">
      {!output.available && (
        <Alert variant="warning">
          <AlertDescription>{tbs("betaRequired")}</AlertDescription>
        </Alert>
      )}
      <Grid gap="1.5">
        <Label htmlFor="wizard-output-board-name">{tbs("boardNameLabel")}</Label>
        <Input
          id="wizard-output-board-name"
          value={name}
          maxLength={MAX_BOARD_NAME_LENGTH}
          onChange={(e) => setName(e.target.value)}
          placeholder={tbs("boardNamePlaceholder")}
        />
      </Grid>
      {output.device_models.length > 1 && (
        <Grid gap="1.5">
          <Label htmlFor="wizard-output-device-model">{tbs("deviceModelLabel")}</Label>
          <Select value={deviceModel} onValueChange={(v) => v && setDeviceModel(v)}>
            <SelectTrigger id="wizard-output-device-model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {output.device_models.map((model) => (
                <SelectItem key={model.id} value={model.id}>
                  {model.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Grid>
      )}
      {previewModel && (
        <Box data-testid="wizard-output-device-preview" className="flex justify-center">
          <DevicePreview model={previewModel} message={name.trim() || output.name} size="sm">
            {null}
          </DevicePreview>
        </Box>
      )}
      <PluginBoardSettings
        output={output}
        values={config}
        onChange={setConfig}
        deviceModel={deviceModel}
        disabled={create.isPending}
      />
      {create.isError && (
        <Alert variant="destructive" data-testid="wizard-output-create-error">
          <XCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>{t("createFailed")}</AlertTitle>
          <AlertDescription>{create.error.message}</AlertDescription>
        </Alert>
      )}
      <Button
        type="button"
        onClick={() => create.mutate()}
        disabled={create.isPending || !deviceModel}
        className="w-full"
      >
        {create.isPending ? tbs("creating") : createLabel}
      </Button>
    </Stack>
  );
}

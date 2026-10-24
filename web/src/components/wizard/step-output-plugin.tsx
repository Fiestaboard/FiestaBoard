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
 * different of the user: the repository could not be downloaded (503 —
 * check the internet connection), or the plugin cannot run on this
 * FiestaBoard (400 — the server's reason). No opt-in is ever asked for:
 * display plugins need none since settings v7.
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
import { CheckCircle2, WifiOff, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DevicePreview } from "@/components/device-preview";
import { OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { OutputSummary } from "@/lib/api";
import { api, ApiError } from "@/lib/api";
import {
  MAX_BOARD_NAME_LENGTH,
  MAX_GRID_COLS,
  MAX_GRID_ROWS,
  MAX_NOTES_PER_AXIS,
  MIN_GRID_COLS,
  MIN_GRID_ROWS,
  NOTE_COLS,
  NOTE_ROWS,
} from "@/lib/board-dimensions";
import { isLedModel, modelInNewBoardFace, resolveBoardModel } from "@/lib/device-preview";

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
  connectionVerified?: boolean;
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

type InstallFailure = { kind: "offline"; message: string } | { kind: "refused"; message: string };

function classify(error: unknown): InstallFailure {
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
        <AlertDescription>
          <Stack gap="1">
            <Text>{t("created", { board: done.name })}</Text>
            <Text size="sm">{done.connectionVerified ? t("verified") : t("savedUnverified")}</Text>
          </Stack>
        </AlertDescription>
      </Alert>
    );
  }

  if (install.isPending) {
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
  const [size, setSize] = useState<Record<string, string>>({});
  const modelGeometry = output.device_models.find((model) => model.id === deviceModel)?.geometry;
  const sizeFields =
    modelGeometry?.kind === "panel"
      ? [
          {
            key: "rows",
            label: t("rows"),
            min: MIN_GRID_ROWS,
            max: MAX_GRID_ROWS,
            fallback: modelGeometry.rows ?? MIN_GRID_ROWS,
          },
          {
            key: "cols",
            label: t("columns"),
            min: MIN_GRID_COLS,
            max: MAX_GRID_COLS,
            fallback: modelGeometry.cols ?? MIN_GRID_COLS,
          },
        ]
      : modelGeometry?.kind === "note_array"
        ? [
            { key: "notes_tall", label: t("notesTall"), min: 1, max: MAX_NOTES_PER_AXIS, fallback: 1 },
            { key: "notes_wide", label: t("notesWide"), min: 1, max: MAX_NOTES_PER_AXIS, fallback: 1 },
          ]
        : [];
  const geometry = Object.fromEntries(
    sizeFields.map((field) => [field.key, Number(size[field.key] ?? field.fallback)]),
  );
  const sizeValid = sizeFields.every(
    (field) =>
      Number.isInteger(geometry[field.key]) && geometry[field.key] >= field.min && geometry[field.key] <= field.max,
  );
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [verifiedConfig, setVerifiedConfig] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const configKey = JSON.stringify({ config, deviceModel });
  const verified = verifiedConfig === configKey;
  const canTest = output.actions.some((action) => action.id === "test_connection");
  // What the chosen LED device looks like, showing the board's name: FiestaUI
  // draws a model it builds in as its matrix; a plugin's own model is only
  // known once the board exists, so it shows no preview here (nor does a
  // split-flap one, whose shape the rest of the wizard already shows).
  // A new LED board is drawn in the face it will be created in (a Pixoo 64
  // is created Large, 5x7), which core names per device model.
  const resolvedModel = modelInNewBoardFace(
    resolveBoardModel({ device_model: deviceModel }),
    output.device_models.find((model) => model.id === deviceModel),
  );
  const previewModel = isLedModel(resolvedModel) ? resolvedModel : null;

  const create = useMutation({
    // Creating a board is not idempotent: an interrupted response must not submit it twice.
    retry: false,
    mutationFn: async () => {
      setIsLoading(true);
      try {
        const board = await api.createOutputBoard(output.id, {
          device_model: deviceModel,
          output_config: config,
          ...(sizeFields.length ? { geometry } : {}),
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
      onCreated({ outputId: output.id, boardId: board.id, name: board.name, connectionVerified: verified });
    },
  });

  return (
    // Not a <form>: an action's input dialog is a form of its own, and React
    // bubbles its submit through the portal into any form around it.
    <Stack gap="4">
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
          <Select
            value={deviceModel}
            disabled={create.isPending || actionPending}
            onValueChange={(v) => {
              if (v) {
                setDeviceModel(v);
                setSize({});
                setVerifiedConfig(null);
              }
            }}
          >
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
      {sizeFields.length > 0 && (
        <Stack gap="2">
          <Text size="sm" tone="muted">
            {t("sizeHelp")}
          </Text>
          <Grid cols="2" gap="3">
            {sizeFields.map((field) => (
              <Stack key={field.key} gap="1">
                <Label htmlFor={`wizard-size-${field.key}`}>{field.label}</Label>
                <Input
                  id={`wizard-size-${field.key}`}
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={1}
                  value={size[field.key] ?? field.fallback}
                  disabled={create.isPending || actionPending}
                  onChange={(event) => setSize((current) => ({ ...current, [field.key]: event.target.value }))}
                  aria-invalid={
                    !Number.isInteger(geometry[field.key]) ||
                    geometry[field.key] < field.min ||
                    geometry[field.key] > field.max
                  }
                />
                <Text size="xs" tone="muted">
                  {t("sizeRange", { min: field.min, max: field.max })}
                </Text>
              </Stack>
            ))}
          </Grid>
        </Stack>
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
        onChange={(values) => {
          setConfig(values);
          setVerifiedConfig(null);
        }}
        deviceModel={deviceModel}
        facts={{ device_type: "panel", device_model: deviceModel }}
        onGeometry={
          sizeFields.length
            ? (detected) => {
                setSize(
                  modelGeometry?.kind === "note_array"
                    ? {
                        notes_tall: String(detected.notes_tall ?? detected.rows / NOTE_ROWS),
                        notes_wide: String(detected.notes_wide ?? detected.cols / NOTE_COLS),
                      }
                    : { rows: String(detected.rows), cols: String(detected.cols) },
                );
              }
            : undefined
        }
        disabled={create.isPending}
        onActionStateChange={(id, pending) => {
          setActionPending(pending);
          if (id === "test_connection" && pending) setVerifiedConfig(null);
        }}
        onActionResult={(id, result, tested) => {
          if (id === "test_connection") setVerifiedConfig(result.status === "ok" ? JSON.stringify(tested) : null);
        }}
      />
      <Stack gap="1" className="rounded-lg bg-muted p-3" data-testid="plugin-connection-status" role="status">
        <Text weight="medium">{verified ? t("verified") : t("unverified")}</Text>
        <Text size="sm" tone="muted">
          {verified ? t("verifiedHelp") : canTest ? t("testHelp") : t("noTestHelp")}
        </Text>
      </Stack>
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
        disabled={create.isPending || actionPending || !deviceModel || !sizeValid}
        className="w-full"
      >
        {create.isPending ? tbs("creating") : createLabel}
      </Button>
    </Stack>
  );
}

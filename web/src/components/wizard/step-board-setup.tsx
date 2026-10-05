"use client";

/**
 * The setup wizard's Vestaboard step: the board's own settings screen — the
 * one Settings → Hardware shows, drawn from the Vestaboard output's manifest
 * (plan D13) — on draft settings (scan, Get API Key from Board and Test
 * Connection run on the draft action route, before a board exists), then the
 * board's type, colour and code-62 flap. A passing Test Connection saves the
 * board (settings-v4 shape: its connection in `output_config`) and unlocks
 * Next.
 */
import { Alert, AlertDescription, Flex, Stack, Text, ToggleCard, ToggleCardGroup } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { useOutputs } from "@/components/settings/output-boards";
import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, BoardInstance, Code62Glyph } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The board shapes the wizard can set up. */
type DeviceType = "flagship" | "note";

function isDeviceType(value: string): value is DeviceType {
  return value === "flagship" || value === "note";
}

/**
 * The two flaps a Flagship's character-code-62 slot can physically carry
 * (issue #1657). Module scope so the swatch pair has one source of truth.
 */
const CODE62_CHOICES: ReadonlyArray<{ value: Code62Glyph; glyph: string; labelKey: string }> = [
  { value: "degree", glyph: "°", labelKey: "code62DegreeAriaLabel" },
  { value: "heart", glyph: "♥", labelKey: "code62HeartAriaLabel" },
];

export interface BoardConfig {
  /** The Vestaboard's connection, as its settings screen edits it (the board's `output_config`). */
  output_config: Record<string, unknown>;
  connectionVerified: boolean;
  device_type: DeviceType;
  board_color: "black" | "white";
  /** Which flap this Flagship's code-62 slot carries (issue #1657). */
  code62_glyph: Code62Glyph;
}

interface StepBoardSetupProps {
  config: BoardConfig;
  onConfigChange: (config: BoardConfig) => void;
  onValidChange: (valid: boolean) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
}

export function StepBoardSetup({ config, onConfigChange, onValidChange, setIsLoading }: StepBoardSetupProps) {
  const t = useTranslations("wizard.boardSetup");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const { data: outputs, isLoading: outputsLoading } = useOutputs();
  const vestaboard = outputs?.find((o) => o.id === "vestaboard");
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    onValidChange(config.connectionVerified);
  }, [config.connectionVerified, onValidChange]);

  const facts = useMemo(() => ({ device_type: config.device_type, device_model: null }), [config.device_type]);

  // Editing the connection un-verifies it: the board saved by the last
  // passing test is not what the form now says.
  const onSettingsChange = (outputConfig: Record<string, unknown>) =>
    onConfigChange({ ...config, output_config: outputConfig, connectionVerified: false });

  const onActionResult = useCallback(
    async (actionId: string, result: ActionResult) => {
      if (actionId !== "test_connection") return;
      if (result.status !== "ok") {
        onConfigChange({ ...config, connectionVerified: false });
        return;
      }
      setIsLoading(true);
      setSaveError(null);
      try {
        // The board store is the one source of truth: first-run detection
        // reads it (plan D13).
        await api.updateBoardSettings({
          boards: [
            {
              // No name: the backend fills in its default ("My Board");
              // users rename boards in Settings → Boards (issue #1792).
              device_type: config.device_type,
              board_color: config.board_color,
              code62_glyph: config.code62_glyph,
              enabled: true,
              output: "vestaboard",
              output_config: config.output_config,
            } as BoardInstance,
          ],
        });
        queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
        onConfigChange({ ...config, connectionVerified: true });
      } catch (error) {
        setSaveError(error instanceof Error ? error.message : t("connectionTestFailed"));
        onConfigChange({ ...config, connectionVerified: false });
      } finally {
        setIsLoading(false);
      }
    },
    [config, onConfigChange, queryClient, setIsLoading, t],
  );

  const onGeometry = (geometry: ActionGeometry) => {
    if (isDeviceType(geometry.device_type)) onConfigChange({ ...config, device_type: geometry.device_type });
  };

  const previewMessage = useMemo(() => {
    if (config.device_type === "note") {
      return ["   WELCOME TO  ", "  FIESTABOARD! ", ""].join("\n");
    }
    const colorCodes = [64, 65, 63, 68];
    const colorRow = Array.from({ length: 22 }, (_, i) => `{${colorCodes[i % colorCodes.length]}}`).join("");
    return [colorRow, "", "      WELCOME TO      ", "     FIESTABOARD!     ", "", colorRow].join("\n");
  }, [config.device_type]);

  return (
    <Stack gap="6">
      {vestaboard ? (
        <PluginBoardSettings
          output={vestaboard}
          values={config.output_config}
          onChange={onSettingsChange}
          facts={facts}
          onGeometry={onGeometry}
          onActionResult={(id, result) => void onActionResult(id, result)}
        />
      ) : outputsLoading ? (
        <Flex justify="center">
          <Spinner />
        </Flex>
      ) : (
        <Alert variant="destructive">
          <AlertDescription>{t("connectionTestFailed")}</AlertDescription>
        </Alert>
      )}

      {config.connectionVerified && (
        <Flex align="center" gap="2" role="status" data-testid="wizard-board-saved">
          <CheckCircle className="h-4 w-4 text-success" aria-hidden="true" />
          <Text as="span" size="sm">
            {t("connectedSaved")}
          </Text>
        </Flex>
      )}
      {saveError && (
        <Alert variant="destructive">
          <AlertDescription>{saveError}</AlertDescription>
        </Alert>
      )}

      {/* Device Type & Board Color */}
      <Stack gap="4" className="pt-4 border-t">
        <Stack gap="3">
          <Text weight="medium">{t("boardType")}</Text>
          {/* One-of-two, so a radiogroup: one tab stop, arrows move the
              choice, and each tile announces "1 of 2". */}
          <ToggleCardGroup
            columns="2"
            align="center"
            value={config.device_type}
            onValueChange={(value) => {
              if (isDeviceType(value)) onConfigChange({ ...config, device_type: value });
            }}
            aria-label={t("boardType")}
          >
            <ToggleCard value="flagship" title={tc("flagship")} description={t("flagshipDimensions")} />
            <ToggleCard value="note" title={tc("note")} description={t("noteDimensions")} />
          </ToggleCardGroup>
        </Stack>

        <Stack gap="3">
          <Text weight="medium">{t("boardColor")}</Text>
          <Flex align="center" gap="3">
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "black" })}
              aria-label={tc("black")}
              aria-pressed={config.board_color === "black"}
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-dark transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                config.board_color === "black"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground",
              )}
            />
            <button
              type="button"
              onClick={() => onConfigChange({ ...config, board_color: "white" })}
              aria-label={tc("white")}
              aria-pressed={config.board_color === "white"}
              className={cn(
                "h-8 w-8 rounded-full border-2 bg-board-surface-light transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                config.board_color === "white"
                  ? "border-primary ring-2 ring-primary/30"
                  : "border-border hover:border-muted-foreground",
              )}
            />
          </Flex>
        </Stack>

        {/* Code-62 flap (issue #1657). Flagship only: Note hardware has only
            ever carried the heart, so there is nothing to ask its owner. */}
        {config.device_type === "flagship" && (
          <Stack gap="3">
            <Text weight="medium">{t("code62Label")}</Text>
            <Text size="sm" tone="muted">
              {t("code62Help")}
            </Text>
            <Flex align="center" gap="3">
              {CODE62_CHOICES.map(({ value, glyph, labelKey }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onConfigChange({ ...config, code62_glyph: value })}
                  aria-label={t(labelKey)}
                  aria-pressed={config.code62_glyph === value}
                  data-testid={`wizard-code62-${value}`}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                    config.code62_glyph === value
                      ? "border-primary ring-2 ring-primary/30"
                      : "border-border hover:border-muted-foreground",
                  )}
                >
                  <Text as="span" aria-hidden="true">
                    {glyph}
                  </Text>
                </button>
              ))}
            </Flex>
          </Stack>
        )}

        {/* Live board preview */}
        <Stack gap="2" className="pt-3">
          <Text weight="medium" tone="muted">
            {tc("preview")}
          </Text>
          <ScaledBoardDisplay
            message={previewMessage}
            size="sm"
            boardType={config.board_color}
            deviceType={config.device_type}
            code62Glyph={config.code62_glyph}
          />
        </Stack>
      </Stack>
    </Stack>
  );
}

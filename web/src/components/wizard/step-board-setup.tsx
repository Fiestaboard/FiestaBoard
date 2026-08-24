"use client";

import {
  Button,
  Flex,
  Grid,
  Input,
  Label,
  List,
  ListItem,
  Stack,
  Text,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { SecretInput } from "@fiestaboard/ui/components/forms/secret-input";
import { CheckCircle, Cloud, HelpCircle, Key, KeyRound, Loader2, Search, Wifi, XCircle } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, Code62Glyph, DiscoveredBoard } from "@/lib/api";
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

interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
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

type LocalKeyMode = "api_key" | "enablement_token";

export function StepBoardSetup({
  config,
  onConfigChange,
  onValidChange,
  isLoading,
  setIsLoading,
}: StepBoardSetupProps) {
  const t = useTranslations("wizard.boardSetup");
  const tc = useTranslations("common");
  const tbs = useTranslations("boardSettings");
  // Mirrors `config` for use inside async callbacks (connection tests, board
  // scans) so they always read the latest value instead of a stale closure.
  // Refs may only be read/written outside of render, so the mirror is
  // synced in an effect rather than assigned inline during render.
  const configRef = useRef(config);
  useEffect(() => {
    configRef.current = config;
  }, [config]);

  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "success" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");
  const [troubleshootingSteps, setTroubleshootingSteps] = useState<string[]>([]);
  const [localKeyMode, setLocalKeyMode] = useState<LocalKeyMode>("api_key");
  const [enablementToken, setEnablementToken] = useState("");
  const [enablementStatus, setEnablementStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [enablementMessage, setEnablementMessage] = useState("");
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [discoveredBoards, setDiscoveredBoards] = useState<DiscoveredBoard[]>([]);

  // Update validity when config or test status changes
  useEffect(() => {
    const hasRequiredFields =
      config.api_mode === "cloud" ? !!config.cloud_key : !!config.local_api_key && !!config.host;

    onValidChange(hasRequiredFields && config.connectionVerified);
  }, [config, onValidChange]);

  const handleModeChange = (mode: "local" | "cloud") => {
    onConfigChange({
      ...config,
      api_mode: mode,
      connectionVerified: false,
    });
    setTestStatus("idle");
    setTestMessage("");
    setEnablementStatus("idle");
    setEnablementMessage("");
  };

  const handleScanForBoards = async () => {
    setScanStatus("scanning");
    setDiscoveredBoards([]);
    try {
      const result = await api.scanForBoards();
      setDiscoveredBoards(result.boards);
      setScanStatus("done");
    } catch {
      setScanStatus("error");
    }
  };

  const handleSelectBoard = (board: DiscoveredBoard) => {
    onConfigChange({
      ...config,
      host: board.ip,
      connectionVerified: false,
    });
    setTestStatus("idle");
  };

  const handleEnableLocalApi = async () => {
    if (!config.host || !enablementToken) return;

    setEnablementStatus("loading");
    setEnablementMessage("");
    setIsLoading(true);

    try {
      const result = await api.enableLocalApi({
        host: config.host,
        enablement_token: enablementToken,
      });

      if (result.success && result.api_key) {
        setEnablementStatus("success");
        setEnablementMessage(result.message);
        // Update the config with the retrieved API key
        onConfigChange({
          ...config,
          local_api_key: result.api_key,
          connectionVerified: false,
        });
        // Switch to API key mode since we now have one
        setLocalKeyMode("api_key");
        // Clear the enablement token
        setEnablementToken("");
      } else {
        setEnablementStatus("error");
        setEnablementMessage(result.message || t("failedToEnableLocalApi"));
      }
    } catch (error) {
      setEnablementStatus("error");
      setEnablementMessage(error instanceof Error ? error.message : t("failedToEnableLocalApi"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    setTestStatus("testing");
    setIsLoading(true);
    setTestMessage("");
    setTroubleshootingSteps([]);

    // Read the latest config from the ref to avoid stale closures
    const cfg = configRef.current;

    try {
      const result = await api.testBoardConnection({
        api_mode: cfg.api_mode,
        local_api_key: cfg.api_mode === "local" ? cfg.local_api_key : undefined,
        cloud_key: cfg.api_mode === "cloud" ? cfg.cloud_key : undefined,
        host: cfg.api_mode === "local" ? cfg.host : undefined,
      });

      if (result.success) {
        setTestStatus("success");
        setTestMessage(result.message);
        setTroubleshootingSteps([]);

        // Save per-board instance first (primary source of truth for settings page)
        await api.updateBoardSettings({
          boards: [
            {
              name: "My Board",
              device_type: cfg.device_type,
              board_color: cfg.board_color,
              code62_glyph: cfg.code62_glyph,
              api_mode: cfg.api_mode,
              host: cfg.host,
              local_api_key: cfg.local_api_key,
              cloud_key: cfg.cloud_key,
              enabled: true,
            } as BoardInstance,
          ],
        });

        // Then save global connection config (used by validation/first-run detection)
        await api.updateBoardConfig({
          api_mode: cfg.api_mode,
          local_api_key: cfg.local_api_key,
          cloud_key: cfg.cloud_key,
          host: cfg.host,
        });

        onConfigChange({ ...cfg, connectionVerified: true });
      } else {
        setTestStatus("error");
        setTestMessage(result.message || t("connectionTestFailed"));
        setTroubleshootingSteps(result.troubleshooting || []);
        onConfigChange({ ...cfg, connectionVerified: false });
      }
    } catch (error) {
      setTestStatus("error");
      setTestMessage(error instanceof Error ? error.message : t("connectionTestFailed"));
      setTroubleshootingSteps([]);
      onConfigChange({ ...configRef.current, connectionVerified: false });
    } finally {
      setIsLoading(false);
    }
  };

  const canTest = config.api_mode === "cloud" ? !!config.cloud_key : !!config.local_api_key && !!config.host;

  const canEnableLocalApi = !!config.host && !!enablementToken;

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
      {/* API Mode Selection */}
      <Stack gap="3">
        <Text size="base" weight="medium">
          {t("connectionType")}
        </Text>
        <Grid cols="2" gap="3">
          <button
            type="button"
            onClick={() => handleModeChange("cloud")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "cloud" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
            )}
          >
            <Cloud className={cn("h-8 w-8", config.api_mode === "cloud" ? "text-primary" : "text-muted-foreground")} />
            <Text as="span" weight="medium">
              {t("cloudApi")}
            </Text>
            <Text as="span" size="xs" tone="muted" className="text-center">
              {t("cloudApiEasiest")}
            </Text>
          </button>

          <button
            type="button"
            onClick={() => handleModeChange("local")}
            className={cn(
              "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
              config.api_mode === "local" ? "border-primary bg-primary/5" : "border-muted hover:border-border",
            )}
          >
            <Wifi className={cn("h-8 w-8", config.api_mode === "local" ? "text-primary" : "text-muted-foreground")} />
            <Text as="span" weight="medium">
              {t("localApi")}
            </Text>
            <Text as="span" size="xs" tone="muted" className="text-center">
              {t("localApiFaster")}
            </Text>
          </button>
        </Grid>
      </Stack>

      {/* Fields based on mode */}
      {config.api_mode === "cloud" ? (
        <Stack gap="4">
          <Stack gap="2">
            <Label htmlFor="cloud_key">{t("readWriteApiKey")}</Label>
            <SecretInput
              id="cloud_key"
              placeholder={t("cloudKeyPlaceholder")}
              value={config.cloud_key}
              onChange={(e) => {
                onConfigChange({
                  ...config,
                  cloud_key: e.target.value,
                  connectionVerified: false,
                });
                setTestStatus("idle");
              }}
              showLabel={tbs("showApiKey")}
              hideLabel={tbs("hideApiKey")}
            />
            <Text size="xs" tone="muted" className="flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              {t("cloudKeyHelp")}
            </Text>
          </Stack>
        </Stack>
      ) : (
        <Stack gap="4">
          {/* Board IP Address - always needed for local */}
          <Stack gap="2">
            <Label htmlFor="host">{t("boardIpAddress")}</Label>
            <Flex gap="2">
              <Input
                id="host"
                placeholder={t("boardIpPlaceholder")}
                value={config.host}
                onChange={(e) => {
                  onConfigChange({
                    ...config,
                    host: e.target.value,
                    connectionVerified: false,
                  });
                  setTestStatus("idle");
                  setEnablementStatus("idle");
                }}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                size="default"
                onClick={handleScanForBoards}
                disabled={scanStatus === "scanning"}
                title={t("scanNetworkTooltip")}
              >
                {scanStatus === "scanning" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </Flex>
            <Text size="xs" tone="muted" className="flex items-center gap-1">
              <HelpCircle className="h-3 w-3" />
              {t("boardIpHelp")}
            </Text>
          </Stack>

          {/* Scan results */}
          {scanStatus === "scanning" && (
            <Flex align="center" gap="2" className="p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <Spinner label={null} />
              <Text as="span" tone="muted">
                {t("scanningNetwork")}
              </Text>
            </Flex>
          )}
          {scanStatus === "done" && discoveredBoards.length === 0 && (
            <Flex align="center" gap="2" className="p-3 rounded-lg bg-muted/50 text-sm text-muted-foreground">
              <HelpCircle className="h-4 w-4" />
              <Text as="span" tone="muted">
                {t("noBoardsFound")}
              </Text>
            </Flex>
          )}
          {scanStatus === "done" && discoveredBoards.length >= 1 && (
            <Stack gap="2">
              <Text>{t("foundBoards", { count: discoveredBoards.length })}</Text>
              <Stack gap="1.5">
                {discoveredBoards.map((board) => (
                  <button
                    key={board.ip}
                    type="button"
                    onClick={() => handleSelectBoard(board)}
                    className={cn(
                      "w-full flex items-center justify-between p-2.5 rounded-md border text-sm transition-colors text-left",
                      config.host === board.ip
                        ? "border-primary bg-primary/5"
                        : "border-muted hover:border-muted-foreground/30",
                    )}
                  >
                    <Text as="span" className="font-mono">
                      {board.ip}
                    </Text>
                    {board.hostname && (
                      <Text as="span" size="xs" tone="muted">
                        {board.hostname}
                      </Text>
                    )}
                  </button>
                ))}
              </Stack>
            </Stack>
          )}
          {scanStatus === "error" && (
            <Flex align="center" gap="2" className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
              <XCircle className="h-4 w-4" />
              <Text as="span" tone="destructive">
                {t("scanFailed")}
              </Text>
            </Flex>
          )}

          {/* Local Key Mode Toggle */}
          <Stack gap="3">
            <Text weight="medium">{t("authenticationMethod")}</Text>
            <Grid cols="2" gap="2">
              <button
                type="button"
                onClick={() => setLocalKeyMode("api_key")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "api_key"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground",
                )}
              >
                <Key className="h-4 w-4" />
                {t("apiKey")}
              </button>
              <button
                type="button"
                onClick={() => setLocalKeyMode("enablement_token")}
                className={cn(
                  "flex items-center justify-center gap-2 p-2.5 rounded-md border text-sm transition-all",
                  localKeyMode === "enablement_token"
                    ? "border-primary bg-primary/5 text-primary"
                    : "border-muted hover:border-border text-muted-foreground",
                )}
              >
                <KeyRound className="h-4 w-4" />
                {t("enablementToken")}
              </button>
            </Grid>
          </Stack>

          {localKeyMode === "api_key" ? (
            <Stack gap="2">
              <Label htmlFor="local_api_key">{t("localApiKey")}</Label>
              <SecretInput
                id="local_api_key"
                placeholder={t("localApiKeyPlaceholder")}
                value={config.local_api_key}
                onChange={(e) => {
                  onConfigChange({
                    ...config,
                    local_api_key: e.target.value,
                    connectionVerified: false,
                  });
                  setTestStatus("idle");
                }}
                showLabel={tbs("showApiKey")}
                hideLabel={tbs("hideApiKey")}
              />
              <Text size="xs" tone="muted" className="flex items-center gap-1">
                <HelpCircle className="h-3 w-3" />
                {t("localApiKeyHelp")}
              </Text>
            </Stack>
          ) : (
            <Stack gap="3">
              <Stack gap="2">
                <Label htmlFor="enablement_token">{t("enablementToken")}</Label>
                <SecretInput
                  id="enablement_token"
                  placeholder={t("enablementTokenPlaceholder")}
                  value={enablementToken}
                  onChange={(e) => {
                    setEnablementToken(e.target.value);
                    setEnablementStatus("idle");
                  }}
                  showLabel={tbs("showToken")}
                  hideLabel={tbs("hideToken")}
                />
                <Text size="xs" tone="muted" className="flex items-center gap-1">
                  <HelpCircle className="h-3 w-3" />
                  {t("enablementTokenHelp")}
                </Text>
              </Stack>

              <Button
                onClick={handleEnableLocalApi}
                disabled={!canEnableLocalApi || isLoading}
                variant="secondary"
                className="w-full"
              >
                {enablementStatus === "loading" ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    {t("enablingLocalApi")}
                  </>
                ) : enablementStatus === "success" ? (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2 text-success" />
                    {t("apiKeyRetrieved")}
                  </>
                ) : (
                  t("getApiKeyFromBoard")
                )}
              </Button>

              {/* Enablement status message */}
              {enablementMessage && (
                <Flex
                  align="start"
                  gap="2"
                  className={cn(
                    "p-3 rounded-lg text-sm",
                    enablementStatus === "success"
                      ? "bg-success/10 text-success"
                      : "bg-destructive/10 text-destructive",
                  )}
                >
                  {enablementStatus === "success" ? (
                    <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                  )}
                  {enablementMessage}
                </Flex>
              )}
            </Stack>
          )}
        </Stack>
      )}

      {/* Test Connection */}
      <Stack gap="3">
        <Button
          onClick={handleTestConnection}
          disabled={!canTest || isLoading}
          variant={testStatus === "success" ? "outline" : "default"}
          className="w-full"
        >
          {testStatus === "testing" ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              {t("testingConnection")}
            </>
          ) : testStatus === "success" ? (
            <>
              <CheckCircle className="h-4 w-4 mr-2 text-success" />
              {t("connectedTestAgain")}
            </>
          ) : (
            t("testConnection")
          )}
        </Button>

        {/* Status message */}
        {testMessage && (
          <Flex
            align="start"
            gap="2"
            className={cn(
              "p-3 rounded-lg text-sm",
              testStatus === "success" ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
            )}
          >
            {testStatus === "success" ? (
              <CheckCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
            )}
            <Stack gap="2" className="flex-1">
              {testMessage}
              {testStatus === "error" && troubleshootingSteps.length > 0 && (
                <Stack gap="1.5" className="mt-2">
                  <Text size="xs" weight="medium" className="text-foreground/80 uppercase tracking-wide">
                    {t("thingsToTry")}
                  </Text>
                  <List as="ol" marker="decimal" gap="1" className="text-foreground/70">
                    {troubleshootingSteps.map((step, i) => (
                      <ListItem key={i}>{step}</ListItem>
                    ))}
                  </List>
                </Stack>
              )}
            </Stack>
          </Flex>
        )}
      </Stack>

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

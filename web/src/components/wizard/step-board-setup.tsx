"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Flex,
  Grid,
  Input,
  Label,
  List,
  ListItem,
  SecretInput,
  SegmentedControl,
  SegmentedControlItem,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
  ToggleCard,
  ToggleCardGroup,
} from "@fiestaboard/ui";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Info } from "lucide-react";
import { useEffect, useImperativeHandle, useRef, useState } from "react";

import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { ActionResult, BoardInstance, Code62Glyph } from "@/lib/api";
import { api } from "@/lib/api";

import { removeUntouchedPlaceholder } from "./default-board";
import type { WizardCreatedBoard } from "./step-output-plugin";

export interface BoardConfig {
  output_config: Record<string, unknown>;
  connectionVerified: boolean;
  device_type: "flagship" | "note";
  board_color: "black" | "white";
  code62_glyph: Code62Glyph;
  name?: string;
}

export interface BoardSetupHandle {
  save: (skipTest?: boolean) => Promise<WizardCreatedBoard | null>;
}

interface StepBoardSetupProps {
  config: BoardConfig;
  onConfigChange: (config: BoardConfig) => void;
  onValidChange: (valid: boolean) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  requireTest?: boolean;
  replacePlaceholder?: boolean;
  createdBoardId?: string;
  ref?: React.Ref<BoardSetupHandle>;
}

/** Read-only draft testing; saving happens only on Continue or Add display. */
export function StepBoardSetup({
  config,
  onConfigChange,
  onValidChange,
  isLoading,
  setIsLoading,
  requireTest = false,
  replacePlaceholder = true,
  createdBoardId,
  ref,
}: StepBoardSetupProps) {
  const t = useTranslations("wizard.connection");
  const queryClient = useQueryClient();
  const { data: settings } = useBoardSettings();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [knownChoice, setKnownChoice] = useState("keep");
  const busy = useRef(false);
  const revision = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const mode = config.output_config.api_mode === "cloud" ? "cloud" : "local";
  const host = String(config.output_config.host ?? "");
  const keyField = mode === "local" ? "local_api_key" : "cloud_key";
  const secret = String(config.output_config[keyField] ?? "");
  const name = config.name ?? t("defaultName");
  const known = settings?.boards?.find(
    (board) =>
      (board.output ?? "vestaboard") === "vestaboard" &&
      (board.id === createdBoardId ||
        (mode === "local" &&
          host.trim() &&
          String(board.output_config?.host ?? "")
            .trim()
            .toLowerCase() === host.trim().toLowerCase()) ||
        (mode === "cloud" && secret && secret !== "***" && board.output_config?.cloud_key === secret)),
  );
  const keep = !!known && knownChoice === "keep";
  const fieldsValid = !!name.trim() && !!secret.trim() && (mode === "cloud" || !!host.trim());
  const failed = result?.status === "error";
  const valid = keep || (fieldsValid && !failed && (!requireTest || config.connectionVerified));

  useEffect(() => {
    onValidChange(valid);
  }, [onValidChange, valid]);

  const change = (next: BoardConfig) => {
    revision.current++;
    setResult(null);
    setError(null);
    onConfigChange({ ...next, connectionVerified: false });
  };
  const connection = (values: Record<string, unknown>) => change({ ...config, output_config: values });

  const test = async () => {
    if (busy.current || !fieldsValid) return;
    busy.current = true;
    const testedRevision = revision.current;
    setIsLoading(true);
    setError(null);
    const start = performance.now();
    try {
      const response = await api.runDraftOutputAction("vestaboard", "test_connection", {
        output_config: config.output_config,
      });
      if (!alive.current || revision.current !== testedRevision) return;
      setElapsed(Math.round(performance.now() - start));
      setResult(response);
      const deviceType = response.geometry?.device_type;
      onConfigChange({
        ...config,
        connectionVerified: response.status === "ok",
        ...(deviceType === "flagship" || deviceType === "note" ? { device_type: deviceType } : {}),
      });
    } catch (failure) {
      if (alive.current && revision.current === testedRevision) {
        setResult({
          status: "error",
          message: failure instanceof Error ? failure.message : t("failed"),
          guidance: [],
          fields: {},
          geometry: null,
          devices: [],
        });
        onConfigChange({ ...config, connectionVerified: false });
      }
    } finally {
      busy.current = false;
      if (alive.current) setIsLoading(false);
    }
  };

  useImperativeHandle(ref, () => ({
    save: async (skipTest = false) => {
      if (busy.current || (!valid && !(skipTest && fieldsValid))) return null;
      busy.current = true;
      setIsLoading(true);
      setError(null);
      try {
        // Re-read before writing: preserve the fleet, and recognize a board
        // added from another browser while this step was open.
        const fresh = await api.getBoardSettings();
        const existing = fresh.boards.find(
          (board) =>
            (board.output ?? "vestaboard") === "vestaboard" &&
            (board.id === createdBoardId ||
              (mode === "local" &&
                host.trim() &&
                String(board.output_config?.host ?? "")
                  .trim()
                  .toLowerCase() === host.trim().toLowerCase()) ||
              (mode === "cloud" && secret !== "***" && secret && board.output_config?.cloud_key === secret)),
        );
        let board: BoardInstance | undefined = existing;
        if (existing) {
          if (knownChoice === "update") {
            await api.updateBoardSettings({
              boards: fresh.boards.map((item) =>
                item.id === existing.id ? { ...item, output_config: config.output_config } : item,
              ),
            });
          }
        } else {
          const saved = await api.addBoard({
            name: name.trim(),
            device_type: config.device_type,
            board_color: config.board_color,
            code62_glyph: config.code62_glyph,
            enabled: true,
            output: "vestaboard",
            output_config: config.output_config,
          });
          board = saved.boards.find((item) => !fresh.boards.some((old) => old.id === item.id));
        }
        if (!board) throw new Error(t("saveFailed"));
        if (replacePlaceholder && !existing) await removeUntouchedPlaceholder(board.id);
        void queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
        return {
          outputId: "vestaboard",
          boardId: board.id,
          name: board.name,
          connectionVerified: config.connectionVerified,
        };
      } catch (failure) {
        if (alive.current) setError(failure instanceof Error ? failure.message : t("saveFailed"));
        return null;
      } finally {
        busy.current = false;
        if (alive.current) setIsLoading(false);
      }
    },
  }));

  return (
    <Stack gap="4">
      {known && (
        <Stack gap="3">
          <Alert variant="info">
            <Info aria-hidden="true" />
            <AlertTitle>{t("knownTitle")}</AlertTitle>
            <AlertDescription>{t("knownDescription", { name: known.name, host })}</AlertDescription>
          </Alert>
          <ToggleCardGroup value={knownChoice} onValueChange={setKnownChoice} columns="2" aria-label={t("knownTitle")}>
            <ToggleCard value="keep" title={t("keep", { name: known.name })} description={t("keepHint")} />
            <ToggleCard value="update" title={t("update")} description={t("updateHint")} />
          </ToggleCardGroup>
        </Stack>
      )}
      {!keep && (
        <>
          <Grid gap="1.5">
            <Label htmlFor="setup-display-name">{t("name")}</Label>
            <Input
              id="setup-display-name"
              value={name}
              disabled={isLoading}
              maxLength={100}
              onChange={(event) => change({ ...config, name: event.target.value })}
            />
          </Grid>
          <Grid gap="1.5">
            <Label>{t("connection")}</Label>
            <SegmentedControl
              layout="grid"
              value={mode}
              onValueChange={(value) => connection({ ...config.output_config, api_mode: value })}
              aria-label={t("connection")}
            >
              <SegmentedControlItem value="local" disabled={isLoading}>
                {t("local")}
              </SegmentedControlItem>
              <SegmentedControlItem value="cloud" disabled={isLoading}>
                {t("cloud")}
              </SegmentedControlItem>
            </SegmentedControl>
          </Grid>
          {mode === "local" && (
            <Grid gap="1.5">
              <Label htmlFor="setup-board-address">{t("address")}</Label>
              <Input
                id="setup-board-address"
                value={host}
                disabled={isLoading}
                onChange={(event) => connection({ ...config.output_config, host: event.target.value })}
                aria-invalid={failed}
                aria-describedby="setup-address-help"
              />
              <Text id="setup-address-help" size="xs" tone="muted">
                {t("addressHint")}
              </Text>
            </Grid>
          )}
          <Grid gap="1.5">
            <Label htmlFor="setup-board-key">{t(mode === "local" ? "localKey" : "cloudKey")}</Label>
            <SecretInput
              id="setup-board-key"
              value={secret}
              disabled={isLoading}
              revealDisabled={secret === "***"}
              showLabel={t("showKey")}
              hideLabel={t("hideKey")}
              onChange={(event) => connection({ ...config.output_config, [keyField]: event.target.value })}
              aria-describedby="setup-key-help"
            />
            <Text id="setup-key-help" size="xs" tone="muted">
              {t(mode === "local" ? "keyHint" : "cloudHint")}
            </Text>
          </Grid>
          <Grid gap="1.5">
            <Label htmlFor="setup-board-type">{t("boardType")}</Label>
            <Select
              value={config.device_type}
              onValueChange={(value) => {
                if (value === "flagship" || value === "note") change({ ...config, device_type: value });
              }}
              disabled={isLoading}
            >
              <SelectTrigger id="setup-board-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="flagship">{t("typeFlagship")}</SelectItem>
                <SelectItem value="note">{t("typeNote")}</SelectItem>
              </SelectContent>
            </Select>
          </Grid>
          {result?.status === "ok" && (
            <Alert variant="success" role="status">
              <CheckCircle2 aria-hidden="true" />
              <AlertTitle>{t("passed", { ms: elapsed })}</AlertTitle>
              <AlertDescription>{result.message}</AlertDescription>
            </Alert>
          )}
          {failed && (
            <>
              <Alert variant="destructive">
                <Info aria-hidden="true" />
                <AlertTitle>{t("failed")}</AlertTitle>
                <AlertDescription>
                  {result.message} {t("unchanged")}
                </AlertDescription>
              </Alert>
              <Stack gap="2" className="rounded-lg bg-muted p-3">
                <Text weight="medium">{t("tryThis")}</Text>
                <List as="ol" className="list-decimal space-y-2 pl-5 text-sm">
                  <ListItem>{t("checkPower")}</ListItem>
                  <ListItem>{t("checkNetwork")}</ListItem>
                  <ListItem>{t("checkKey")}</ListItem>
                </List>
              </Stack>
            </>
          )}
          <Flex gap="2" wrap>
            <Button
              variant="outline"
              onClick={() => void test()}
              disabled={!fieldsValid || isLoading}
              className="max-md:min-h-11"
            >
              {t(result ? "testAgain" : "test")}
            </Button>
            {failed && mode === "local" && (
              <Button
                variant="ghost"
                onClick={() => connection({ ...config.output_config, api_mode: "cloud" })}
                className="max-md:min-h-11"
              >
                {t("useCloud")}
              </Button>
            )}
          </Flex>
        </>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </Stack>
  );
}

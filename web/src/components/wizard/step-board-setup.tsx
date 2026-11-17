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
} from "@fiestaboard/ui";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Info } from "lucide-react";
import { useEffect, useImperativeHandle, useRef, useState } from "react";

import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { ActionResult, BoardInstance, Code62Glyph } from "@/lib/api";
import { api } from "@/lib/api";
import { MAX_NOTES_PER_AXIS } from "@/lib/board-dimensions";

import { removeUntouchedPlaceholder } from "./default-board";
import {
  ExistingDisplayChoice,
  ExistingDisplayError,
  existingDisplayQuery,
  useExistingDisplay,
} from "./existing-display";
import type { WizardCreatedBoard } from "./step-output-plugin";

export interface BoardConfig {
  output_config: Record<string, unknown>;
  connectionVerified: boolean;
  device_type: "flagship" | "note" | "note_array";
  notes_wide?: number;
  notes_tall?: number;
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
  const td = useTranslations("displaySettings");
  const to = useTranslations("outputSettings.vestaboard.fields");
  const tw = useTranslations("wizard.outputSetup");
  const queryClient = useQueryClient();
  const { data: settings } = useBoardSettings();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [knownSelection, setKnownSelection] = useState<{ boardId: string; value: string } | null>(null);
  const busy = useRef(false);
  const revision = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const isArray = config.device_type === "note_array";
  const notesWide = config.notes_wide ?? 2;
  const notesTall = config.notes_tall ?? 1;
  const topologyValid =
    !isArray ||
    [notesWide, notesTall].every((value) => Number.isInteger(value) && value >= 1 && value <= MAX_NOTES_PER_AXIS);
  const mode = config.output_config.api_mode === "cloud" ? "cloud" : "local";
  const host = String(config.output_config.host ?? "");
  const keyField = isArray ? "note_array_token" : mode === "local" ? "local_api_key" : "cloud_key";
  const secret = String(config.output_config[keyField] ?? "");
  const name = config.name ?? t("defaultName");
  const lookupQuery = existingDisplayQuery(
    "vestaboard",
    {
      ...(isArray
        ? { note_array_token: secret }
        : mode === "local"
          ? { host, port: config.output_config.port }
          : { cloud_key: secret }),
    },
    createdBoardId,
  );
  const lookup = useExistingDisplay(lookupQuery);
  const resumed = settings?.boards.find((board) => board.id === createdBoardId);
  const known =
    lookup.existing[0] ??
    (resumed
      ? { board_id: resumed.id, name: resumed.name, output: resumed.output ?? "vestaboard", matched: "host" as const }
      : null);
  const knownChoice = knownSelection?.boardId === known?.board_id ? (knownSelection?.value ?? "keep") : "keep";
  const setKnownChoice = (value: string) => {
    if (known) setKnownSelection({ boardId: known.board_id, value });
  };
  const keep = !!known && knownChoice === "keep";
  const fieldsValid = topologyValid && !!name.trim() && !!secret.trim() && (mode === "cloud" || !!host.trim());
  const failed = result?.status === "error";
  const valid =
    !lookup.pending &&
    !lookup.error &&
    (keep || (fieldsValid && !failed && (!requireTest || config.connectionVerified)));

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
        output_config: {
          ...config.output_config,
          ...(isArray ? { device_type: "note_array", notes_wide: notesWide, notes_tall: notesTall } : {}),
        },
      });
      if (!alive.current || revision.current !== testedRevision) return;
      setElapsed(Math.round(performance.now() - start));
      setResult(response);
      const deviceType = response.geometry?.device_type;
      onConfigChange({
        ...config,
        connectionVerified: response.status === "ok",
        ...(isArray
          ? {
              notes_wide: response.geometry?.notes_wide ?? notesWide,
              notes_tall: response.geometry?.notes_tall ?? notesTall,
            }
          : deviceType === "flagship" || deviceType === "note"
            ? { device_type: deviceType }
            : {}),
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
        const matches = lookupQuery ? (await api.checkExistingBoards(lookupQuery)).existing : [];
        const existing =
          fresh.boards.find((board) => board.id === matches[0]?.board_id) ??
          fresh.boards.find((board) => board.id === createdBoardId);
        if (matches.length && !existing) throw new Error(t("saveFailed"));
        let board: BoardInstance | undefined = existing;
        if (existing) {
          if (
            knownChoice === "update" &&
            known?.board_id === existing.id &&
            (existing.output ?? "vestaboard") === "vestaboard"
          ) {
            await api.updateBoardSettings({
              boards: fresh.boards.map((item) =>
                item.id === existing.id ? { ...item, output_config: config.output_config } : item,
              ),
            });
          }
        } else {
          if (!fieldsValid) throw new Error(t("saveFailed"));
          const saved = await api.addBoard({
            name: name.trim(),
            device_type: config.device_type,
            ...(isArray ? { notes_wide: notesWide, notes_tall: notesTall } : {}),
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
        <ExistingDisplayChoice
          match={known}
          host={mode === "local" ? host : t("cloud")}
          choice={knownChoice}
          onChange={setKnownChoice}
          output="vestaboard"
        />
      )}
      {lookup.error && <ExistingDisplayError error={lookup.error} retry={lookup.retry} />}
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
              <SegmentedControlItem value="local" disabled={isLoading || isArray}>
                {t("local")}
              </SegmentedControlItem>
              <SegmentedControlItem value="cloud" disabled={isLoading}>
                {isArray ? to("api_mode.cards.cloud.title") : t("cloud")}
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
            <Label htmlFor="setup-board-key">
              {isArray ? to("note_array_token.title") : t(mode === "local" ? "localKey" : "cloudKey")}
            </Label>
            <SecretInput
              id="setup-board-key"
              maxLength={512}
              value={secret}
              disabled={isLoading}
              revealDisabled={secret === "***"}
              showLabel={t("showKey")}
              hideLabel={t("hideKey")}
              onChange={(event) => connection({ ...config.output_config, [keyField]: event.target.value })}
              aria-describedby="setup-key-help"
            />
            <Text id="setup-key-help" size="xs" tone="muted">
              {isArray ? to("note_array_token.description") : t(mode === "local" ? "keyHint" : "cloudHint")}
            </Text>
          </Grid>
          <Grid gap="1.5">
            <Label htmlFor="setup-board-type">{t("boardType")}</Label>
            <Select
              value={config.device_type}
              onValueChange={(value) => {
                if (value === "note_array")
                  change({
                    ...config,
                    device_type: value,
                    notes_wide: 2,
                    notes_tall: 1,
                    output_config: { api_mode: "cloud", note_array_token: config.output_config.note_array_token ?? "" },
                  });
                else if (value === "flagship" || value === "note") change({ ...config, device_type: value });
              }}
              disabled={isLoading}
            >
              <SelectTrigger id="setup-board-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="flagship">{t("typeFlagship")}</SelectItem>
                <SelectItem value="note">{t("typeNote")}</SelectItem>
                <SelectItem value="note_array">{td("noteArrayLabel")}</SelectItem>
              </SelectContent>
            </Select>
          </Grid>
          {isArray && (
            <Grid cols="2" gap="3">
              {(
                [
                  { key: "notes_wide", value: notesWide, label: "notesWide" },
                  { key: "notes_tall", value: notesTall, label: "notesTall" },
                ] as const
              ).map((field) => (
                <Grid key={field.key} gap="1.5">
                  <Label htmlFor={`setup-${field.key}`}>{tw(field.label)}</Label>
                  <Input
                    id={`setup-${field.key}`}
                    type="number"
                    min={1}
                    max={MAX_NOTES_PER_AXIS}
                    value={field.value}
                    disabled={isLoading}
                    onChange={(event) => change({ ...config, [field.key]: Number(event.target.value) })}
                    aria-invalid={!Number.isInteger(field.value) || field.value < 1 || field.value > MAX_NOTES_PER_AXIS}
                  />
                </Grid>
              ))}
            </Grid>
          )}
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

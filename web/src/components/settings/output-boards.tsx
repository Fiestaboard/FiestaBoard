"use client";

/**
 * Boards for outputs other than the Vestaboard (plan D13), in Settings →
 * Hardware:
 *
 * - {@link OtherOutputCards}: the "Add board" choices `GET /outputs` lists
 *   beyond the Vestaboard (whose Flagship / Note / Note array row stays as it
 *   was). FiestaPanel goes to its own section; an output plugin opens
 *   {@link AddOutputBoardDialog}.
 * - {@link AddOutputBoardDialog}: name, device model and the plugin's own
 *   settings screen on draft settings, then `POST /outputs/{id}/boards`.
 * - {@link OutputBoardSettings}: a saved output-plugin board's screen, saved
 *   with the board settings (`output_config`, secrets echoed as `"***"`).
 */
import {
  ActionCard,
  Alert,
  AlertDescription,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cpu, Grid3x3, LayoutGrid, Lightbulb, type LucideIcon, Monitor, MonitorSmartphone, Tv } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import { ANCHOR_ATTR } from "@/lib/ai-choreography/anchors";
import type { BoardInstance, OutputSummary } from "@/lib/api";
import { api } from "@/lib/api";
import { MAX_BOARD_NAME_LENGTH } from "@/lib/board-dimensions";

import { PluginBoardSettings } from "./plugin-board-settings";

export const OUTPUTS_QUERY_KEY = ["outputs"] as const;

/** The outputs this install has (`GET /outputs`). */
export function useOutputs() {
  return useQuery({ queryKey: OUTPUTS_QUERY_KEY, queryFn: () => api.listOutputs(), staleTime: 60_000 });
}

/** A board an output plugin drives: neither a Vestaboard nor a FiestaPanel. */
export function isPluginOutputBoard(board: Pick<BoardInstance, "output">): boolean {
  return !!board.output && board.output !== "vestaboard" && board.output !== "fiestapanel";
}

const ICONS: Record<string, LucideIcon> = {
  cpu: Cpu,
  "grid-3x3": Grid3x3,
  "layout-grid": LayoutGrid,
  lightbulb: Lightbulb,
  monitor: Monitor,
  tv: Tv,
};

/** The Lucide icon a manifest names, from a small known set; a generic display otherwise. */
export function OutputIcon({ name, className }: { name: string | null | undefined; className?: string }) {
  const Icon = (name && ICONS[name]) || MonitorSmartphone;
  return <Icon className={className ?? "h-4 w-4"} aria-hidden="true" />;
}

function scrollToPanels() {
  const section = document.querySelector<HTMLElement>(`[${ANCHOR_ATTR}="settings.panels"]`);
  section?.scrollIntoView({ behavior: "smooth", block: "start" });
  section?.focus?.({ preventScroll: true });
}

export function OtherOutputCards({ onChosen }: { onChosen: () => void }) {
  const t = useTranslations("boardSettingsScreen");
  const { data: outputs } = useOutputs();
  const [adding, setAdding] = useState<OutputSummary | null>(null);
  const others = (outputs ?? []).filter((o) => o.id !== "vestaboard");
  if (others.length === 0) return null;

  return (
    <Stack gap="2" data-testid="other-output-cards">
      <Text as="span" size="xs" tone="muted" id="other-outputs-label">
        {t("otherDisplays")}
      </Text>
      <Grid gap="2" className="sm:grid-cols-2" role="list" aria-labelledby="other-outputs-label">
        {others.map((output) => (
          <Box role="listitem" key={output.id}>
            <ActionCard
              icon={<OutputIcon name={output.icon} />}
              title={output.name}
              description={output.available ? output.description : t("betaRequired")}
              disabled={!output.available}
              data-testid={`add-output-${output.id}`}
              onClick={() => {
                if (output.id === "fiestapanel") {
                  scrollToPanels();
                  onChosen();
                } else {
                  setAdding(output);
                }
              }}
            />
          </Box>
        ))}
      </Grid>
      <Dialog open={adding !== null} onOpenChange={(open) => !open && setAdding(null)}>
        {adding && (
          <AddOutputBoardDialog
            key={adding.id}
            output={adding}
            onDone={() => {
              setAdding(null);
              onChosen();
            }}
          />
        )}
      </Dialog>
    </Stack>
  );
}

export function AddOutputBoardDialog({ output, onDone }: { output: OutputSummary; onDone: () => void }) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [deviceModel, setDeviceModel] = useState(output.device_models[0]?.id ?? "");
  const [config, setConfig] = useState<Record<string, unknown>>({});

  const create = useMutation({
    mutationFn: () =>
      api.createOutputBoard(output.id, {
        device_model: deviceModel,
        output_config: config,
        ...(name.trim() ? { name: name.trim() } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success(t("boardCreated"));
      onDone();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
      <Box
        as="form"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <DialogHeader>
          <DialogTitle>{t("addOutputTitle", { name: output.name })}</DialogTitle>
          <DialogDescription>{output.description}</DialogDescription>
        </DialogHeader>
        <Stack gap="4" className="py-4">
          <Grid gap="1.5">
            <Label htmlFor="output-board-name">{t("boardNameLabel")}</Label>
            <Input
              id="output-board-name"
              value={name}
              maxLength={MAX_BOARD_NAME_LENGTH}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("boardNamePlaceholder")}
            />
          </Grid>
          {output.device_models.length > 1 && (
            <Grid gap="1.5">
              <Label htmlFor="output-device-model">{t("deviceModelLabel")}</Label>
              <Select value={deviceModel} onValueChange={(v) => v && setDeviceModel(v)}>
                <SelectTrigger id="output-device-model">
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
          <PluginBoardSettings output={output} values={config} onChange={setConfig} deviceModel={deviceModel} />
        </Stack>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onDone}>
            {tc("cancel")}
          </Button>
          <Button type="submit" disabled={create.isPending || !deviceModel}>
            {create.isPending ? t("creating") : t("createBoard")}
          </Button>
        </DialogFooter>
      </Box>
    </DialogContent>
  );
}

export function OutputBoardSettings({
  board,
  onSave,
  saving,
}: {
  board: BoardInstance;
  onSave: (outputConfig: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const t = useTranslations("boardSettingsScreen");
  const tc = useTranslations("common");
  const { data: outputs, isLoading } = useOutputs();
  const stored = board.output_config ?? {};
  const [values, setValues] = useState<Record<string, unknown>>(stored);
  const output = outputs?.find((o) => o.id === board.output);

  if (isLoading) return null;
  if (!output) {
    return (
      <Alert variant="warning" data-testid="output-not-installed">
        <AlertDescription>{t("outputNotInstalled", { output: board.output ?? "" })}</AlertDescription>
      </Alert>
    );
  }
  const dirty = JSON.stringify(values) !== JSON.stringify(stored);

  return (
    <Stack gap="3">
      {!output.available && (
        <Alert variant="warning">
          <AlertDescription>{t("betaRequired")}</AlertDescription>
        </Alert>
      )}
      <PluginBoardSettings output={output} values={values} onChange={setValues} boardId={board.id} />
      <Box>
        <Button type="button" size="sm" disabled={!dirty || saving} onClick={() => onSave(values)}>
          {saving ? tc("saving") : t("saveSettings")}
        </Button>
      </Box>
    </Stack>
  );
}

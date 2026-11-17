"use client";

/**
 * The setup wizard's board step for FiestaPanel (plan D18): a TV or any
 * browser. A name and the screen size are all it takes — `POST /panels`
 * creates the panel and its auto-fit board — then the step shows the address
 * to open on the TV. Everything else (aspect ratio, backdrop, calibration)
 * stays in Settings → FiestaPanel.
 */
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Flex,
  Grid,
  IconTile,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Globe, Tv, XCircle } from "lucide-react";
import { useEffect, useImperativeHandle, useRef, useState } from "react";

import { queryKeys } from "@/hooks/use-board";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import { useTranslations } from "@/i18n/translations";
import { api, type Panel } from "@/lib/api";
import { appUrl } from "@/lib/base-path";

import { removeUntouchedPlaceholder } from "./default-board";
import type { WizardCreatedBoard } from "./step-output-plugin";

const MIN_INCHES = 3;
const MAX_INCHES = 200;
const DEFAULT_INCHES = 55;

export interface PanelSetupHandle {
  save: () => Promise<WizardCreatedBoard | null>;
}

interface StepPanelSetupProps {
  ref?: React.Ref<PanelSetupHandle>;
  hideCreate?: boolean;
  createLabel?: string;
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
  ref,
  hideCreate = false,
  createLabel,
}: StepPanelSetupProps) {
  const t = useTranslations("wizard.panelSetup");
  const queryClient = useQueryClient();
  const done = created?.outputId === "fiestapanel" ? created : null;
  const [name, setName] = useState(() => t("defaultName"));
  const [inches, setInches] = useState(String(DEFAULT_INCHES));
  const size = Number(inches);
  const sizeValid = Number.isFinite(size) && size >= MIN_INCHES && size <= MAX_INCHES;

  useEffect(() => {
    onValidChange(done !== null || (!!name.trim() && sizeValid));
  }, [done, name, sizeValid, onValidChange]);

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
      // Populate an already-cached inactive list too: opening the new display
      // must not briefly render the old empty panel list.
      queryClient.setQueryData<{ panels: Panel[]; total: number }>(PANELS_QUERY_KEY, (previous) => {
        if (!previous) return previous;
        const panels = [...previous.panels.filter((item) => item.id !== panel.id), panel];
        return { ...previous, panels, total: panels.length };
      });
      // The display page and page targets read panels through this key.
      void queryClient.invalidateQueries({ queryKey: PANELS_QUERY_KEY });
      onCreated({
        outputId: "fiestapanel",
        boardId: panel.board_id,
        name: panel.name,
        viewerPath: panel.short_code > 0 ? `/p/${panel.short_code}` : `/panel/${panel.id}`,
      });
    },
  });

  const busy = useRef(false);
  useImperativeHandle(ref, () => ({
    save: async () => {
      if (done) return done;
      if (busy.current || !name.trim() || !sizeValid) return null;
      busy.current = true;
      try {
        const panel = await create.mutateAsync();
        return {
          outputId: "fiestapanel",
          boardId: panel.board_id,
          name: panel.name,
          viewerPath: panel.short_code > 0 ? `/p/${panel.short_code}` : `/panel/${panel.id}`,
        };
      } catch {
        return null;
      } finally {
        busy.current = false;
      }
    },
  }));

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
              <TextLink
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-sm break-all underline underline-offset-4"
              >
                {url}
              </TextLink>
              <Text size="xs" tone="muted">
                {t("viewerHint")}
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
        <Select
          value={inches}
          onValueChange={(value) => {
            if (value) setInches(value);
          }}
          disabled={create.isPending}
        >
          <SelectTrigger id="wizard-panel-size" aria-describedby="wizard-panel-size-help">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[32, 43, 55, 65, 75].map((value) => (
              <SelectItem key={value} value={String(value)}>
                {t("autoSize", { inches: value })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Text size="xs" tone="muted" id="wizard-panel-size-help">
          {t("autoSizeHint")}
        </Text>
      </Grid>
      <Text weight="medium">{t("howConnects")}</Text>
      <Stack gap="3">
        <Flex gap="3" className="rounded-lg bg-muted p-3">
          <IconTile tone="muted">
            <Tv aria-hidden="true" />
          </IconTile>
          <Stack gap="1">
            <Text size="sm" weight="medium">
              {t("tvApp")}
            </Text>
            <Text size="xs" tone="muted">
              {t("tvAppHint")}{" "}
              <TextLink href={appUrl("/activate")}>
                {new URL(appUrl("/activate"), window.location.origin).toString()}
              </TextLink>
            </Text>
          </Stack>
        </Flex>
        <Flex gap="3" className="rounded-lg bg-muted p-3">
          <IconTile tone="muted">
            <Globe aria-hidden="true" />
          </IconTile>
          <Stack gap="1">
            <Text size="sm" weight="medium">
              {t("browser")}
            </Text>
            <Text size="xs" tone="muted">
              {t("browserHint")}
            </Text>
          </Stack>
        </Flex>
        <Text size="sm" role="status" className="rounded-lg border p-3">
          {t("waiting")}
        </Text>
      </Stack>
      {create.isError && (
        <Alert variant="destructive" data-testid="wizard-panel-error">
          <XCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>{t("failed")}</AlertTitle>
          <AlertDescription>{create.error.message}</AlertDescription>
        </Alert>
      )}
      {!hideCreate && (
        <Button
          type="button"
          className="w-full"
          disabled={create.isPending || !name.trim() || !sizeValid}
          onClick={() => create.mutate()}
        >
          {create.isPending ? t("creating") : (createLabel ?? t("create"))}
        </Button>
      )}
    </Stack>
  );
}

"use client";

import {
  Button,
  CopyButton,
  Flex,
  Grid,
  Input,
  Label,
  PageCard,
  PageSection,
  SegmentedControl,
  SegmentedControlItem,
  Stack,
  Switch,
  Text,
} from "@fiestaboard/ui";
import type { ReactNode } from "react";
import { useState } from "react";
import { toast } from "sonner";

import { PanelTvPreview } from "@/components/panel/panel-tv-preview";
import { TimePicker } from "@/components/ui/time-picker";
import { useTranslations } from "@/i18n/translations";
import type { Panel, PanelRenderStyle, PanelUpdateRequest } from "@/lib/api";

interface InlinePanelSettingsProps {
  panel: Panel;
  url: string;
  pending: boolean;
  error: Error | null;
  preview?: ReactNode;
  nameField?: ReactNode;
  renderStyles: ReadonlyArray<{ value: PanelRenderStyle; labelKey: "renderStyleSplitFlap" | "renderStyleLed" }>;
  onPatch: (changes: PanelUpdateRequest) => void;
  onAdvanced: () => void;
  onDelete: () => void;
}

/** Selected-display form: discrete choices save immediately, text fields on blur. */
export function InlinePanelSettings({
  panel,
  url,
  pending,
  error,
  preview,
  nameField,
  renderStyles,
  onPatch,
  onAdvanced,
  onDelete,
}: InlinePanelSettingsProps) {
  const t = useTranslations("fiestaPanels");
  const tCommon = useTranslations("common");
  const [custom, setCustom] = useState(false);
  const [invalidName, setInvalidName] = useState(false);
  const [invalidSize, setInvalidSize] = useState(false);
  const presets = [43, 55, 65, 75];
  const sizeIsCustom = custom || !presets.includes(panel.screen_diagonal_inches);
  const validSize = (value: number) => Number.isFinite(value) && value >= 3 && value <= 200;

  return (
    <Grid cols="1" gap="5" className="lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:items-start">
      <Stack gap="5">
        <PageCard>
          <PageSection title={t("displaySettings")}>
            {nameField ?? (
              <Stack gap="2">
                <Label htmlFor={`inline-name-${panel.id}`}>{t("panelName")}</Label>
                <Input
                  key={panel.name}
                  id={`inline-name-${panel.id}`}
                  defaultValue={panel.name}
                  required
                  disabled={pending}
                  aria-invalid={invalidName}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                  onBlur={(event) => {
                    const name = event.currentTarget.value.trim();
                    setInvalidName(!name);
                    if (name && name !== panel.name) onPatch({ name });
                  }}
                />
              </Stack>
            )}
            <Flex align="center" justify="between" gap="3" className="mt-4">
              <Text size="sm">{tCommon("type")}</Text>
              <Text size="sm" tone="muted">
                {t("title")}
              </Text>
            </Flex>
          </PageSection>
        </PageCard>
        <PageCard>
          <PageSection title={t("title")} contentClassName="space-y-5">
            <Stack gap="2">
              <Label htmlFor={`inline-url-${panel.id}`}>{t("panelUrl")}</Label>
              <Flex align="center" gap="2">
                <Input id={`inline-url-${panel.id}`} value={url} readOnly className="min-w-0" />
                <CopyButton
                  value={url}
                  size="icon-sm"
                  variant="ghost"
                  labels={{ copy: t("copyUrl"), copied: t("urlCopied") }}
                  onCopyError={() => toast.error(t("urlCopyFailed"))}
                />
              </Flex>
              <Text size="xs" tone="muted">
                {t("openOnTv")}
              </Text>
            </Stack>
            <Stack gap="2">
              <Label>{t("screenSize")}</Label>
              <SegmentedControl
                aria-label={t("screenSize")}
                value={sizeIsCustom ? "custom" : String(panel.screen_diagonal_inches)}
                disabled={pending}
                className="w-fit max-w-full flex-wrap"
                onValueChange={(value) => {
                  if (value === "custom") setCustom(true);
                  else {
                    setCustom(false);
                    onPatch({ screen_diagonal_inches: Number(value) });
                  }
                }}
              >
                {presets.map((size) => (
                  <SegmentedControlItem key={size} value={String(size)} className="min-h-11">
                    {size}&quot;
                  </SegmentedControlItem>
                ))}
                <SegmentedControlItem value="custom" className="min-h-11">
                  {t("screenSizeCustom")}
                </SegmentedControlItem>
              </SegmentedControl>
              {sizeIsCustom && (
                <Input
                  key={panel.screen_diagonal_inches}
                  type="number"
                  min={3}
                  max={200}
                  step={0.5}
                  aria-label={t("screenSizeCustom")}
                  defaultValue={panel.screen_diagonal_inches}
                  disabled={pending}
                  aria-invalid={invalidSize}
                  className="max-w-32"
                  onKeyDown={(event) => {
                    if (event.key === "Enter") event.currentTarget.blur();
                  }}
                  onBlur={(event) => {
                    const size = Number(event.currentTarget.value);
                    setInvalidSize(!validSize(size));
                    if (validSize(size) && size !== panel.screen_diagonal_inches)
                      onPatch({ screen_diagonal_inches: size });
                  }}
                />
              )}
            </Stack>
            <Stack gap="2">
              <Label>{t("renderStyle")}</Label>
              <SegmentedControl
                aria-label={t("renderStyle")}
                value={panel.render_style ?? "split_flap"}
                disabled={pending}
                className="w-fit max-w-full flex-wrap"
                onValueChange={(value) => {
                  if (renderStyles.some((style) => style.value === value))
                    onPatch({ render_style: value as PanelRenderStyle });
                }}
              >
                {renderStyles.map((style) => (
                  <SegmentedControlItem key={style.value} value={style.value} className="min-h-11">
                    {t(style.labelKey)}
                  </SegmentedControlItem>
                ))}
              </SegmentedControl>
            </Stack>
            <Flex align="center" justify="between" gap="3">
              <Label htmlFor={`inline-dim-${panel.id}`}>{t("autoDim")}</Label>
              <Switch
                id={`inline-dim-${panel.id}`}
                checked={panel.auto_dim.enabled}
                disabled={pending}
                onCheckedChange={(enabled) => onPatch({ auto_dim: { ...panel.auto_dim, enabled } })}
              />
            </Flex>
            {panel.auto_dim.enabled && (
              <Grid cols="1" sm="2" gap="3">
                <Stack gap="2">
                  <Label htmlFor={`inline-dim-start-${panel.id}`}>{t("autoDimStart")}</Label>
                  <TimePicker
                    id={`inline-dim-start-${panel.id}`}
                    value={panel.auto_dim.start}
                    disabled={pending}
                    onChange={(start) => onPatch({ auto_dim: { ...panel.auto_dim, start } })}
                  />
                </Stack>
                <Stack gap="2">
                  <Label htmlFor={`inline-dim-end-${panel.id}`}>{t("autoDimEnd")}</Label>
                  <TimePicker
                    id={`inline-dim-end-${panel.id}`}
                    value={panel.auto_dim.end}
                    disabled={pending}
                    onChange={(end) => onPatch({ auto_dim: { ...panel.auto_dim, end } })}
                  />
                </Stack>
              </Grid>
            )}
            <Flex align="center" justify="between" gap="3">
              <Label htmlFor={`inline-output-${panel.id}`}>{t("displayOutput")}</Label>
              <Switch
                id={`inline-output-${panel.id}`}
                checked={panel.is_display}
                disabled={pending}
                onCheckedChange={(is_display) => onPatch({ is_display })}
              />
            </Flex>
            <Button variant="outline" onClick={onAdvanced} disabled={pending}>
              {t("advancedSettings")}
            </Button>
            {pending && (
              <Text role="status" size="sm">
                {tCommon("saving")}
              </Text>
            )}
            {error && (
              <Text role="alert" size="sm" tone="destructive">
                {error.message}
              </Text>
            )}
          </PageSection>
        </PageCard>
      </Stack>
      <Stack gap="5">
        <PageCard>
          <PageSection title={t("previewAt", { inches: panel.screen_diagonal_inches })}>
            {preview ?? <PanelTvPreview panelId={panel.id} />}
          </PageSection>
        </PageCard>
        <PageCard>
          <PageSection title={t("removeDisplayTitle")} description={t("deleteConfirmBody", { name: panel.name })}>
            <Button variant="destructive" onClick={onDelete} disabled={pending} className="w-full sm:w-auto min-h-11">
              {t("removeDisplay")}
            </Button>
          </PageSection>
        </PageCard>
      </Stack>
    </Grid>
  );
}

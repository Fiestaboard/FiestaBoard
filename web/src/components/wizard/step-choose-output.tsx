"use client";

/**
 * The setup wizard's first step (plan D18): what will FiestaBoard show on?
 *
 * One card per output `GET /outputs/available` offers — installed ones
 * (Vestaboard, FiestaPanel, any output plugin), outputs bundled with the
 * image, and output plugins from the registry — plus a first-class
 * way out: "I'll add a display later" ends the wizard as skipped, and the app
 * opens with previews only.
 */
import { Alert, AlertDescription, Button, Flex, Stack, Text, ToggleCard, ToggleCardGroup } from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { ArrowRight } from "lucide-react";
import { useEffect } from "react";

import { CatalogAvailability, DisplayCatalogBrowser, useDisplayCatalog } from "@/components/displays/display-catalog";
import { OutputIcon } from "@/components/settings/output-boards";
import { useTranslations } from "@/i18n/translations";
import type { AvailableOutput } from "@/lib/api";

export const AVAILABLE_OUTPUTS_QUERY_KEY = ["outputs", "available"] as const;

interface StepChooseOutputProps {
  /** The chosen output's id, if any. */
  value: string | null;
  onChange: (output: AvailableOutput) => void;
  /** "I'll add a display later" (the wizard's way out); none when absent. */
  onSkip?: () => void;
  onValidChange: (valid: boolean) => void;
  /** Which outputs to offer (all by default). Displays → Add a display keeps registry ones for "Find more displays". */
  include?: (output: AvailableOutput) => boolean;
  /** The compact Add display dialog uses a single list at every width. */
  columns?: "1" | "2";
}

export function StepChooseOutput({
  value,
  onChange,
  onSkip,
  onValidChange,
  include,
  columns = "2",
}: StepChooseOutputProps) {
  const t = useTranslations("wizard.chooseOutput");
  const { data, isLoading, isError, refetch, isFetching } = useDisplayCatalog();
  const outputs = include ? (data?.outputs ?? []).filter(include) : (data?.outputs ?? []);
  const chosen = outputs.find((output) => output.id === value) ?? null;

  useEffect(() => {
    onValidChange(chosen !== null);
  }, [chosen, onValidChange]);

  // BB-C-14: one short line under each name (Figma 325:34531, 335:59549), so
  // the choices and Continue fit a phone screen. Built-ins have their own
  // summary; a plugin's description is clamped, and a model line that only
  // repeats the name is dropped.
  const summary = (output: AvailableOutput) =>
    output.builtin && (output.id === "vestaboard" || output.id === "fiestapanel") ? (
      t(output.id === "vestaboard" ? "summaryVestaboard" : "summaryFiestapanel")
    ) : (
      // The card's description style (text-xs, muted); only the length is clamped.
      <Text as="span" size="xs" tone="muted" className="line-clamp-2">
        {output.description}
      </Text>
    );
  const modelLine = (output: AvailableOutput) => {
    if (output.builtin) return null;
    const parts = [output.display?.manufacturer, ...(output.display?.models ?? []).slice(0, 3)].filter(
      (part): part is string => !!part && !output.name.includes(part),
    );
    return parts.length ? parts.join(" · ") : null;
  };

  // 07d draws five directly visible choices. Larger plugin catalogs keep
  // the existing searchable, categorized and paginated discovery workflow.
  const choices = (shown: AvailableOutput[]) => (
    <ToggleCardGroup
      columns={columns}
      className={columns === "1" ? "p-0.5 grid-cols-1" : "p-0.5 sm:grid-cols-1 md:grid-cols-2"}
      value={value ?? ""}
      onValueChange={(id) => {
        const output = outputs.find((o) => o.id === id);
        if (output) onChange(output);
      }}
      aria-label={t("optionsLabel")}
      data-testid="wizard-output-choices"
    >
      {shown.map((output) => (
        <ToggleCard
          key={output.id}
          value={output.id}
          icon={<OutputIcon name={output.icon} className="h-5 w-5" />}
          title={output.name}
          description={summary(output)}
          data-testid={`wizard-output-${output.id}`}
        >
          {modelLine(output) ? (
            <Text as="span" size="xs" tone="muted" className="block">
              {modelLine(output)}
            </Text>
          ) : null}
          {/* Spans: the card is a <button>, which may hold phrasing content only. */}
          {output.needs_network ? (
            <Text as="span" size="xs" tone="muted" className="block">
              {t("downloads")}
            </Text>
          ) : null}
        </ToggleCard>
      ))}
    </ToggleCardGroup>
  );

  return (
    <Stack gap="4">
      {!isLoading && !isError && outputs.length === 0 && <Text role="status">{t("empty")}</Text>}
      {isLoading && (
        <Flex align="center" gap="2" role="status">
          <Spinner label={null} />
          <Text as="span" tone="muted">
            {t("loading")}
          </Text>
        </Flex>
      )}

      {isError && (
        <Alert variant="destructive">
          <AlertDescription>
            <Stack gap="2">
              <Text size="sm">{t("loadFailed")}</Text>
              <Flex>
                <Button type="button" size="sm" variant="outline" onClick={() => void refetch()} disabled={isFetching}>
                  {t("retry")}
                </Button>
              </Flex>
            </Stack>
          </AlertDescription>
        </Alert>
      )}

      <CatalogAvailability
        unavailable={data?.registry_status === "unavailable"}
        retry={() => void refetch()}
        busy={isFetching}
      />
      {outputs.length > 0 &&
        (outputs.length > 5 ? (
          <DisplayCatalogBrowser outputs={outputs} selectedId={value}>
            {choices}
          </DisplayCatalogBrowser>
        ) : (
          choices(outputs)
        ))}

      {onSkip && (
        <Stack gap="1" className="border-t pt-4">
          <Flex>
            <Button type="button" variant="ghost" onClick={onSkip} data-testid="wizard-skip-display">
              {t("skipTitle")}
              <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
            </Button>
          </Flex>
          <Text size="xs" tone="muted">
            {t("skipDescription")}
          </Text>
        </Stack>
      )}
    </Stack>
  );
}

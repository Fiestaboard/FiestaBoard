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
import { BringYourOwnDisplay } from "@/components/displays/display-marketplace";
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
}

export function StepChooseOutput({ value, onChange, onSkip, onValidChange, include }: StepChooseOutputProps) {
  const t = useTranslations("wizard.chooseOutput");
  const { data, isLoading, isError, refetch, isFetching } = useDisplayCatalog();
  const outputs = include ? (data?.outputs ?? []).filter(include) : (data?.outputs ?? []);
  const chosen = outputs.find((output) => output.id === value) ?? null;

  useEffect(() => {
    onValidChange(chosen !== null);
  }, [chosen, onValidChange]);

  return (
    <Stack gap="6">
      {onSkip && (
        <Stack gap="2" className="rounded-lg bg-muted/50 p-4">
          <Text weight="medium">{t("introTitle")}</Text>
          <Text size="sm" tone="muted">
            {t("introDescription")}
          </Text>
          <Text size="sm" tone="muted">
            {t("displayHint")}
          </Text>
        </Stack>
      )}
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
      {outputs.length > 0 && (
        <DisplayCatalogBrowser outputs={outputs} selectedId={value}>
          {(shown) => (
            <ToggleCardGroup
              columns="1"
              className="max-h-96 overflow-y-auto p-1"
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
                  description={output.description}
                  data-testid={`wizard-output-${output.id}`}
                >
                  {output.display?.manufacturer || output.display?.models?.length ? (
                    <Text as="span" size="xs" tone="muted" className="block">
                      {[output.display?.manufacturer, ...(output.display?.models ?? []).slice(0, 3)]
                        .filter(Boolean)
                        .join(" · ")}
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
          )}
        </DisplayCatalogBrowser>
      )}

      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm font-medium">{t("customPlugin")}</summary>
        <Stack gap="3" className="mt-3">
          <BringYourOwnDisplay
            onAdd={(output) => {
              onChange({
                ...output,
                description: "",
                icon: null,
                source: "installed",
                installed: true,
                builtin: false,
                beta_gated: false,
                available: true,
                needs_network: false,
                output_api: null,
              });
              void refetch();
            }}
          />
        </Stack>
      </details>
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

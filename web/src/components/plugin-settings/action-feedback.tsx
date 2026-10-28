"use client";

/**
 * An action's answer, shown where the action was run: its status, message,
 * guidance, the settings it filled and a size it detected — or why the
 * request itself failed. The board settings screen puts one under each
 * action button; a device picker puts its own under the address field.
 */
import { Alert, AlertDescription, AlertTitle, Button, Flex, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import type { ActionGeometry, ActionResult, OutputActionDescriptor } from "@/lib/api";

/** What one run of an action left behind. */
export interface ActionFeedbackEntry {
  action: OutputActionDescriptor;
  /** The answer, or `null` when the request itself failed. */
  result: ActionResult | null;
  /** Why the request failed (network, 4xx, 5xx). */
  error: string | null;
  /** Titles of the settings the result filled. */
  filled: string[];
  /** Whether the result's geometry was applied at once (`auto_apply`). */
  applied: boolean;
}

export function ActionFeedback({
  entry,
  onGeometry,
  showDevices = true,
}: {
  entry: ActionFeedbackEntry;
  onGeometry?: (geometry: ActionGeometry) => void;
  /** List the devices the result found (a device picker shows them as its pick-list instead). */
  showDevices?: boolean;
}) {
  const t = useTranslations("boardSettingsScreen");
  const { result, error, filled, applied } = entry;

  if (result === null) {
    return (
      <Alert variant="destructive" data-testid="action-failure" data-action={entry.action.id}>
        <XCircle className="h-4 w-4" aria-hidden="true" />
        <AlertTitle>{t("resultError")}</AlertTitle>
        <AlertDescription>{error || t("actionFailed")}</AlertDescription>
      </Alert>
    );
  }

  const variant = result.status === "ok" ? "success" : result.status === "warning" ? "warning" : "destructive";
  const Icon = result.status === "ok" ? CheckCircle2 : result.status === "warning" ? AlertTriangle : XCircle;
  const title =
    result.status === "ok" ? t("resultOk") : result.status === "warning" ? t("resultWarning") : t("resultError");

  return (
    <Alert variant={variant} data-testid="action-result" data-status={result.status} data-action={entry.action.id}>
      <Icon className="h-4 w-4" aria-hidden="true" />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <Stack gap="2">
          {result.message && <Text size="sm">{result.message}</Text>}
          {result.guidance.length > 0 && (
            <Stack gap="1">
              <Text size="xs" weight="medium">
                {t("guidanceLabel")}
              </Text>
              <List>
                {result.guidance.map((line) => (
                  <ListItem key={line}>{line}</ListItem>
                ))}
              </List>
            </Stack>
          )}
          {filled.length > 0 && <Text size="xs">{t("fieldsFilled", { fields: filled.join(", ") })}</Text>}
          {result.geometry && (
            <Flex align="center" gap="2" wrap>
              <Text size="xs">
                {applied
                  ? t("geometryApplied", { rows: result.geometry.rows, cols: result.geometry.cols })
                  : t("geometryDetected", { rows: result.geometry.rows, cols: result.geometry.cols })}
              </Text>
              {onGeometry && !applied && (
                <Button type="button" size="sm" variant="outline" onClick={() => onGeometry(result.geometry!)}>
                  {t("applyGeometry")}
                </Button>
              )}
            </Flex>
          )}
          {showDevices && result.devices && result.devices.length === 0 && <Text size="xs">{t("noDevicesFound")}</Text>}
          {showDevices && result.devices && result.devices.length > 0 && (
            <List>
              {result.devices.map((device) => (
                <ListItem key={`${device.ip}:${device.port}`}>
                  {device.hostname || device.label || device.ip} ({device.ip}:{device.port})
                </ListItem>
              ))}
            </List>
          )}
        </Stack>
      </AlertDescription>
    </Alert>
  );
}

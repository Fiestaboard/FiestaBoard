// "Missing values (H6)" (07c 307:46094 / 316:97494) and the Sample / render-at
// notes under the preview board.

"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  type DataSource,
  Flex,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { Sigma } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import type { FormulaDiagnostic, PreviewSource } from "@/lib/api/formula-debug";
import { appUrl } from "@/lib/base-path";
import { fallbackTip, type MissingEntry, missingReport } from "@/lib/formula-ide/data-source";

/**
 * Kit `AlertTitle` is always an `<h5>`. In the editor it sits under the
 * page's h2 (and beside the h3 card titles), so announce it as level 3 to
 * keep the heading outline unbroken (axe heading-order). FiestaUI gap:
 * AlertTitle has no heading-level prop.
 */
const MISSING_TITLE_LEVEL = 3;

export interface MissingValuesCardProps {
  mode: DataSource;
  /** Localized render-at time, or null for now. */
  atLabel: string | null;
  template: readonly string[];
  roots: readonly string[];
  /** Referenced plugins with no example values (Sample keeps their hub data). */
  unsampled: readonly string[];
  formulas: readonly FormulaDiagnostic[];
  sources: Record<string, PreviewSource> | null;
  loading: boolean;
  failed: boolean;
  /** Wraps `{{path}}` on a line in DEFAULT(path, "--"). */
  onAddFallback: (line: number, path: string) => void;
}

function useReason() {
  const t = useTranslations("formulaIde");
  return (entry: MissingEntry): string => {
    const shows: string[] = [];
    if (entry.variableLines.length) shows.push(t("missingShowsUnknown", { lines: entry.variableLines.join(", ") }));
    if (entry.formulaLines.length) shows.push(t("missingShowsRef", { lines: entry.formulaLines.join(", ") }));
    if (entry.fallbackLines.length) shows.push(t("missingShowsFallback", { lines: entry.fallbackLines.join(", ") }));
    const why =
      entry.state === "stale" && entry.updatedAt
        ? t("missingStale", {
            time: new Date(entry.updatedAt).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }),
          })
        : entry.state === "none"
          ? t("missingNone")
          : t("missingSimulated");
    return [why, ...shows].join(" → ");
  };
}

export function MissingValuesCard({
  mode,
  atLabel,
  template,
  roots,
  unsampled,
  formulas,
  sources,
  loading,
  failed,
  onAddFallback,
}: MissingValuesCardProps) {
  const t = useTranslations("formulaIde");
  const reason = useReason();

  const atNote = atLabel ? (
    <Text size="xs" tone="muted" data-testid="render-at-note">
      {t("renderAtNote", { time: atLabel })}
    </Text>
  ) : null;

  if (mode === "live") return atNote;

  if (failed) {
    return (
      <Alert variant="destructive" data-testid="preview-context-error">
        <AlertDescription>{t("previewFailed")}</AlertDescription>
      </Alert>
    );
  }

  if (mode === "sample") {
    return (
      <Stack gap="1" data-testid="sample-note">
        <Text size="xs" tone="muted">
          {t("sampleNote")}
        </Text>
        {unsampled.length > 0 && (
          <Text size="xs" tone="muted">
            {t("sampleUnsampled", { plugins: unsampled.join(", ") })}
          </Text>
        )}
        {atNote}
      </Stack>
    );
  }

  if (loading) return <Skeleton className="h-24 w-full rounded-lg" />;

  const entries = missingReport({ template, roots, formulas, sources });
  if (entries.length === 0) {
    return (
      <Stack gap="1" data-testid="missing-values">
        <Alert variant="success">
          <AlertTitle aria-level={MISSING_TITLE_LEVEL}>{t("missingNothingTitle")}</AlertTitle>
          <AlertDescription>{t("missingNothingBody")}</AlertDescription>
        </Alert>
        {atNote}
      </Stack>
    );
  }

  const fixable = entries.find((entry) => entry.variableLines.length > 0 && entry.path !== entry.root);
  return (
    <Stack gap="2" data-testid="missing-values">
      <Alert variant="warning">
        <AlertTitle aria-level={MISSING_TITLE_LEVEL}>
          <Flex align="center" gap="2" wrap>
            <Badge variant="outline">{t("missingCount", { count: entries.length })}</Badge>
            {t("missingTitle")}
          </Flex>
        </AlertTitle>
        <AlertDescription>
          <Stack gap="1">
            {entries.map((entry) => (
              <Text key={entry.root} size="sm">
                <Text as="span" size="sm" weight="medium" className="font-mono">
                  {entry.path}
                </Text>
                {" — "}
                {reason(entry)}
              </Text>
            ))}
            {fixable && (
              <Text size="sm" className="font-mono">
                {t("missingTip", { formula: fallbackTip(fixable.path) })}
              </Text>
            )}
            <Flex gap="2" wrap className="pt-1">
              <Button asChild variant="outline" size="sm">
                <TextLink href={appUrl("/integrations")} className="text-foreground no-underline">
                  {t("openIntegrations")}
                </TextLink>
              </Button>
              {fixable && (
                <Button variant="ghost" size="sm" onClick={() => onAddFallback(fixable.variableLines[0], fixable.path)}>
                  <Sigma aria-hidden />
                  {t("addFallback", { line: fixable.variableLines[0] })}
                </Button>
              )}
            </Flex>
          </Stack>
        </AlertDescription>
      </Alert>
      <Text size="xs" tone="muted">
        {t("missingExplainer")}
      </Text>
      {atNote}
    </Stack>
  );
}

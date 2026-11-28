// "Missing values (H6)" (07c 307:46094 / 316:97494) under the preview board,
// and the one-line caption slot above it (UX-4-4) that carries the Sample,
// render-at and Inspect notes without moving anything.

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
import { openIdeProblems } from "@/lib/ide/open-problems";

/**
 * Kit `AlertTitle` is always an `<h5>`. In the editor it sits under the page
 * name, the editor's h1 (BB-E-23), so announce it as level 2 to keep the
 * heading outline unbroken (axe heading-order). FiestaUI gap: AlertTitle has
 * no heading-level prop.
 */
const MISSING_TITLE_LEVEL = 2;

export interface PreviewCaptionProps {
  /** Desktop: the slot keeps its line even when empty, so nothing under it moves. */
  reserved: boolean;
  inspecting: boolean;
  mode: DataSource;
  /** Localized render-at time, or null for now. */
  atLabel: string | null;
  /** Referenced plugins with no example values (Sample keeps their hub data). */
  unsampled: readonly string[];
}

/**
 * The fixed one-line caption under the board (UX-4-4): Inspect's hint, then
 * Sample's note, then the render-at note. One line with an ellipsis; the full
 * text is its tooltip.
 */
export function PreviewCaption({ reserved, inspecting, mode, atLabel, unsampled }: PreviewCaptionProps) {
  const t = useTranslations("formulaIde");
  const tv = useTranslations("previewView");
  const text = inspecting
    ? tv("inspectCaption")
    : mode === "sample"
      ? [t("sampleNote"), unsampled.length > 0 && t("sampleUnsampled", { plugins: unsampled.join(", ") })]
          .filter(Boolean)
          .join(" ")
      : atLabel
        ? t("renderAtNote", { time: atLabel })
        : "";
  if (!text && !reserved) return null;
  return (
    <Text
      size="xs"
      tone="muted"
      aria-live="polite"
      title={text || undefined}
      data-slot="preview-caption"
      data-testid={
        inspecting ? "inspect-hint" : mode === "sample" ? "sample-note" : atLabel ? "render-at-note" : undefined
      }
      className="block h-4 truncate leading-4"
    >
      {text}
    </Text>
  );
}

export interface MissingValuesCardProps {
  mode: DataSource;
  template: readonly string[];
  roots: readonly string[];
  /** Referenced integrations that are switched off (BB-E-12): named in Live, and as the reason in Missing. */
  offRoots?: readonly { root: string; name: string }[];
  formulas: readonly FormulaDiagnostic[];
  sources: Record<string, PreviewSource> | null;
  loading: boolean;
  failed: boolean;
  /** Wraps `{{path}}` on a line in DEFAULT(path, "--"). */
  onAddFallback: (line: number, path: string) => void;
}

function useReason(offRoots: readonly { root: string; name: string }[]) {
  const t = useTranslations("formulaIde");
  return (entry: MissingEntry): string => {
    const off = offRoots.find((item) => item.root === entry.root);
    const shows: string[] = [];
    if (entry.variableLines.length) shows.push(t("missingShowsUnknown", { lines: entry.variableLines.join(", ") }));
    if (entry.formulaLines.length) shows.push(t("missingShowsRef", { lines: entry.formulaLines.join(", ") }));
    if (entry.fallbackLines.length) shows.push(t("missingShowsFallback", { lines: entry.fallbackLines.join(", ") }));
    const why = off
      ? t("missingOff", { plugin: off.name })
      : entry.state === "stale" && entry.updatedAt
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
  template,
  roots,
  offRoots = [],
  formulas,
  sources,
  loading,
  failed,
  onAddFallback,
}: MissingValuesCardProps) {
  const t = useTranslations("formulaIde");
  const tv = useTranslations("previewView");
  const reason = useReason(offRoots);

  // Live: an integration that is switched off prints ??? on the real board, so
  // the panel says which and why (Figma 307:46094, BB-E-12).
  const liveOff = mode === "live" && !failed && offRoots.length > 0;
  // Live says what it needs in the caption slot (UX-4-4).
  if (mode === "live" && !liveOff) return null;
  if (failed && !liveOff) {
    return (
      <Alert variant="destructive" data-testid="preview-context-error">
        <AlertDescription>{t("previewFailed")}</AlertDescription>
      </Alert>
    );
  }
  if (mode === "sample") return null;

  if (loading && !liveOff) return <Skeleton className="h-24 w-full rounded-lg" />;

  const entries = missingReport({
    template,
    roots: liveOff ? offRoots.map((item) => item.root) : roots,
    formulas,
    sources,
  });
  if (entries.length === 0) {
    // Nothing is missing, but a formula error still shows on the board: name
    // it as what it is, and send the user to Problems (UX-4-4).
    const broken = formulas.find((formula) => formula.error);
    if (broken) {
      return (
        <Stack gap="1" data-testid="missing-values">
          <Alert>
            <AlertTitle aria-level={MISSING_TITLE_LEVEL}>{tv("missingNoDataTitle")}</AlertTitle>
            <AlertDescription>
              <Flex align="center" gap="2" wrap>
                <Text size="sm">{tv("missingFormulaError", { error: broken.error!, line: broken.line })}</Text>
                <Button variant="link" size="sm" className="h-auto px-0" onClick={openIdeProblems}>
                  {tv("seeProblems")}
                </Button>
              </Flex>
            </AlertDescription>
          </Alert>
        </Stack>
      );
    }
    return (
      <Stack gap="1" data-testid="missing-values">
        <Alert variant="success">
          <AlertTitle aria-level={MISSING_TITLE_LEVEL}>{t("missingNothingTitle")}</AlertTitle>
          <AlertDescription>{t("missingNothingBody")}</AlertDescription>
        </Alert>
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
    </Stack>
  );
}

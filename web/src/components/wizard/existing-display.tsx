"use client";

import { Alert, AlertDescription, AlertTitle, Button, Stack, ToggleCard, ToggleCardGroup } from "@fiestaboard/ui";
import { Info } from "lucide-react";
import { useEffect, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api, type ExistingBoardMatch, type ExistingBoardQuery } from "@/lib/api";

/** No API keys in query caches, URLs or logs. H19 owns host normalization,
 * port matching and constant-time comparison against masked saved secrets. */
export function existingDisplayQuery(
  output: string,
  config: Record<string, unknown>,
  excludeBoardId?: string,
): ExistingBoardQuery | null {
  const query: ExistingBoardQuery = { output, ...(excludeBoardId ? { exclude_board_id: excludeBoardId } : {}) };
  for (const key of ["host", "cloud_key", "note_array_token"] as const) {
    const value = config[key];
    if (typeof value === "string" && value.trim() && value !== "***") query[key] = value;
  }
  if (!query.host && !query.cloud_key && !query.note_array_token) return null;
  if (typeof config.port === "number" && Number.isInteger(config.port)) query.port = config.port;
  return query;
}

export function useExistingDisplay(query: ExistingBoardQuery | null) {
  const signature = query ? JSON.stringify(query) : null;
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${attempt}:${signature}`;
  const [response, setResponse] = useState<{
    signature: string;
    existing: ExistingBoardMatch[];
    error: string | null;
  } | null>(null);
  useEffect(() => {
    if (!signature) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void api
        .checkExistingBoards(JSON.parse(signature) as ExistingBoardQuery)
        .then(({ existing }) => {
          if (active) setResponse({ signature: requestKey, existing, error: null });
        })
        .catch((error: unknown) => {
          if (active)
            setResponse({
              signature: requestKey,
              existing: [],
              error: error instanceof Error ? error.message : String(error),
            });
        });
    }, 150);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [signature, requestKey]);
  const current = response?.signature === requestKey ? response : null;
  return {
    existing: current?.existing ?? [],
    pending: !!signature && !current,
    error: current?.error ?? null,
    retry: () => setAttempt((value) => value + 1),
  };
}

export function ExistingDisplayChoice({
  match,
  host,
  choice,
  onChange,
  output,
}: {
  match: ExistingBoardMatch;
  host: string;
  choice: string;
  onChange: (choice: string) => void;
  output: string;
}) {
  const t = useTranslations("wizard.connection");
  return (
    <Stack gap="3">
      <Alert variant="info">
        <Info aria-hidden="true" />
        <AlertTitle>{t("knownTitle")}</AlertTitle>
        <AlertDescription>{t("knownDescription", { name: match.name, host })}</AlertDescription>
      </Alert>
      <ToggleCardGroup value={choice} onValueChange={onChange} columns="2" aria-label={t("knownTitle")}>
        <ToggleCard value="keep" title={t("keep", { name: match.name })} description={t("keepHint")} />
        <ToggleCard
          value="update"
          title={t("update")}
          description={t("updateHint")}
          disabled={match.output !== output}
        />
      </ToggleCardGroup>
    </Stack>
  );
}

export function ExistingDisplayError({ error, retry }: { error: string; retry: () => void }) {
  const t = useTranslations("wizard.chooseOutput");
  return (
    <Alert variant="destructive">
      <AlertDescription>
        <Stack gap="2">
          {error}
          <Button variant="outline" onClick={retry}>
            {t("retry")}
          </Button>
        </Stack>
      </AlertDescription>
    </Alert>
  );
}

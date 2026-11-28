"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type TemplateValidationTarget, validateTemplateAt } from "@/lib/api/template-validation";
import { type LineOverflow, lineOverflows } from "@/lib/complex-editing";

/**
 * H4: which template lines the board will cut, measured by the hub at the
 * board's real width (`POST /templates/validate` with the editor's geometry
 * and board). Callers pass the debounced template so typing does not fire a
 * request per keystroke. A failed check shows nothing rather than a guess.
 */
/** How long a first paint waits for the first check before it shows without it. */
const SETTLE_CAP_MS = 1500;

export function useLineOverflow(target: TemplateValidationTarget, cols: number, enabled: boolean) {
  // A slow hub must never hold the editor back for long.
  const [capped, setCapped] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setCapped(true), SETTLE_CAP_MS);
    return () => clearTimeout(id);
  }, []);
  const hasContent = target.template.some((line) => line.trim().length > 0);
  const query = useQuery({
    queryKey: ["template-validate-at", target],
    queryFn: ({ signal }) => validateTemplateAt(target, signal),
    enabled: enabled && hasContent,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
  const overflows: LineOverflow[] = enabled && hasContent && !query.isError ? lineOverflows(query.data, cols) : [];
  return {
    overflows,
    checkedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
    /** The first check has answered (or there is nothing to check): the H4 card won't appear later on its own. */
    settled: capped || !enabled || !hasContent || !query.isPending,
  };
}

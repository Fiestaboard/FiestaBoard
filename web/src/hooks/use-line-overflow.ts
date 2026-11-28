"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { type TemplateValidationTarget, validateTemplateAt } from "@/lib/api/template-validation";
import { type LineOverflow, lineOverflows, type RowsPastBoard,rowsPastBoard } from "@/lib/complex-editing";

/**
 * H4: which template lines the board will cut, measured by the hub at the
 * board's real width, and which run past its last row (`POST
 * /templates/validate` with the editor's geometry and board). Callers pass the debounced template so typing does not fire a
 * request per keystroke. A failed check shows nothing rather than a guess.
 */
export function useLineOverflow(target: TemplateValidationTarget, cols: number, enabled: boolean) {
  const hasContent = target.template.some((line) => line.trim().length > 0);
  const query = useQuery({
    queryKey: ["template-validate-at", target],
    queryFn: ({ signal }) => validateTemplateAt(target, signal),
    enabled: enabled && hasContent,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
    retry: false,
  });
  const checked = enabled && hasContent && !query.isError;
  const overflows: LineOverflow[] = checked ? lineOverflows(query.data, cols) : [];
  // Rows the board runs out of (a line past the last row, a wrap off its end): W-1.
  const pastBoard: RowsPastBoard[] = checked ? rowsPastBoard(query.data) : [];
  return {
    overflows,
    pastBoard,
    checkedAt: query.dataUpdatedAt ? new Date(query.dataUpdatedAt) : null,
  };
}

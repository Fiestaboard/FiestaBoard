"use client";

/**
 * Seasonal theming now lives in the design system — this shim keeps the
 * historic import path working. Prefer useActiveSeason() for new code.
 */
export { useActiveSeason, usePrideActive } from "@fiestaboard/ui";

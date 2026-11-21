import { SegmentedControl, SegmentedControlItem } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

export type LibraryViewMode = "grid" | "list";

/**
 * The Grid / List switch the Pages and Collections libraries share (Figma
 * 297:1824 `Segmented`: two text pills, SegmentedControl / Item md), so the
 * two libraries draw the same control (BB-FP-6).
 */
export function LibraryViewToggle({
  value,
  onValueChange,
}: {
  value: LibraryViewMode;
  onValueChange: (mode: LibraryViewMode) => void;
}) {
  const t = useTranslations("pages");
  return (
    <SegmentedControl
      aria-label={t("viewModeLabel")}
      value={value}
      onValueChange={(next) => {
        if (next === "grid" || next === "list") onValueChange(next);
      }}
    >
      <SegmentedControlItem value="grid">{t("gridView")}</SegmentedControlItem>
      <SegmentedControlItem value="list">{t("listView")}</SegmentedControlItem>
    </SegmentedControl>
  );
}

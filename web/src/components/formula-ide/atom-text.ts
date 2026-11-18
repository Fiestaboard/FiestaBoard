import type { AtomHintValue } from "@/lib/formula-ide/hints";

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** The FormulaAtom `value` text: "= 7:40 AM", "= 3 of 7 rows", or the bare error tag. */
export function atomValueText(value: AtomHintValue, t: Translate): string {
  if (value.kind === "error") return value.tag;
  if (value.kind === "rows") return t("atomRows", { shown: value.shown, wanted: value.wanted });
  return t("atomValue", { value: value.text });
}

/**
 * A searchable model picker: the models a provider lists (name and id), and
 * any id typed by hand.
 *
 * OpenRouter lists hundreds of models, so this filters as you type and
 * renders only the first matches (the Combobox's `maxVisible`, announced).
 * A typed id the list does not have is offered as its own row, so a model
 * the provider does not list, or a provider that cannot list any, still
 * works.
 */
import { Combobox, type ComboboxOption, defaultComboboxFilter } from "@fiestaboard/ui";
import { useCallback, useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
import type { AIModel } from "@/lib/api";

export interface ModelComboboxProps {
  /** The models to offer. */
  models: readonly AIModel[];
  /** The chosen id, or "" for none (an "add a model" field). */
  value: string;
  onValueChange: (id: string) => void;
  /** Ids not to offer (models already added). */
  exclude?: readonly string[];
  id?: string;
  "aria-label"?: string;
  "aria-describedby"?: string;
  disabled?: boolean;
  /** Keep the list inside the surrounding popup (a Popover) instead of the page body. */
  portal?: boolean;
  className?: string;
}

export function ModelCombobox({
  models,
  value,
  onValueChange,
  exclude,
  id,
  "aria-label": ariaLabel,
  "aria-describedby": ariaDescribedBy,
  disabled,
  portal,
  className,
}: ModelComboboxProps) {
  const t = useTranslations("modelCombobox");

  const options = useMemo<ComboboxOption[]>(() => {
    const excluded = new Set(exclude ?? []);
    const rows: ComboboxOption[] = [];
    const seen = new Set<string>();
    for (const model of models) {
      if (excluded.has(model.id) || seen.has(model.id)) continue;
      seen.add(model.id);
      const named = !!model.name && model.name !== model.id;
      rows.push({
        value: model.id,
        label: named ? model.name : model.id,
        meta: named ? model.id : undefined,
        keywords: [model.id],
      });
    }
    // The chosen id always has a row, so the field can show it.
    if (value && !seen.has(value)) rows.unshift({ value, label: value });
    return rows;
  }, [models, exclude, value]);

  const filter = useCallback(
    (all: readonly ComboboxOption[], query: string) => {
      const matches = defaultComboboxFilter(all, query);
      const typed = query.trim();
      if (!typed || all.some((option) => option.value === typed) || exclude?.includes(typed)) return matches;
      return [{ value: typed, label: typed, meta: t("typedId") }, ...matches];
    },
    [exclude, t],
  );

  return (
    <Combobox
      id={id}
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
      options={options}
      value={value}
      onValueChange={(next) => {
        if (next) onValueChange(next);
      }}
      filter={filter}
      disabled={disabled}
      portal={portal}
      className={className}
      labels={{
        placeholder: t("placeholder"),
        trigger: t("trigger"),
        list: t("list"),
        empty: t("empty"),
        showingFirst: (shown, total) => t("showingFirst", { shown, total }),
      }}
    />
  );
}

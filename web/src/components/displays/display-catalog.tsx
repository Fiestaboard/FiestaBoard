"use client";

import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Flex,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useId, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { api, type AvailableOutput } from "@/lib/api";

export const DISPLAY_CATALOG_QUERY_KEY = ["outputs", "catalog"] as const;
export function useDisplayCatalog() {
  return useQuery({ queryKey: DISPLAY_CATALOG_QUERY_KEY, queryFn: () => api.listOutputCatalog(), staleTime: 60_000 });
}

export function CatalogAvailability({
  unavailable,
  retry,
  busy,
}: {
  unavailable: boolean;
  retry: () => void;
  busy: boolean;
}) {
  const t = useTranslations("displays.catalog");
  if (!unavailable) return null;
  return (
    <Alert data-testid="catalog-unavailable">
      <AlertTitle>{t("unavailableTitle")}</AlertTitle>
      <AlertDescription>
        <Stack gap="2">
          <Text size="sm">{t("unavailableBody")}</Text>
          <Flex>
            <Button type="button" size="sm" variant="outline" onClick={retry} disabled={busy}>
              {t("retry")}
            </Button>
          </Flex>
        </Stack>
      </AlertDescription>
    </Alert>
  );
}

/** A category is discovery metadata, never a switch that chooses a setup implementation. */
export function DisplayCatalogBrowser({
  outputs,
  selectedId,
  children,
}: {
  outputs: AvailableOutput[];
  selectedId?: string | null;
  children: (outputs: AvailableOutput[]) => ReactNode;
}) {
  const t = useTranslations("displays.catalog");
  const id = useId();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(0);
  const categoryOf = (output: AvailableOutput) => output.display?.category?.trim() || t("other");
  const categories = [...new Set(outputs.map(categoryOf))].sort((a, b) => a.localeCompare(b));
  const words = search.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  const filtered = outputs.filter((output) => {
    const text = [
      output.id,
      output.name,
      output.description,
      categoryOf(output),
      output.display?.manufacturer,
      ...(output.display?.models ?? []),
      ...(output.display?.keywords ?? []),
    ]
      .join(" ")
      .toLocaleLowerCase();
    return (!category || categoryOf(output) === category) && words.every((word) => text.includes(word));
  });
  const pages = Math.max(1, Math.ceil(filtered.length / 12));
  const current = Math.min(page, pages - 1);
  const selected = outputs.find((output) => output.id === selectedId);
  const clear = () => {
    setSearch("");
    setCategory("");
    setPage(0);
  };
  return (
    <Stack gap="3">
      <Stack gap="2">
        <Label htmlFor={`${id}-search`}>{t("search")}</Label>
        <Input
          id={`${id}-search`}
          type="search"
          placeholder={t("searchPlaceholder")}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(0);
          }}
        />
        <Label htmlFor={`${id}-category`}>{t("category")}</Label>
        <Select
          value={category ? `category:${category}` : "all"}
          onValueChange={(value) => {
            setCategory(value?.startsWith("category:") ? value.slice(9) : "");
            setPage(0);
          }}
        >
          <SelectTrigger id={`${id}-category`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("all")}</SelectItem>
            {categories.map((item) => (
              <SelectItem key={item} value={`category:${item}`}>
                {item}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Stack>
      {selected && (
        <Text size="sm" weight="medium" className="rounded-md bg-muted p-3">
          {t("selected", { name: selected.name })}
        </Text>
      )}
      <Flex align="center" justify="between" gap="2">
        <Text size="sm" tone="muted" role="status" aria-live="polite">
          {t("count", { count: filtered.length })}
        </Text>
        {(search || category) && (
          <Button type="button" size="sm" variant="ghost" onClick={clear}>
            {t("clear")}
          </Button>
        )}
      </Flex>
      {filtered.length ? (
        children(filtered.slice(current * 12, current * 12 + 12))
      ) : (
        <Stack gap="1" className="rounded-lg border border-dashed p-4">
          <Text weight="medium">{t("emptyTitle")}</Text>
          <Text size="sm" tone="muted">
            {t("emptyBody")}
          </Text>
        </Stack>
      )}
      {pages > 1 && (
        <Flex align="center" justify="between" gap="2" aria-label={t("pagination")}>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            {t("previous")}
          </Button>
          <Text size="sm">{t("page", { current: current + 1, total: pages })}</Text>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={current === pages - 1}
            onClick={() => setPage(current + 1)}
          >
            {t("next")}
          </Button>
        </Flex>
      )}
    </Stack>
  );
}

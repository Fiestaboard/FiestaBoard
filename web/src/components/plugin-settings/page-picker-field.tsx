"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

interface PagePickerFieldProps {
  id: string;
  value: string;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}

// Radix Select doesn't accept empty-string item values, so the "None" option
// uses this sentinel and is translated back to "" when written to the form.
const NONE_VALUE = "__none__";

export function PagePickerField({ id, value, onChange, disabled }: PagePickerFieldProps) {
  const { data: pagesData, isLoading } = useQuery({
    queryKey: ["pages"],
    queryFn: api.getPages,
  });

  const pages = pagesData?.pages ?? [];
  const selectValue = value && value.length > 0 ? value : NONE_VALUE;

  return (
    <Select
      value={selectValue}
      onValueChange={(v) => onChange(v === NONE_VALUE ? "" : v)}
      disabled={disabled || isLoading}
      modal={false}
    >
      <SelectTrigger id={id}>
        <SelectValue placeholder={isLoading ? "Loading pages…" : "Choose a page…"} />
      </SelectTrigger>
      <SelectContent className="max-h-[300px] z-[120]">
        <SelectItem value={NONE_VALUE}>None (no override)</SelectItem>
        {pages.map((page) => (
          <SelectItem key={page.id} value={page.id}>
            {page.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

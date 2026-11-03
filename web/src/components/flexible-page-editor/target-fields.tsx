import { Checkbox, Label, Stack, Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import type { BoardInstance, PageCreate } from "@/lib/api";

export function TargetFields({
  targets,
  boards,
  onChange,
}: {
  targets: PageCreate["targets"];
  boards: BoardInstance[];
  onChange: (targets: NonNullable<PageCreate["targets"]>) => void;
}) {
  const t = useTranslations("flexibleEditor");
  const toggle = (field: "boards" | "technology", value: string, checked: boolean) => {
    const current = targets?.[field] ?? [];
    onChange({
      ...targets,
      [field]: checked ? [...new Set([...current, value])] : current.filter((item) => item !== value),
    });
  };
  const technologies = [
    ["led_matrix", t("technologyLed")],
    ["split_flap", t("technologyFlap")],
    ["screen", t("technologyScreen")],
  ];
  for (const value of targets?.technology ?? []) {
    if (!technologies.some(([id]) => id === value)) technologies.push([value, value]);
  }
  const choices = boards.map((board) => ({ id: board.id, name: board.name }));
  for (const id of targets?.boards ?? []) {
    if (!choices.some((board) => board.id === id)) choices.push({ id, name: t("unavailableDisplay", { id }) });
  }
  return (
    <details>
      <summary>{t("targets")}</summary>
      <Stack gap="3" className="pt-3">
        <Text className="text-sm">{t("targetsHelp")}</Text>
        <fieldset className="space-y-2">
          <legend>{t("technologies")}</legend>
          {technologies.map(([id, name]) => (
            <Label key={id} className="flex items-center gap-2">
              <Checkbox
                checked={targets?.technology?.includes(id) ?? false}
                onChange={(event) => toggle("technology", id, event.target.checked)}
              />
              {name}
            </Label>
          ))}
        </fieldset>
        <fieldset className="space-y-2">
          <legend>{t("displays")}</legend>
          {choices.map(({ id, name }) => (
            <Label key={id} className="flex items-center gap-2">
              <Checkbox
                checked={targets?.boards?.includes(id) ?? false}
                onChange={(event) => toggle("boards", id, event.target.checked)}
              />
              {name}
            </Label>
          ))}
        </fieldset>
      </Stack>
    </details>
  );
}

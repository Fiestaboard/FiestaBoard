import {
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Flex,
  Input,
  Label,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Stack,
  Text,
  Textarea,
} from "@fiestaboard/ui";
import { useId, useState } from "react";

import { useTranslations } from "@/i18n/translations";
/** Sample editing is local until the hub accepts the read-only dry run. */
export function ScheduleSampleValues({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const t = useTranslations("schedule.lookup");
  const id = useId();
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [draft, setDraft] = useState("");
  let values: Record<string, unknown> | null = null;
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed && !Array.isArray(parsed) && typeof parsed === "object") values = parsed as Record<string, unknown>;
  } catch {
    /* The advanced editor keeps invalid text for repair. */
  }
  return (
    <Stack gap="3">
      <Flex gap="2" align="center" wrap>
        <Text size="sm">{t("whatIf")}</Text>
        {Object.entries(values ?? {}).map(([variable, sample]) => (
          <Badge
            key={variable}
            variant="variable"
            onDismiss={() => {
              const next = { ...values };
              delete next[variable];
              onChange(JSON.stringify(next));
            }}
            dismissLabel={t("removeValue", { path: variable })}
          >
            {variable} = {typeof sample === "string" ? sample : JSON.stringify(sample)}
          </Badge>
        ))}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm">
              {t("addValue")}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80 max-w-[calc(100vw-2rem)]" align="start">
            <Stack gap="3">
              <Label htmlFor={`${id}-path`}>{t("samplePath")}</Label>
              <Input id={`${id}-path`} value={path} onChange={(event) => setPath(event.target.value)} />
              <Label htmlFor={`${id}-draft`}>{t("sampleValue")}</Label>
              <Input id={`${id}-draft`} value={draft} onChange={(event) => setDraft(event.target.value)} />
              <Button
                disabled={!path.trim() || !values}
                onClick={() => {
                  if (!values || !path.trim()) return;
                  let sample: unknown = draft;
                  try {
                    sample = JSON.parse(draft);
                  } catch {
                    /* Plain text remains text. */
                  }
                  onChange(JSON.stringify({ ...values, [path.trim()]: sample }));
                  setOpen(false);
                  setPath("");
                  setDraft("");
                }}
              >
                {t("confirmValue")}
              </Button>
            </Stack>
          </PopoverContent>
        </Popover>
      </Flex>
      <Collapsible>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm">
            {t("editValuesJson")}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <Stack gap="2">
            <Label htmlFor={`${id}-json`}>{t("values")}</Label>
            <Textarea id={`${id}-json`} value={value} onChange={(event) => onChange(event.target.value)} />
          </Stack>
        </CollapsibleContent>
      </Collapsible>
    </Stack>
  );
}

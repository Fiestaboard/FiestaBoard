"use client";

import { Flex, Text, Toggle, ToggleGroup } from "@fiestaboard/ui";
import { Sigma } from "lucide-react";
import type { Dispatch, ReactNode, SetStateAction } from "react";

import { useTranslations } from "@/i18n/translations";

import type { OpenFormulaState, WorkbenchTab } from "./use-formula-ide";

/** "Σ Formula · line 2" with the validation badge and the Code | Builder switch. */
export function WorkbenchHeader({
  line,
  tab,
  setOpen,
  status,
}: {
  line: number | null;
  tab: WorkbenchTab;
  setOpen: Dispatch<SetStateAction<OpenFormulaState | null>>;
  status?: ReactNode;
}) {
  const t = useTranslations("formulaIde");
  return (
    <Flex align="center" justify="between" gap="2" wrap>
      <Flex align="center" gap="2">
        <Sigma aria-hidden className="size-4 text-tag-formula" />
        <Text as="p" weight="semibold">
          {line != null ? t("formulaLine", { line }) : t("formulaNew")}
        </Text>
      </Flex>
      <Flex align="center" gap="2">
        {status}
        <ToggleGroup
          segmented
          aria-label={t("editorModeLabel")}
          value={[tab]}
          onValueChange={(value) => {
            const next = value[0] as WorkbenchTab | undefined;
            if (next) setOpen((current) => (current ? { ...current, tab: next } : current));
          }}
        >
          <Toggle value="code" size="sm" data-testid="tab-code">
            {t("code")}
          </Toggle>
          <Toggle value="builder" size="sm" data-testid="tab-builder">
            {t("builder")}
          </Toggle>
        </ToggleGroup>
      </Flex>
    </Flex>
  );
}

"use client";

import { Flex, Tabs, TabsList, TabsTrigger, Text } from "@fiestaboard/ui";
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
        {/* Figma 111:30911: a Tabs list, the active trigger on the background with shadow-sm (BB-FP-15). */}
        <Tabs
          value={tab}
          onValueChange={(value) => {
            const next = value as WorkbenchTab;
            setOpen((current) => (current ? { ...current, tab: next } : current));
          }}
        >
          <TabsList aria-label={t("editorModeLabel")}>
            <TabsTrigger value="code" data-testid="tab-code">
              {t("code")}
            </TabsTrigger>
            <TabsTrigger value="builder" data-testid="tab-builder">
              {t("builder")}
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </Flex>
    </Flex>
  );
}

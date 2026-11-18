"use client";

import { InspectorRow, List, ListItem, Text } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { jumpToTemplateLine } from "@/lib/ide/jump-to-line";
import type { TemplateReference } from "@/lib/ide/references";

/**
 * Data and Logic tabs (not drawn on web; derived from native 04d): what the
 * template reads, one Inspector row per reference, each jumping to its line.
 */
export function IdeReferences({
  references,
  emptyLabel,
  mono,
}: {
  references: readonly TemplateReference[];
  emptyLabel: string;
  mono?: boolean;
}) {
  const t = useTranslations("creatorIde");
  if (!references.length) {
    return (
      <Text size="sm" tone="muted">
        {emptyLabel}
      </Text>
    );
  }
  return (
    <List gap="0" role="list">
      {references.map((reference, index) => (
        <ListItem key={`${reference.line}-${index}`}>
          <InspectorRow
            title={
              mono ? (
                <Text as="span" className="font-mono">
                  {reference.text}
                </Text>
              ) : (
                reference.text
              )
            }
            detail={t("rowN", { line: reference.line })}
            chevron
            onPress={() => jumpToTemplateLine(reference.line)}
          />
        </ListItem>
      ))}
    </List>
  );
}

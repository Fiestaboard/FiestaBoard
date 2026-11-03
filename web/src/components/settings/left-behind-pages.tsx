"use client";

/**
 * The pages a size change left behind on one display (design section 7:
 * "Size changes that leave pages behind are listed in board settings, not
 * only logged"). `PUT /settings/board` answers them as `left_behind_pages`;
 * each links to its editor with the page picker's reason.
 */
import { Alert, AlertDescription, AlertTitle, Box, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { AlertTriangle } from "lucide-react";
import { useId } from "react";

import Link from "@/components/smart-link";
import { useTranslations } from "@/i18n/translations";
import type { LeftBehindPage } from "@/lib/api";

export function LeftBehindPages({ pages }: { pages: LeftBehindPage[] | undefined }) {
  const t = useTranslations("displaySettings");
  const titleId = useId();
  if (!pages || pages.length === 0) return null;
  return (
    <Box as="section" aria-labelledby={titleId} data-testid="left-behind-pages">
      {/* It stays on the page after the save that produced it: polite, not an alarm. */}
      <Alert variant="warning" politeness="polite">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        <AlertTitle id={titleId}>{t("leftBehind.title")}</AlertTitle>
        <AlertDescription>
          <Stack gap="1">
            <Text size="xs" tone="muted">
              {t("leftBehind.description")}
            </Text>
            <List gap="0">
              {pages.map((page) => (
                <ListItem key={page.page_id} className="text-xs">
                  <Link href={`/pages/edit/${page.page_id}`} className="font-medium underline underline-offset-2">
                    {page.page_name}
                  </Link>
                  {" — "}
                  {page.reason}
                </ListItem>
              ))}
            </List>
          </Stack>
        </AlertDescription>
      </Alert>
    </Box>
  );
}

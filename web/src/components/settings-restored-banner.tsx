"use client";

import { Alert, AlertDescription, AlertTitle, Box, Button, Code, Flex, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History } from "lucide-react";

import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { isChromelessPath } from "@/lib/chromeless";

export const settingsRestoreNoticeKey = ["settingsRestoreNotice"] as const;

/**
 * App-wide banner shown after a rollback (output-plugins plan D8).
 *
 * When this build boots on a settings.json written by a newer FiestaBoard, it
 * restores its own pre-upgrade snapshot and moves the newer file aside. The
 * banner says so, and names the set-aside file, because anything changed
 * after the upgrade lives only there. It stays until dismissed, which only
 * forgets the notice — the file is kept.
 *
 * The notice is decided at boot, so it is read once per page load rather
 * than polled.
 */
export function SettingsRestoredBanner() {
  const t = useTranslations("settingsRestoreNotice");
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const chromeless = isChromelessPath(pathname);

  const { data } = useQuery({
    queryKey: settingsRestoreNoticeKey,
    queryFn: api.getSettingsRestoreNotice,
    enabled: !chromeless,
    staleTime: Infinity,
    retry: false,
  });

  const dismiss = useMutation({
    mutationFn: api.dismissSettingsRestoreNotice,
    onSuccess: (response) => queryClient.setQueryData(settingsRestoreNoticeKey, response),
  });

  const notice = data?.notice;
  if (chromeless || !notice) return null;

  return (
    <Box className="mb-6">
      <Alert
        variant="destructive"
        className="flex flex-col sm:flex-row sm:items-center sm:gap-4 [&>svg]:static [&>svg]:shrink-0 [&>svg+div]:translate-y-0 [&>svg~*]:pl-3"
        data-testid="settings-restored-banner"
      >
        <History className="h-4 w-4" aria-hidden="true" />
        <Box className="flex-1 min-w-0">
          <AlertTitle>{t("title")}</AlertTitle>
          <AlertDescription>
            {t("description")} <Code className="break-all text-xs">{notice.aside_path}</Code>
            {dismiss.isError ? (
              <Text as="span" role="alert">
                {" "}
                {t("dismissFailed")}
              </Text>
            ) : null}
          </AlertDescription>
        </Box>
        <Flex align="center" className="self-center shrink-0">
          <Button variant="outline" size="sm" onClick={() => dismiss.mutate()} disabled={dismiss.isPending}>
            {t("dismiss")}
          </Button>
        </Flex>
      </Alert>
    </Box>
  );
}

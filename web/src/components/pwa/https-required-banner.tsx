"use client";

import { StatusBanner, StatusBannerAction } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";
import { hubHost } from "@/lib/pwa/device-words";
import { isSecureOrigin } from "@/lib/pwa/environment";
import { HTTPS_HELP_URL } from "@/lib/pwa/https-help";

/**
 * "Requires HTTPS" (07e `329:49323`, the 07a HTTPS banner): on a plain-http
 * address, say once, with the fix, that install and offline can't work here.
 * Renders nothing on a secure origin.
 *
 * Page furniture, present from load, so it is not announced
 * (`politeness="off"`).
 */
export function HttpsRequiredBanner({ className }: { className?: string }) {
  const t = useTranslations("pwa.https");
  if (isSecureOrigin()) return null;
  return (
    <StatusBanner
      kind="https"
      politeness="off"
      className={className}
      title={t("title")}
      description={t("body", { host: hubHost() })}
      action={
        <StatusBannerAction variant="ghost" asChild>
          {/* eslint-disable-next-line react/forbid-elements -- single Slot child of Button asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling */}
          <a href={HTTPS_HELP_URL} target="_blank" rel="noreferrer">
            {t("help")}
          </a>
        </StatusBannerAction>
      }
    />
  );
}

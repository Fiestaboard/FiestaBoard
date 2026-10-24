"use client";

import { Button } from "@fiestaboard/ui";

import { SilenceNotice } from "@/components/silence-notice";
import { useTranslations } from "@/i18n/translations";

export interface LiveOutputSilenceStripProps {
  /** Live Output is switched on in the editor. */
  liveOutputEnabled: boolean;
  /** The last live render came back `silenced: true` — the board was left alone. */
  lastSilenced: boolean;
  /** The target board is inside its silence window right now. */
  silenceActive: boolean;
  /** The user chose "Send to board anyway": live renders carry `override_silence`. */
  overriding: boolean;
  /** When silence ends ("7:00 AM"); null when unknown. */
  until: string | null;
  onSendAnyway: () => void;
  onStopOverriding: () => void;
}

/**
 * The page editor's Live Output, told the truth about silence (#1943).
 *
 * While the target board is silenced, live renders keep updating the preview
 * but leave the board alone, and this strip says so with one explicit way to
 * write anyway. Once overriding, the permission and its revoke control stay
 * visible even when quiet-hours metadata is stale. It never raises a toast.
 */
export function LiveOutputSilenceStrip({
  liveOutputEnabled,
  lastSilenced,
  silenceActive,
  overriding,
  until,
  onSendAnyway,
  onStopOverriding,
}: LiveOutputSilenceStripProps) {
  const t = useTranslations("pageBuilder");
  if (!liveOutputEnabled) return null;

  if (overriding) {
    return (
      <SilenceNotice
        compact
        variant="warning"
        until={silenceActive ? until : null}
        title={silenceActive ? undefined : t("livePermissionTitle")}
        description={t("liveSilenceOverriding")}
        className="mt-2"
        data-testid="live-silence-overriding"
      >
        <Button variant="ghost" size="sm" onClick={onStopOverriding} data-testid="live-stop-override">
          {t("liveStopOverriding")}
        </Button>
      </SilenceNotice>
    );
  }

  if (lastSilenced && !overriding) {
    return (
      <SilenceNotice
        compact
        variant="info"
        until={until}
        description={t("liveSilencePreviewOnly")}
        className="mt-2"
        data-testid="live-silence"
      >
        <Button variant="outline" size="sm" onClick={onSendAnyway} data-testid="live-send-anyway">
          {t("liveSendAnyway")}
        </Button>
      </SilenceNotice>
    );
  }

  return null;
}

import {
  Box,
  CopyButton,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Textarea,
} from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

/**
 * A saved page's share string, read-only with a copy button. The library
 * card's "Export share string" opens it; the editor's Export draws the same
 * dialog with the same `pageBuilder.export*` copy.
 */
export function ExportPageDialog({
  shareString,
  onOpenChange,
}: {
  /** The share string to show; null keeps the dialog closed. */
  shareString: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useTranslations("pageBuilder");
  return (
    <Dialog open={shareString !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("exportDialogTitle")}</DialogTitle>
          <DialogDescription>{t("exportDialogDescription")}</DialogDescription>
        </DialogHeader>
        <Box className="relative">
          <Textarea
            readOnly
            value={shareString ?? ""}
            aria-label={t("exportStringAriaLabel")}
            className="h-28 pr-10 text-xs font-mono bg-muted resize-none"
            onFocus={(e) => e.target.select()}
          />
          <CopyButton
            value={shareString ?? ""}
            size="icon-sm"
            labels={{ copy: t("exportCopyAriaLabel") }}
            className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
          />
        </Box>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { useTranslations } from "@/i18n/translations";

interface PanelViewProps {
  panelId: string;
}

/**
 * Full-viewport FiestaPanel scene. Shell only for now — the live board,
 * physical scaling, and room scene land with the panel data hooks.
 */
export function PanelView({ panelId }: PanelViewProps) {
  const t = useTranslations("fiestaPanels");
  return (
    <div className="fixed inset-0 overflow-hidden bg-black" data-testid="panel-scene" data-panel-id={panelId}>
      <span className="sr-only">{t("title")}</span>
    </div>
  );
}

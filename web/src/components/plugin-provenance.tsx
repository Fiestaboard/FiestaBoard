"use client";

import { Badge } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

/** Repository attribution only; missing or malformed sources stay unknown. */
export function repositoryProvenance(repository?: string | null): "official" | "community" | "unknown" {
  if (!repository?.trim()) return "unknown";
  const raw = repository.trim().replace(/^git\+/, "");
  const scp = /^git@([^:]+):(.+)$/.exec(raw);
  try {
    const url = new URL(scp ? `ssh://git@${scp[1]}/${scp[2]}` : raw);
    if (!["https:", "http:", "ssh:", "git:"].includes(url.protocol)) return "unknown";
    const parts = url.pathname.split("/").filter(Boolean);
    if (!url.hostname || parts.length < 2) return "unknown";
    return url.hostname.toLowerCase() === "github.com" && parts[0].toLowerCase() === "fiestaboard"
      ? "official"
      : "community";
  } catch {
    return "unknown";
  }
}

export function PluginProvenance({ repository }: { repository?: string | null }) {
  const t = useTranslations("plugins");
  if (repositoryProvenance(repository) !== "community") return null;
  return (
    <Badge variant="outline" className="shrink-0 text-[10px]" title={t("communityDescription")}>
      {t("communityBadge")}
    </Badge>
  );
}

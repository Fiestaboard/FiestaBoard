import { FileText } from "lucide-react";
import { Outlet } from "react-router";

import { SectionShell } from "@/components/section-shell";
import { usePages } from "@/hooks/use-board";
import { useParams, usePathname, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/** Which page the editor routes are on: "new", an id, or none (the list). */
function useOpenPageId(): string | null {
  const pathname = usePathname();
  const { id } = useParams<{ id?: string }>();
  const searchParams = useSearchParams();
  if (pathname === "/pages/new") return "new";
  if (id) return id;
  // /pages/edit?id=… — the static-export form of the editor route.
  if (pathname === "/pages/edit") return searchParams.get("id");
  return null;
}

/**
 * The Pages section: its card and header stay mounted while the list and the
 * page editor swap beneath them. The editor used to slide up as a screen of
 * its own; it now opens under "Pages › <page name>", and pins the card to the
 * viewport so the editor keeps the height it scrolls within.
 */
export function PagesSection({ children }: { children: React.ReactNode }) {
  const t = useTranslations("pages");
  const tCommon = useTranslations("common");
  const openId = useOpenPageId();
  const { data, isLoading } = usePages();

  const page = openId && openId !== "new" ? data?.pages.find((p) => p.id === openId) : undefined;
  const detail = openId
    ? {
        id: openId,
        title: openId === "new" ? t("newPage") : (page?.name ?? (isLoading ? tCommon("loading") : openId)),
      }
    : null;

  return (
    <SectionShell
      icon={FileText}
      title={t("title")}
      description={t("description")}
      href="/pages"
      detail={detail}
      fill={detail != null}
    >
      {children}
    </SectionShell>
  );
}

export default function PagesLayout() {
  return (
    <PagesSection>
      <Outlet />
    </PagesSection>
  );
}

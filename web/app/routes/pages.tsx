import { LayoutGrid } from "lucide-react";
import { useCallback, useState } from "react";
import { Outlet } from "react-router";

import { CreatedPageContext } from "@/components/pages/created-page-context";
import { SectionShell } from "@/components/section-shell";
import { usePages } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useParams, usePathname, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/**
 * Which page the editor routes are on: "new", an id, or none (the list).
 * `created` is the page /pages/new made with its first save: the address
 * already shows it while the router still says /pages/new (BB-B-9).
 */
function useOpenPageId(created: string | null): string | null {
  const pathname = usePathname();
  const { id } = useParams<{ id?: string }>();
  const searchParams = useSearchParams();
  if (pathname === "/pages/new") return created ?? "new";
  if (id) return id;
  // /pages/edit?id=… — the static-export form of the editor route.
  if (pathname === "/pages/edit") return searchParams.get("id");
  return null;
}

/**
 * The Pages section. The list sits in the Pages card under its header; the
 * page editor replaces both with its own header (back to Pages, the name,
 * Save), as Figma draws it (57:64661, 184:159319), and pins itself to the
 * viewport so the editor keeps the height it scrolls within.
 */
export function PagesSection({ children }: { children: React.ReactNode }) {
  const t = useTranslations("pages");
  const tCommon = useTranslations("common");
  const pathname = usePathname();
  // The page this visit to /pages/new created. Forgotten as soon as the route
  // moves on, so the next New Page starts as "new" again.
  const [created, setCreated] = useState<string | null>(null);
  if (useDepsChanged([pathname]) && created !== null) setCreated(null);
  const openId = useOpenPageId(created);
  const reportCreated = useCallback((id: string) => setCreated(id), []);
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
      icon={LayoutGrid}
      title={t("title")}
      description={t("description")}
      href="/pages"
      detail={detail}
      fill={detail != null}
      bare
    >
      <CreatedPageContext.Provider value={reportCreated}>{children}</CreatedPageContext.Provider>
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

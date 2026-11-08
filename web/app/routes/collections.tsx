import { GalleryHorizontalEnd } from "lucide-react";
import { Outlet } from "react-router";

import { SectionShell } from "@/components/section-shell";
import { useCollections } from "@/hooks/use-board";
import { useParams, usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

// Keep the existing public utility/form imports stable.
export type { IntervalUnit } from "@/components/collection-form";
export { CollectionForm, formatInterval, parseCustomInterval, splitInterval } from "@/components/collection-form";

export default function CollectionsLayout() {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const pathname = usePathname();
  const { collectionId } = useParams<{ collectionId?: string }>();
  const { data, isLoading } = useCollections();
  const isNew = pathname === "/collections/new";
  const collection = data?.collections.find((item) => item.id === collectionId);
  const detail = isNew
    ? { id: "new", title: t("newCollection"), description: t("createDescription") }
    : collectionId
      ? {
          id: collectionId,
          title: collection?.name ?? (isLoading ? tc("loading") : t("editCollection")),
          description: t("editDescription"),
        }
      : null;
  return (
    <SectionShell
      icon={GalleryHorizontalEnd}
      title={t("title")}
      description={t("description")}
      href="/collections"
      detail={detail}
    >
      <Outlet />
    </SectionShell>
  );
}

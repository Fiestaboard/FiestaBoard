import { Button, PageHeader, PageLayout } from "@fiestaboard/ui";
import { Compass, Home as HomeIcon } from "lucide-react";

import Link from "@/components/smart-link";
import { RAIL_BREAKPOINT } from "@/hooks/use-below-rail";
import { useTranslations } from "@/i18n/translations";

/**
 * Any URL no route matches (BB-A-9): a page inside the app shell, so the
 * header and nav stay, with the way back Home. Without it React Router drew
 * a bare "404 Not Found" with no shell and no links.
 */
export default function NotFound() {
  const t = useTranslations("notFound");
  return (
    <PageLayout railBreakpoint={RAIL_BREAKPOINT}>
      <PageHeader icon={Compass} title={t("title")} description={t("description")} hue="orange">
        <Button asChild variant="brand" size="touch" className="gap-2">
          <Link href="/">
            <HomeIcon className="size-4" aria-hidden="true" />
            {t("home")}
          </Link>
        </Button>
      </PageHeader>
    </PageLayout>
  );
}

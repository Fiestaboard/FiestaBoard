import { Box, Button, EmptyState, PageLayout } from "@fiestaboard/ui";
import { CircleHelp, Home as HomeIcon, Search } from "lucide-react";

import Link from "@/components/smart-link";
import { useRailBreakpoint } from "@/hooks/use-below-rail";
import { useTranslations } from "@/i18n/translations";
import { HELP_DOCS_URL } from "@/lib/nav-items";

/**
 * Any URL no route matches (BB-A-9; 07e `329:50241` phone, `329:49338`
 * desktop): a centred empty state inside the app shell, so the header and nav
 * stay, naming the address that has nothing, with Go to Home and Help & Docs.
 * Without it React Router drew a bare "404 Not Found" with no shell or links.
 */
export default function NotFound() {
  const t = useTranslations("notFound");
  const railBreakpoint = useRailBreakpoint();
  const where = typeof window === "undefined" ? "" : `${window.location.host}${window.location.pathname}`;
  return (
    <PageLayout railBreakpoint={railBreakpoint}>
      <EmptyState
        icon={Search}
        illustration={<Search className="size-8 text-foreground" />}
        title={t("title")}
        description={t("description", { where })}
        className="min-h-[60dvh] [&_h3]:text-xl [&_h3]:font-semibold [&_[data-slot=empty-state-action]]:w-full [&_[data-slot=empty-state-action]]:max-w-sm"
        action={
          <Box className="flex w-full flex-col gap-3">
            <Button asChild variant="brand" size="touch" className="w-full gap-2">
              <Link href="/">
                <HomeIcon className="size-4" aria-hidden="true" />
                {t("home")}
              </Link>
            </Button>
            <Button asChild variant="outline" size="touch" className="w-full gap-2">
              <Link href={HELP_DOCS_URL} target="_blank" rel="noreferrer">
                <CircleHelp className="size-4" aria-hidden="true" />
                {t("help")}
              </Link>
            </Button>
          </Box>
        }
      />
    </PageLayout>
  );
}

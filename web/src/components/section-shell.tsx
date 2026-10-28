import {
  Box,
  PageCard,
  PageHeader,
  PageLayout,
  PageOutlet,
  PageSubheader,
  type PageSubheaderDetail,
} from "@fiestaboard/ui";
import type { LucideIcon } from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import Link from "@/components/smart-link";
import { usePathname } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";

/** The item a section's route has drilled into. */
export interface SectionDetail {
  /** Which item — a board id, a plugin id, a page id. Focus follows this, not the title. */
  id: string;
  /** The item's name: the breadcrumb's current entry and the h2. */
  title: string;
  description?: React.ReactNode;
  /** Where the crumb goes back to — the tab or filter the reader came from. Defaults to the section. */
  backHref?: string;
}

interface SectionShellProps {
  icon: LucideIcon;
  /** The section's name — the h1, and the crumb back to it. */
  title: string;
  description: React.ReactNode;
  /** The section root, e.g. "/displays". */
  href: string;
  /** The list's own action (Add a display). Tucks away while an item is open. */
  action?: React.ReactNode;
  /** The open item, or null at the section's list. */
  detail: SectionDetail | null;
  /** Pin the card to the viewport so the body can scroll inside it (the page editor). */
  fill?: boolean;
  /** The route outlet. */
  children: React.ReactNode;
}

/** The sub-header's action slot, for a detail page's own buttons. Null outside a shell. */
const ActionSlot = createContext<HTMLElement | null | undefined>(undefined);

/**
 * A SECTION'S CARD, MOUNTED ONCE. Each section with items to drill into
 * (Displays, Integrations, Pages) renders its routes inside this from a layout
 * route, so moving between the list and an item swaps only the body: the
 * header holds still, a breadcrumb and the item's h2 expand under it, and the
 * body fades in below. Before, each route drew its own card and the whole page
 * faded in again on every drill-in.
 *
 * The section works out `detail` itself, from the URL and data it already
 * caches, rather than having the detail route report it after mounting: an
 * item known on the first render is what lets a deep link land open, without
 * an animation and without taking focus.
 */
export function SectionShell({ icon, title, description, href, action, detail, fill, children }: SectionShellProps) {
  const t = useTranslations("common");
  const pathname = usePathname();
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  const subheader = useMemo<PageSubheaderDetail | null>(
    () =>
      detail && {
        id: detail.id,
        title: detail.title,
        description: detail.description,
        crumbs: [{ label: title, href: detail.backHref ?? href }],
        action: <Box ref={setSlot} className="contents" data-slot="section-action" />,
      },
    [detail, title, href],
  );

  // Coming back to the list, put focus on the link that opened the item. The
  // sub-header goes inert as it closes, which drops focus from the crumb the
  // reader just used; without this it lands on <body>.
  // A list opens items with links (matched by href) or with buttons that
  // navigate in a handler (a page tile), which say which item they open with
  // `data-section-item="<id>"`.
  const opened = useRef<{ path: string; id: string } | null>(null);
  useEffect(() => {
    if (detail) {
      opened.current = { path: pathname, id: detail.id };
      return;
    }
    const was = opened.current;
    opened.current = null;
    if (!was) return;
    const outlet = "[data-slot=page-outlet]";
    const byId = document.querySelector<HTMLElement>(`${outlet} [data-section-item="${CSS.escape(was.id)}"]`);
    const byHref = Array.from(document.querySelectorAll<HTMLAnchorElement>(`${outlet} a[href]`)).find((a) =>
      a.getAttribute("href")?.endsWith(was.path),
    );
    (byId ?? byHref)?.focus({ preventScroll: true });
  }, [detail, pathname]);

  return (
    <PageLayout fillHeight={fill}>
      <PageCard fillHeight={fill}>
        <PageHeader icon={icon} title={title} description={description} collapsed={detail != null}>
          {action}
        </PageHeader>
        <PageSubheader
          detail={subheader}
          breadcrumbLabel={t("breadcrumb")}
          renderLink={({ href: to, children: label }) => <Link href={to}>{label}</Link>}
        />
        <ActionSlot value={slot}>
          <PageOutlet key={pathname} fill={fill}>
            {children}
          </PageOutlet>
        </ActionSlot>
      </PageCard>
    </PageLayout>
  );
}

/**
 * A detail page's own actions (Install, Add instance), drawn on the
 * sub-header row beside the item's name. Rendered in place when the page is
 * not inside a shell — a test rendering the route on its own.
 */
export function SectionAction({ children }: { children: React.ReactNode }) {
  const slot = useContext(ActionSlot);
  if (slot === undefined) return <>{children}</>;
  return slot ? createPortal(children, slot) : null;
}

import {
  Box,
  Button,
  Flex,
  Heading,
  PageCard,
  PageHeader,
  PageLayout,
  PageOutlet,
  PageSubheader,
  type PageSubheaderDetail,
  Stack,
} from "@fiestaboard/ui";
import { ChevronLeft, type LucideIcon } from "lucide-react";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import Link from "@/components/smart-link";
import { useBelowRail, useRailBreakpoint } from "@/hooks/use-below-rail";
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
  /**
   * On a phone, drop the card and the section description: the list is the
   * title with its action beside it, and an item is "‹ <section>" over its
   * name (07d `320:17086`, `328:27519`; BB-A-19, BB-A-24).
   */
  compactOnPhone?: boolean;
  /**
   * The open item draws its own header (the page editor: back, name, Save), so
   * the section's header, breadcrumb and card are not drawn around it.
   */
  bare?: boolean;
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
export function SectionShell({
  icon,
  title,
  description,
  href,
  action,
  detail,
  fill,
  compactOnPhone,
  bare = false,
  children,
}: SectionShellProps) {
  const railBreakpoint = useRailBreakpoint();
  const t = useTranslations("common");
  const phone = useBelowRail();
  // Drilling in on a phone moves focus to the item's name, as the card's
  // sub-header does on wider screens; a deep link (first render) keeps it.
  const titleRef = useRef<HTMLHeadingElement>(null);
  const shownId = useRef(detail?.id ?? null);
  useEffect(() => {
    const id = detail?.id ?? null;
    if (id === shownId.current) return;
    shownId.current = id;
    if (id && compactOnPhone && phone) titleRef.current?.focus({ preventScroll: true });
  }, [detail?.id, compactOnPhone, phone]);
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

  if (bare && detail) {
    // The item fills the viewport and scrolls inside itself at every width,
    // so its own sticky header (and the editor's docked preview) stay put.
    // On a phone it runs edge to edge, as the editor frames draw it.
    return (
      <PageLayout
        railBreakpoint={railBreakpoint}
        fillHeight={fill}
        outerClassName="flex h-dvh flex-col overflow-hidden sm:h-dvh"
        className="flex min-h-0 flex-1 flex-col overflow-hidden max-sm:p-0"
      >
        <PageCard fillHeight={fill} surface="plain">
          <ActionSlot value={null}>
            <PageOutlet key={pathname} fill={fill}>
              {children}
            </PageOutlet>
          </ActionSlot>
        </PageCard>
      </PageLayout>
    );
  }

  // One tree for both layouts: the outlet keeps its place (PageCard → slot →
  // PageOutlet), so crossing the breakpoint (a rotated tablet, a full-page
  // capture) never remounts the page and its state (#2568 review).
  const compact = !!compactOnPhone && phone;
  const compactHeader = detail ? (
    <Stack gap="1" className="mb-3">
      <Button asChild variant="ghost" size="touch" className="-ms-4 self-start gap-1 px-3">
        <Link href={detail.backHref ?? href}>
          <ChevronLeft className="size-4" aria-hidden="true" />
          {title}
        </Link>
      </Button>
      <Heading level={1} size="2xl" ref={titleRef} tabIndex={-1} className="focus-ring rounded-sm">
        {detail.title}
      </Heading>
    </Stack>
  ) : (
    <Flex align="center" justify="between" gap="3" className="mb-4">
      <Heading level={1} size="2xl">
        {title}
      </Heading>
      {action}
    </Flex>
  );

  return (
    <PageLayout railBreakpoint={railBreakpoint} fillHeight={fill}>
      <PageCard
        fillHeight={fill}
        // On a phone the page is the surface (07d): the kit's plain card, and
        // the page's own sections on the gutter (DD-W135); a section that is a
        // card's content keeps its inset.
        surface={compact ? "plain" : "card"}
        className={
          compact
            ? "overflow-visible [&_[data-slot=page-section]:not([data-slot=card]_*)]:px-0 [&_[data-slot=page-toolbar]]:px-0"
            : undefined
        }
      >
        {compact ? (
          compactHeader
        ) : (
          <PageHeader icon={icon} title={title} description={description} collapsed={detail != null}>
            {action}
          </PageHeader>
        )}
        {compact ? null : (
          <PageSubheader
            detail={subheader}
            breadcrumbLabel={t("breadcrumb")}
            renderLink={({ href: to, children: label }) => <Link href={to}>{label}</Link>}
          />
        )}
        {/* On a phone there is no sub-header slot: a detail page's own
            actions render in place. */}
        <ActionSlot value={compact ? undefined : slot}>
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

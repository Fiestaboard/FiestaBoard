/**
 * Swizzled `@theme/Logo` — renders the brand mark with FiestaUI's `FiestaIcon`
 * + `FiestaLogo` instead of a pair of PNG lockups.
 *
 * The stock component renders `themeConfig.navbar.logo` through `ThemedImage`,
 * which meant shipping `logo-lockup-light.png` / `logo-lockup-dark.png` and then
 * hand-nudging them into alignment in `custom.css`:
 *
 *     .navbar__logo img { height: 48px; object-fit: cover;
 *                         object-position: left 100%; transform: translateY(-8px); }
 *
 * …because the raster lockup carried transparent padding above the taco. The DS
 * components are vector, tint from the theme tokens (so no light/dark pair), and
 * need no nudging — both the rule and the second image are gone.
 *
 * Swizzled here rather than at `@theme/Navbar/Logo` so every call site is
 * covered: the navbar, the mobile sidebar header, and `DocSidebar/Desktop`
 * (which renders a logo of its own whenever `navbar.hideOnScroll` is enabled).
 *
 * `themeConfig.navbar.logo` is left in place — it is a documented config
 * surface and Docusaurus reads `logo.href`/`logo.target` — but the `src` /
 * `srcDark` images are no longer rendered anywhere.
 */

import Link from "@docusaurus/Link";
import { useThemeConfig } from "@docusaurus/theme-common";
import useBaseUrl from "@docusaurus/useBaseUrl";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import { FiestaIcon, FiestaLogo } from "@fiestaboard/ui";
import type { Props } from "@theme/Logo";
import clsx from "clsx";
import type { ReactNode } from "react";

export default function Logo({ className, imageClassName, titleClassName, ...props }: Props): ReactNode {
  const {
    siteConfig: { title },
  } = useDocusaurusContext();
  const {
    navbar: { logo },
  } = useThemeConfig();
  const logoLink = useBaseUrl(logo?.href || "/");

  return (
    <Link
      to={logoLink}
      aria-label={title}
      {...(logo?.target && { target: logo.target })}
      {...props}
      className={clsx("flex items-center gap-2", className)}
    >
      <FiestaIcon size={28} className={imageClassName} />
      <FiestaLogo size="md" className={clsx("text-foreground", titleClassName)} />
    </Link>
  );
}

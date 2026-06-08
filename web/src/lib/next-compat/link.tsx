/**
 * Compat shim for `next/link` on React Router v7.
 *
 * Maps `next/link`'s `href` prop to RR7's `to`, ignores Next-only props
 * (`prefetch`, `replace`, `scroll`, `shallow`, `locale`, `legacyBehavior`,
 * `passHref`). For internal navigations RR7's <Link> does the right
 * thing — client-side transition without a full reload. For external
 * URLs (with protocol), fall back to a plain anchor.
 */
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { Link as RRLink } from "react-router";

type NextLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  as?: string;
  prefetch?: boolean | null;
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
  locale?: string | false;
  legacyBehavior?: boolean;
  passHref?: boolean;
  children?: ReactNode;
};

export default function Link({
  href,
  as: _as,
  prefetch: _prefetch,
  replace,
  scroll: _scroll,
  shallow: _shallow,
  locale: _locale,
  legacyBehavior: _legacyBehavior,
  passHref: _passHref,
  children,
  ...rest
}: NextLinkProps) {
  // External links go through a plain <a> so target/_blank/etc. work as
  // expected and we don't try to client-side route a different origin.
  const isExternal = /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(href);
  if (isExternal) {
    return (
      <a href={href} {...rest}>
        {children}
      </a>
    );
  }
  return (
    <RRLink to={href} replace={replace} {...rest}>
      {children}
    </RRLink>
  );
}

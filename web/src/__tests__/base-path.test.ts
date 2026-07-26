/**
 * Unit spec for the runtime base-path helper that makes API URLs work
 * behind HA Ingress. The source of truth is React Router's hydration
 * global — nginx's sub_filter rewrites its `"basename":"/"` literal to
 * the ingress prefix (see entrypoint.sh::configure_ingress_path_rewrite),
 * so reading it back gives the SPA the prefix without any hard-coded
 * knowledge of HA.
 */
import { afterEach, describe, expect, it } from "vitest";

import { apiUrl, appUrl, getBasePath, stripBasePath } from "@/lib/base-path";

type IngressWindow = Window & {
  __reactRouterContext?: { basename?: string };
};
const win = window as IngressWindow;

afterEach(() => {
  delete win.__reactRouterContext;
});

describe("getBasePath", () => {
  it("returns '' when the hydration global is absent (vite dev, tests)", () => {
    expect(getBasePath()).toBe("");
  });

  it("returns '' for the default basename '/'", () => {
    win.__reactRouterContext = { basename: "/" };
    expect(getBasePath()).toBe("");
  });

  it("returns '' for an empty basename", () => {
    win.__reactRouterContext = { basename: "" };
    expect(getBasePath()).toBe("");
  });

  it("strips the trailing slash from an ingress basename", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(getBasePath()).toBe("/api/hassio_ingress/tok");
  });

  it("tolerates a basename without a trailing slash", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok" };
    expect(getBasePath()).toBe("/api/hassio_ingress/tok");
  });
});

describe("apiUrl", () => {
  it("builds plain /api URLs for direct deployments", () => {
    expect(apiUrl("/health")).toBe("/api/health");
  });

  it("prefixes the ingress base path", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(apiUrl("/pages")).toBe("/api/hassio_ingress/tok/api/pages");
  });
});

describe("appUrl", () => {
  it("passes document URLs through for direct deployments", () => {
    expect(appUrl("/login?redirect=%2F")).toBe("/login?redirect=%2F");
  });

  it("prefixes document URLs with the ingress base path", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(appUrl("/login?redirect=%2F")).toBe("/api/hassio_ingress/tok/login?redirect=%2F");
  });
});

describe("stripBasePath", () => {
  it("returns the pathname unchanged for direct deployments", () => {
    expect(stripBasePath("/settings")).toBe("/settings");
  });

  it("strips the ingress prefix from a pathname", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(stripBasePath("/api/hassio_ingress/tok/settings")).toBe("/settings");
  });

  it("maps the bare prefix to '/'", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(stripBasePath("/api/hassio_ingress/tok/")).toBe("/");
    expect(stripBasePath("/api/hassio_ingress/tok")).toBe("/");
  });

  it("leaves pathnames outside the prefix unchanged", () => {
    win.__reactRouterContext = { basename: "/api/hassio_ingress/tok/" };
    expect(stripBasePath("/other/route")).toBe("/other/route");
  });
});

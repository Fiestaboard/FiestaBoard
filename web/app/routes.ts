import { type RouteConfig, index, route } from "@react-router/dev/routes";

/**
 * Route configuration for FiestaBoard. The actual route components are
 * kept under `app/routes/` and (where it's a thin re-export) delegate to
 * the canonical implementation under `../src/app/<route>/page.tsx`. The
 * file-based split makes RR7 happy without forcing us to physically move
 * 187 source files in a single PR.
 */
export default [
  index("routes/home.tsx"),
  route("login", "routes/login.tsx"),
  route("offline", "routes/offline.tsx"),
  route("profile", "routes/profile.tsx"),
  route("settings", "routes/settings.tsx"),
  route("collections", "routes/collections.tsx"),
  route("debug", "routes/debug.tsx"),
  route("picks", "routes/picks.tsx"),
  route("integrations", "routes/integrations._index.tsx"),
  route("integrations/:pluginId", "routes/integrations.$pluginId.tsx"),
  route("pages", "routes/pages._index.tsx"),
  route("pages/new", "routes/pages.new.tsx"),
  route("pages/edit", "routes/pages.edit._index.tsx"),
  route("pages/edit/:id", "routes/pages.edit.$id.tsx"),
  route("schedule", "routes/schedule.tsx"),
] satisfies RouteConfig;

import { index, route, type RouteConfig } from "@react-router/dev/routes";

/**
 * Route configuration for FiestaBoard. Each route module lives in
 * `app/routes/` and is loaded by React Router v7 in framework mode.
 */
export default [
  index("routes/home.tsx"),
  route("login", "routes/login.tsx"),
  route("offline", "routes/offline.tsx"),
  route("profile", "routes/profile.tsx"),
  route("settings", "routes/settings.tsx"),
  route("collections", "routes/collections.tsx"),
  route("debug", "routes/debug.tsx"),
  // A section layout: the card and header stay mounted between the list and
  // a display (section-shell.tsx).
  route("displays", "routes/displays.tsx", [
    index("routes/displays._index.tsx"),
    route(":boardId", "routes/displays.$boardId.tsx"),
  ]),
  route("picks", "routes/picks.tsx"),
  route("integrations", "routes/integrations.tsx", [
    index("routes/integrations._index.tsx"),
    route(":pluginId", "routes/integrations.$pluginId.tsx"),
  ]),
  route("pages", "routes/pages.tsx", [
    index("routes/pages._index.tsx"),
    route("new", "routes/pages.new.tsx"),
    route("edit", "routes/pages.edit._index.tsx"),
    route("edit/:id", "routes/pages.edit.$id.tsx"),
  ]),
  route("schedule", "routes/schedule.tsx"),
  route("panel/:panelId", "routes/panel.tsx"),
  route("p/:panelId", "routes/panel-short.tsx"),
] satisfies RouteConfig;

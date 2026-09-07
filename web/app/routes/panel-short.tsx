/**
 * `/p/:panelId` — the TV-typable alias for the FiestaPanel viewer.
 * Same module as `/panel/:panelId`; the param may be a panel's short code
 * (e.g. `1`) or its full id — the public API resolves either.
 */
export { default } from "./panel";

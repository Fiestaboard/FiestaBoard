// Where things are on screen, by name.
//
// The walkthrough never positions anything by pixels: every spotlight,
// ghost value and typed reveal is anchored to an element found by a
// selector, the same contract the docs-capture tooling uses to frame and
// highlight screenshots (assets/docs-captures/README.md, "Anchoring").
//
// An anchor id is a small dotted path (`pages.new`, `page-editor.name`,
// `settings.general.instance_name`, `plugin.weather`). It resolves to the
// first element carrying `data-ai-anchor="<id>"`, then to any legacy
// selector listed here for ids that predate the attribute. Renaming an
// anchor is a contract change: a script and a capture may both name it.

export const ANCHOR_ATTR = "data-ai-anchor";

/**
 * Legacy selectors for anchors whose element already carries a stable id.
 * A `data-ai-anchor` on the element always wins; these are the fallback.
 */
const LEGACY_SELECTORS: Record<string, readonly string[]> = {
  "page-editor.name": ["#page-name"],
  "schedule.form.page": ["#page"],
  "schedule.form.start-time": ["#start-time"],
  "schedule.form.end-time": ["#end-time"],
  "schedule.form.has-end-time": ["#has-end-time"],
  "schedule.form.recurrence": ["#recurrence"],
  "schedule.form.enabled": ["#enabled"],
  "collection.form.name": ["#collection-name"],
  "collection.form.mode": ["#collection-mode"],
  "collection.form.interval": ["#collection-interval"],
  "settings.general.instance_name": ["#instance-name"],
  "settings.general.timezone": ["#timezone-picker"],
  "settings.general.time_format": ["#time-format"],
  "settings.general.date_format": ["#date-format"],
  "settings.location.latitude": ["#latitude"],
  "settings.location.longitude": ["#longitude"],
  "settings.display.reduce_motion": ["#reduce-motion"],
  "settings.polling.interval_seconds": ["#polling-interval"],
  "settings.polling.board_read_interval_local": ["#board-read-local"],
  "settings.polling.board_read_interval_cloud": ["#board-read-cloud"],
  "settings.transitions.step_interval_ms": ["#step-interval"],
  "settings.transitions.step_size": ["#step-size"],
  "settings.silence_schedule": ["#silence-schedule"],
  "settings.silence_schedule.enabled": ["#silence-enabled"],
  "settings.silence_schedule.start_time": ["#silence-start"],
  "settings.silence_schedule.end_time": ["#silence-end"],
  "settings.silence_schedule.mode": ["#silence-mode"],
  "settings.silence_schedule.indicator_text": ["#silence-indicator-text"],
  "settings.silence_schedule.indicator_position": ["#silence-indicator-position"],
  "settings.silence_schedule.page_id": ["#silence-page"],
  "settings.schedule_behavior.defer_on_reenable": ["#schedule-defer-on-reenable"],
  "settings.hdmi_kiosk.enabled": ["#hdmi-kiosk"],
  "settings.ai.enabled": ["#ai-enabled"],
  "settings.mqtt.host": ["#mqtt-broker-host"],
  "settings.mqtt.port": ["#mqtt-broker-port"],
  "settings.mqtt.external_url": ["#mqtt-external-url"],
  "settings.boards": ["#board-card"],
  "settings.boards.name": ["#board-name-input"],
  "settings.boards.paused": ["#board-pause-switch"],
};

/** Every selector that may resolve `id`, most specific first. */
export function anchorSelectors(id: string): string[] {
  // The id sits inside a quoted attribute value, so only a backslash and a
  // double quote need escaping — not `CSS.escape`, which escapes for an
  // identifier position and would turn every dotted path into `a\.b`.
  const escaped = id.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return [`[${ANCHOR_ATTR}="${escaped}"]`, ...(LEGACY_SELECTORS[id] ?? [])];
}

/**
 * The element for `id`, or null when nothing on the page carries it.
 *
 * A settings control falls back to the card that owns it
 * (`settings.general.instance_name` → `settings.general`), so a key whose
 * input has no anchor of its own still has somewhere to point. The fallback
 * is resolved here, against the live DOM, rather than when a script is
 * built — a script is built before its `navigate` has even run, when
 * nothing the tool touches is on screen yet.
 */
export function resolveAnchor(id: string, root: ParentNode = document): HTMLElement | null {
  for (const selector of anchorSelectors(id)) {
    const el = root.querySelector<HTMLElement>(selector);
    if (el) return el;
  }
  const card = settingCardFor(id);
  return card ? resolveAnchor(card, root) : null;
}

/** The card anchor behind a `settings.<category>.<key>` id, if it is one. */
function settingCardFor(id: string): string | null {
  const parts = id.split(".");
  if (parts.length < 3 || parts[0] !== "settings") return null;
  const card = SETTING_SECTIONS[parts[1]]?.card ?? `settings.${parts[1]}`;
  return card === id ? null : card;
}

/** JSX spread that stamps an element as an anchor: `{...anchorProps("pages.new")}`. */
export function anchorProps(id: string): { [ANCHOR_ATTR]: string } {
  return { [ANCHOR_ATTR]: id };
}

/**
 * The settings tab that owns a `update_setting` category, and the card the
 * spotlight lands on when a key has no control-level anchor of its own.
 * Keys resolve to `settings.<category>.<key>` first, then to the card.
 */
export const SETTING_SECTIONS: Record<string, { section: string; card?: string }> = {
  general: { section: "general" },
  location: { section: "general", card: "settings.location" },
  display: { section: "general", card: "settings.display" },
  transitions: { section: "behavior", card: "settings.transitions" },
  polling: { section: "behavior", card: "settings.polling" },
  silence_schedule: { section: "behavior", card: "settings.silence_schedule" },
  schedule_behavior: { section: "behavior", card: "settings.schedule_behavior" },
  output: { section: "hardware", card: "settings.output" },
  hdmi_kiosk: { section: "hardware", card: "settings.hdmi_kiosk" },
  boards: { section: "hardware", card: "settings.boards" },
  ai: { section: "integrations", card: "settings.ai" },
  mqtt: { section: "integrations", card: "settings.mqtt" },
  plugins: { section: "integrations", card: "settings.plugins" },
  release_channel: { section: "system", card: "settings.release_channel" },
  auto_update: { section: "system", card: "settings.auto_update" },
  beta: { section: "advanced", card: "settings.beta" },
};

/** The anchor for one setting key, and the card behind it. */
export function settingAnchors(category: string, key: string): { control: string; card: string } {
  const owner = SETTING_SECTIONS[category];
  return { control: `settings.${category}.${key}`, card: owner?.card ?? `settings.${category}` };
}

/** The settings route that shows `category`, with the card hash when known. */
export function settingsHref(category: string): string {
  const owner = SETTING_SECTIONS[category];
  const section = owner?.section ?? "general";
  return `/settings?section=${section}`;
}

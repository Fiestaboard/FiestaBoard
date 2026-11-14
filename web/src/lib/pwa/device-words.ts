/**
 * "phone" or "computer", for copy that names the device in your hand (07e
 * "This phone isn't connected…"; 07 "Add FiestaBoard Control to this
 * phone?"). Tablets read as phones: both are the touch device you carry.
 */
export type DeviceWord = "phone" | "computer";

export function deviceWord(
  userAgent: string = typeof navigator === "undefined" ? "" : navigator.userAgent,
): DeviceWord {
  return /Mobi|Android|iPhone|iPad|iPod/.test(userAgent) ? "phone" : "computer";
}

/** The hub's address as this page reached it ("fiestapi.local", "board.example.com:8443"). */
export function hubHost(loc: Pick<Location, "host"> = window.location): string {
  return loc.host;
}

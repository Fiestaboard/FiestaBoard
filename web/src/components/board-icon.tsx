/**
 * Vestaboard-shaped icon: a wide rounded frame with rows of split-flap tile
 * dots. Used wherever the UI points at a physical board (board switcher,
 * active-board indicator) instead of lucide's Monitor, which reads as a TV.
 *
 * Drawn in the lucide style (24×24 viewBox, stroke-based, currentColor) so it
 * sits seamlessly next to real lucide icons.
 */
export function BoardIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      data-testid="board-icon"
      aria-hidden="true"
    >
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <path d="M6.5 9.5h.01M10.17 9.5h.01M13.84 9.5h.01M17.5 9.5h.01" />
      <path d="M6.5 14.5h.01M10.17 14.5h.01M13.84 14.5h.01M17.5 14.5h.01" />
    </svg>
  );
}

/**
 * Myra brand mark — a navy rounded-badge with a coral "M" (app-icon style).
 * Self-contained (has its own navy tile + subtle light border), so it reads on any surface:
 * the white header, the light content area (as the reply avatar), and the login / loading screens.
 * Size it via the className (e.g. "h-9 w-9").
 */
export function MyraMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={className} role="img" aria-label="Myra logo">
      {/* White disc backing. In the light theme it blends into the white header (you see just the M);
          in the dark theme it gives the navy legs a light backdrop — so one mark works on both. */}
      <circle cx="50" cy="50" r="49" fill="#ffffff" stroke="rgba(11,53,89,0.15)" strokeWidth="1" />
      {/* navy legs (left slightly lighter, as if lit from upper-left) */}
      <path d="M30 46 L39 52 L39 82 L30 76 Z" fill="#12244d" />
      <path d="M70 46 L61 52 L61 82 L70 76 Z" fill="#0b1732" />
      {/* red isometric "roof" + centre spike; the right roof face is a touch darker for the 3D fold */}
      <path d="M30 46 L50 24 L70 46 L61 52 L50 82 L39 52 Z" fill="#ef2b36" />
      <path d="M50 24 L70 46 L61 52 L50 35 Z" fill="#d3272f" />
      {/* white diamond notch in the top face */}
      <path d="M50 32 L42 42 L50 52 L58 42 Z" fill="#ffffff" />
    </svg>
  );
}

/**
 * Myra avatar shown beside an assistant reply. The mark is already a self-contained navy badge,
 * so we just size it (no extra tile) — matching the chat design.
 */
export function MyraAvatar({ className = "" }: { className?: string }) {
  return <MyraMark className={`h-8 w-8 shrink-0 ${className}`} />;
}

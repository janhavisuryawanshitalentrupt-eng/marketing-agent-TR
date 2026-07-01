/**
 * Myra brand mark — a navy rounded-badge with a coral "M" (app-icon style).
 * Self-contained (has its own navy tile + subtle light border), so it reads on any surface:
 * the white header, the light content area (as the reply avatar), and the login / loading screens.
 * Size it via the className (e.g. "h-9 w-9").
 */
export function MyraMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} role="img" aria-label="Myra logo">
      <defs>
        <linearGradient id="myra-badge" x1="0" y1="0" x2="0.4" y2="1">
          <stop offset="0" stopColor="#134a79" />
          <stop offset="1" stopColor="#0a2c4b" />
        </linearGradient>
        <linearGradient id="myra-coral" x1="0.1" y1="0" x2="0.5" y2="1">
          <stop offset="0" stopColor="#ff9f5e" />
          <stop offset="0.5" stopColor="#ff6a54" />
          <stop offset="1" stopColor="#ff4f72" />
        </linearGradient>
      </defs>
      {/* navy badge tile with a hairline light border so it also reads on dark surfaces */}
      <rect x="3.5" y="3.5" width="41" height="41" rx="11.5" fill="url(#myra-badge)" stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
      {/* soft top-left facet for a subtle 3D badge feel */}
      <path d="M8 19 Q8 8 19 8 L27 8 Z" fill="#ffffff" opacity="0.05" />
      {/* coral angular "M" */}
      <path
        d="M14 33.5 L14 15.5 L24 26.5 L34 15.5 L34 33.5"
        fill="none"
        stroke="url(#myra-coral)"
        strokeWidth="5.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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

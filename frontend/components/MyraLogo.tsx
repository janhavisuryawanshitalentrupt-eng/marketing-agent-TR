/**
 * Myra brand mark — a navy rounded-badge with a coral "M" (app-icon style).
 * Self-contained (has its own navy tile + subtle light border), so it reads on any surface:
 * the white header, the light content area (as the reply avatar), and the login / loading screens.
 * Size it via the className (e.g. "h-9 w-9").
 */
export function MyraMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} role="img" aria-label="Myra logo">
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
      <rect x="4" y="4" width="56" height="56" rx="16" fill="url(#myra-badge)" stroke="rgba(255,255,255,0.14)" strokeWidth="1.5" />
      {/* the Myra "M": two white legs + a coral inner V + a coral swoosh over the top */}
      <rect x="17.5" y="23" width="7" height="23" rx="3.5" fill="#ffffff" />
      <rect x="39.5" y="23" width="7" height="23" rx="3.5" fill="#ffffff" />
      <path d="M21 25 L32 39.5 L43 25" fill="none" stroke="url(#myra-coral)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M22 20.5 C31 13 40 14.5 44 19.5" fill="none" stroke="url(#myra-coral)" strokeWidth="3.4" strokeLinecap="round" opacity="0.92" />
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

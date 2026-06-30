/**
 * Myra brand mark — the "M" with theme-aware legs and a coral→pink gradient swoosh.
 * Pure inline SVG, no background tile: the legs use `currentColor` so the mark reads on BOTH
 * light and dark surfaces (inherits the foreground text color of wherever it's placed), while the
 * coral swoosh stays vivid in either theme. Size it via the className (e.g. "h-9 w-9").
 */
export function MyraMark({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="6 4 52 52" className={className} role="img" aria-label="Myra logo">
      <defs>
        <linearGradient id="myra-coral" x1="0.1" y1="0" x2="0.45" y2="1">
          <stop offset="0" stopColor="#ff9f5e" />
          <stop offset="0.5" stopColor="#ff6a54" />
          <stop offset="1" stopColor="#ff4f72" />
        </linearGradient>
      </defs>
      {/* legs — inherit the surrounding text color so they flip with the theme */}
      <rect x="12.5" y="20" width="9" height="27.5" rx="4.5" fill="currentColor" />
      <rect x="42.5" y="20" width="9" height="27.5" rx="4.5" fill="currentColor" />
      {/* coral inner V (middle of the M) */}
      <path
        d="M17 22.5 L32 43 L47 22.5"
        fill="none"
        stroke="url(#myra-coral)"
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* swoosh arcing over the top */}
      <path
        d="M19.5 19.5 C33 7.5 46 11.5 53 19"
        fill="none"
        stroke="url(#myra-coral)"
        strokeWidth="4"
        strokeLinecap="round"
        opacity="0.92"
      />
    </svg>
  );
}

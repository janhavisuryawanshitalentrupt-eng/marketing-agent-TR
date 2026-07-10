/**
 * Myra brand mark — an app-icon: a rounded pink→purple gradient tile with a white serif "M".
 * The gradient fill + white letter read clearly on ANY surface (white header, light content, pink
 * boxes, avatars). Scalable SVG. Size it via the className (e.g. "h-9 w-9").
 *
 * Pass `wordmark` for the full lockup (tile + M + "MYRA") used on the login screen.
 */
export function MyraMark({ className = "", wordmark = false }: { className?: string; wordmark?: boolean }) {
  return (
    <svg viewBox="0 0 100 100" className={className} role="img" aria-label="Myra logo">
      <defs>
        <linearGradient id="myra-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ff4f87" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      {/* Gradient tile */}
      <rect x="3" y="3" width="94" height="94" rx="26" fill="url(#myra-grad)" />
      {/* Serif "M" */}
      <text
        x="50"
        y={wordmark ? "42" : "51"}
        textAnchor="middle"
        dominantBaseline="central"
        fill="#ffffff"
        fontFamily="Georgia, 'Times New Roman', 'Playfair Display', serif"
        fontSize={wordmark ? "44" : "52"}
        fontWeight={600}
      >
        M
      </text>
      {wordmark && (
        <text
          x="50"
          y="74"
          textAnchor="middle"
          fill="#ffffff"
          fontFamily="Georgia, 'Times New Roman', serif"
          fontSize="12"
          letterSpacing="3.5"
          fontWeight={500}
        >
          MYRA
        </text>
      )}
    </svg>
  );
}

/**
 * Myra avatar shown beside an assistant reply — the app-icon mark, sized (no extra tile).
 */
export function MyraAvatar({ className = "" }: { className?: string }) {
  return <MyraMark className={`h-8 w-8 shrink-0 ${className}`} />;
}

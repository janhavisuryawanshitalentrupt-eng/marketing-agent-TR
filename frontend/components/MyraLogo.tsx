/**
 * Myra brand mark — the official pink→purple "M" (network nodes + sparkle), extracted from the brand
 * sheet as a transparent PNG so it floats cleanly on any surface (light glass, dark glass, avatars).
 * Size it via the className (e.g. "h-9 w-9").
 */
export function MyraMark({ className = "" }: { className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/myra-mark.png"
      alt="Myra"
      draggable={false}
      className={`object-contain select-none ${className}`}
    />
  );
}

/**
 * Full Myra lockup — the mark above the "Myra" wordmark and the "Your AI Marketing Agent" tagline
 * (with "AI" in the brand purple). Text is theme-aware (crisp foreground on light AND dark). Used on
 * the login screen and any splash/hero.
 */
export function MyraLockup({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-col items-center text-center ${className}`}>
      <MyraMark className="h-20 w-20" />
      <div className="mt-3 font-heading text-4xl font-bold leading-none tracking-tight text-foreground">
        Myra
      </div>
      <div className="mt-2 text-sm text-muted">
        Your <span className="font-semibold text-[var(--brand-navy-2)]">AI</span> Marketing Agent
      </div>
    </div>
  );
}

/**
 * Myra avatar shown beside an assistant reply — the mark, sized small.
 */
export function MyraAvatar({ className = "" }: { className?: string }) {
  return <MyraMark className={`h-8 w-8 shrink-0 ${className}`} />;
}

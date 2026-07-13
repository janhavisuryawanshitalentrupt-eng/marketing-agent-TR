"use client";

export function EmptyState({
  icon,
  title,
  subtitle,
  children,
}: {
  icon?: React.ReactNode;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div
        className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl text-white"
        style={{ background: "var(--grad-navy)", boxShadow: "0 8px 24px rgba(168,85,247,0.35)" }}
      >
        <span className="text-white">
          {icon ?? (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
            </svg>
          )}
        </span>
      </div>
      <h2 className="font-heading text-xl font-semibold">{title}</h2>
      {subtitle && <p className="mt-2 max-w-md text-sm text-muted">{subtitle}</p>}
      {children && <div className="mt-6 w-full">{children}</div>}
    </div>
  );
}

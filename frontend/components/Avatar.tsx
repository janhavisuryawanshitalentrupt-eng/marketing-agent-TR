"use client";

import { useEffect, useState } from "react";
import { getAvatar, subscribeAvatar } from "@/lib/avatar";

// Deterministic, tasteful avatar colors (brand-adjacent).
const COLORS = [
  "linear-gradient(135deg,#0b3559,#0e4373)",
  "linear-gradient(135deg,#f6404c,#ff7a52)",
  "linear-gradient(135deg,#2563eb,#0e4373)",
  "linear-gradient(135deg,#0e7490,#0b3559)",
  "linear-gradient(135deg,#b45309,#f6404c)",
  "linear-gradient(135deg,#7c3aed,#2563eb)",
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function hashIndex(name: string, mod: number): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return h % mod;
}

/** `self` = this is the SIGNED-IN user's avatar, so it shows their uploaded profile photo (from the local
 * avatar store) when one is set, falling back to the coloured initials. Company/other avatars omit `self`. */
export function Avatar({ name, size = 36, self = false }: { name: string; size?: number; self?: boolean }) {
  const [photo, setPhoto] = useState<string | null>(null);
  useEffect(() => {
    if (!self) return;
    const update = () => setPhoto(getAvatar());
    update();
    return subscribeAvatar(update);
  }, [self]);

  if (self && photo) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={photo}
        alt=""
        className="inline-block shrink-0 rounded-full object-cover"
        style={{ width: size, height: size }}
        aria-hidden
      />
    );
  }

  const bg = COLORS[hashIndex(name || "?", COLORS.length)];
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-heading font-semibold text-white"
      style={{
        width: size,
        height: size,
        background: bg,
        fontSize: size * 0.36,
      }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

// Local profile-photo store (frontend-only — no backend/workflow touched). The user's uploaded avatar is
// kept in localStorage, keyed per signed-in user, and any `self` <Avatar> subscribes so all of them update
// together the moment it changes. Downscaled to a small square on upload, so it stays tiny in storage.

let activeKey = "tr_avatar:me";
const listeners = new Set<() => void>();

/** Point the store at the signed-in user (so admin and member don't share a photo on the same browser). */
export function setAvatarUser(username: string): void {
  const next = `tr_avatar:${(username || "me").toLowerCase()}`;
  if (next !== activeKey) {
    activeKey = next;
    listeners.forEach((f) => f());
  }
}

export function getAvatar(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(activeKey);
  } catch {
    return null;
  }
}

export function setAvatar(dataUrl: string | null): void {
  try {
    if (dataUrl) localStorage.setItem(activeKey, dataUrl);
    else localStorage.removeItem(activeKey);
  } catch {
    /* quota / privacy mode — ignore */
  }
  listeners.forEach((f) => f());
}

export function subscribeAvatar(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Read an image File, cover-fit it into a `size`×`size` square, return a compact JPEG data URL. */
export function fileToAvatarDataUrl(file: File, size = 256): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("Please choose an image file"));
      return;
    }
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      try {
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("no canvas");
        const scale = Math.max(size / img.width, size / img.height);
        const w = img.width * scale;
        const h = img.height * scale;
        ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      } catch (e) {
        reject(e as Error);
      }
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Couldn't read that image"));
    };
    img.src = url;
  });
}

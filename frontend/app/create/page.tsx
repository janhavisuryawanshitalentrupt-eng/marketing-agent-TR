"use client";

// Create was merged into Chat — this route just redirects to Chat (which now handles generation +
// "Your generations"). The persistent Shell also treats /create as the Chat view, so there's no flash.
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function CreatePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}

const OFFLINE_PLACEHOLDER_URLS = new Set(["", "offline", "demo"]);

export function getDefaultChatHistoryStorageMode(rawMode: string | undefined | null): "mock" | "auto" | "prisma" {
  const mode = rawMode?.trim();
  if (!mode) return "mock";
  if (mode === "auto" || mode === "mock" || mode === "prisma") return mode;
  return "mock";
}

export function shouldUseOfflineBackendFallback(rawUrl: string | undefined | null): boolean {
  const url = rawUrl?.trim();
  return !url || OFFLINE_PLACEHOLDER_URLS.has(url.toLowerCase());
}

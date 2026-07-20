import type { Platform } from "./types";

const TIKTOK_HOSTS = new Set(["tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"]);
const YOUTUBE_HOSTS = new Set(["youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);

// Client-side mirror of backend/app/downloader.py's detect_platform, scoped to
// only the two platforms profile-listing supports — enough to decide whether
// to try /api/list before falling back to the existing /api/analyze flow.
function detectListablePlatform(url: string): Platform | null {
  let hostname: string;
  try {
    hostname = new URL(url).hostname.toLowerCase().replace(/^www\./, "");
  } catch {
    return null;
  }
  if (TIKTOK_HOSTS.has(hostname)) return "tiktok";
  if (YOUTUBE_HOSTS.has(hostname)) return "youtube";
  return null;
}

// Client-side mirror of backend/app/downloader.py's is_profile_url — kept in
// sync manually. This is only a UX optimization (picks which endpoint to try
// first); the server re-checks authoritatively in POST /api/list.
export function isProfileUrl(url: string): boolean {
  const platform = detectListablePlatform(url);
  if (platform === null) return false;

  let path: string;
  try {
    path = new URL(url).pathname.replace(/\/+$/, "");
  } catch {
    return false;
  }

  if (platform === "tiktok") {
    return /^\/@[^/]+$/.test(path);
  }

  // youtube
  if (/\/watch(\/|$)/.test(path) || /^\/shorts\/[^/]+$/.test(path)) return false;
  return /^\/(@[^/]+|channel\/[^/]+|c\/[^/]+|user\/[^/]+)(\/videos|\/shorts|\/streams)?$/.test(
    path,
  );
}

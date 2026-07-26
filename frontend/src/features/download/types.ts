export type Platform = "tiktok" | "instagram" | "facebook" | "youtube" | "twitter";

export interface DownloadResult {
  platform: Platform;
  filename: string;
  blobUrl: string;
}

export interface ErrorResponse {
  status: "error";
  error_code: string;
  message: string;
}

export interface VideoQuality {
  height: number;
  label: string;
  ext: string;
}

export interface AudioQuality {
  bitrate: number;
  label: string;
}

export interface AnalyzeResponse {
  status: "success";
  platform: Platform;
  title: string | null;
  thumbnail: string | null;
  supports_quality_selection: boolean;
  video_qualities: VideoQuality[];
  audio_qualities: AudioQuality[];
}

export type Selection = { type: "video"; height: number } | { type: "audio"; bitrate: number };

export interface ProfileItem {
  id: string;
  title: string | null;
  thumbnail_url: string | null;
  url: string;
  view_count: number | null;
}

export interface ListResponse {
  status: "success";
  platform: Platform;
  items: ProfileItem[];
  truncated: boolean;
}

export const BATCH_MAX_ITEMS = 8;

export type Platform = "tiktok" | "instagram" | "facebook" | "youtube";

export interface DownloadResponse {
  status: "success";
  platform: Platform;
  files: string[];
  filenames: string[];
  preview_url: string | null;
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

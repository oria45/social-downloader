import { useState, useCallback, useRef } from "react";
import { API_BASE } from "./apiBase";
import type { DownloadResult, ErrorResponse, Platform } from "./types";

type BatchDownloadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: DownloadResult }
  | { status: "error"; error: ErrorResponse };

function extractFilename(contentDisposition: string | null): string {
  const match = contentDisposition?.match(/filename="?([^";]+)"?/);
  return match ? match[1] : "download";
}

function triggerBrowserSave(blobUrl: string, filename: string): void {
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function useBatchDownload() {
  const [state, setState] = useState<BatchDownloadState>({ status: "idle" });
  const blobUrlRef = useRef<string | null>(null);

  const downloadBatch = useCallback(async (urls: string[]) => {
    setState({ status: "loading" });
    try {
      const response = await fetch(`${API_BASE}/api/download-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls }),
      });

      if (!response.ok) {
        const body = await response.json();
        setState({ status: "error", error: body as ErrorResponse });
        return;
      }

      const blob = await response.blob();
      const filename = extractFilename(response.headers.get("content-disposition"));
      const platform = (response.headers.get("x-platform") ?? "tiktok") as Platform;

      if (blobUrlRef.current) URL.revokeObjectURL(blobUrlRef.current);
      const blobUrl = URL.createObjectURL(blob);
      blobUrlRef.current = blobUrl;

      triggerBrowserSave(blobUrl, filename);
      setState({ status: "success", result: { platform, filename, blobUrl } });
    } catch {
      setState({
        status: "error",
        error: {
          status: "error",
          error_code: "network_error",
          message: "Couldn't reach the server. Please try again.",
        },
      });
    }
  }, []);

  const reset = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    setState({ status: "idle" });
  }, []);

  return { state, downloadBatch, reset };
}

import { useState, useCallback } from "react";
import { API_BASE } from "./apiBase";
import type { DownloadResponse, ErrorResponse, Selection } from "./types";

type DownloadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: DownloadResponse }
  | { status: "error"; error: ErrorResponse };

export function useDownload() {
  const [state, setState] = useState<DownloadState>({ status: "idle" });

  const download = useCallback(async (url: string, selection?: Selection) => {
    setState({ status: "loading" });
    try {
      const response = await fetch(`${API_BASE}/api/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, selection: selection ?? null }),
      });
      const body = await response.json();
      if (!response.ok) {
        setState({ status: "error", error: body as ErrorResponse });
        return;
      }
      setState({ status: "success", result: body as DownloadResponse });
    } catch {
      setState({
        status: "error",
        error: {
          status: "error",
          error_code: "network_error",
          message: "Couldn't reach the local server. Is it still running?",
        },
      });
    }
  }, []);

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { state, download, reset };
}

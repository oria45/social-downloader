import { useCallback, useState } from "react";
import { API_BASE } from "./apiBase";
import type { AnalyzeResponse, ErrorResponse } from "./types";

type AnalyzeState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: AnalyzeResponse }
  | { status: "error"; error: ErrorResponse };

export function useAnalyze() {
  const [state, setState] = useState<AnalyzeState>({ status: "idle" });

  const analyze = useCallback(async (url: string) => {
    setState({ status: "loading" });
    try {
      const response = await fetch(`${API_BASE}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const body = await response.json();
      if (!response.ok) {
        setState({ status: "error", error: body as ErrorResponse });
        return;
      }
      setState({ status: "success", result: body as AnalyzeResponse });
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

  return { state, analyze, reset };
}

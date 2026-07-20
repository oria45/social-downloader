import { useCallback, useState } from "react";
import { API_BASE } from "./apiBase";
import type { ErrorResponse, ListResponse } from "./types";

type ListState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: ListResponse }
  | { status: "error"; error: ErrorResponse };

export function useListProfile() {
  const [state, setState] = useState<ListState>({ status: "idle" });

  const listProfile = useCallback(async (url: string) => {
    setState({ status: "loading" });
    try {
      const response = await fetch(`${API_BASE}/api/list`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const body = await response.json();
      if (!response.ok) {
        setState({ status: "error", error: body as ErrorResponse });
        return;
      }
      setState({ status: "success", result: body as ListResponse });
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

  const reset = useCallback(() => setState({ status: "idle" }), []);

  return { state, listProfile, reset };
}

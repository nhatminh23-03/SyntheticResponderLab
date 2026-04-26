"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { BackendReadinessPayload } from "@/lib/backend-readiness";

export type BackendReadinessState = BackendReadinessPayload & {
  isChecking: boolean;
  retry: () => void;
};

const MAX_AUTO_ATTEMPTS = 12;
const POLL_INTERVAL_MS = 5000;

const initialState: BackendReadinessPayload = {
  ready: false,
  status: "waking",
  message: "Starting backend... this may take up to a minute.",
};

export function useBackendReadiness(): BackendReadinessState {
  const [state, setState] = useState<BackendReadinessPayload>(initialState);
  const [isChecking, setIsChecking] = useState(true);
  const [retryToken, setRetryToken] = useState(0);
  const timeoutRef = useRef<number | null>(null);

  const retry = useCallback(() => {
    setState(initialState);
    setIsChecking(true);
    setRetryToken((value) => value + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    const clearPoll = () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };

    const poll = async () => {
      clearPoll();
      attempts += 1;
      setIsChecking(true);

      try {
        const response = await fetch("/api/readiness", { cache: "no-store" });
        const payload = (await response.json()) as BackendReadinessPayload;
        if (cancelled) {
          return;
        }

        setState(payload);
        if (payload.ready) {
          setIsChecking(false);
          return;
        }
      } catch {
        if (cancelled) {
          return;
        }
        setState(initialState);
      }

      if (attempts >= MAX_AUTO_ATTEMPTS) {
        setState({
          ready: false,
          status: "unavailable",
          message:
            "The backend is taking longer than expected to start. Please retry in a moment.",
        });
        setIsChecking(false);
        return;
      }

      timeoutRef.current = window.setTimeout(poll, POLL_INTERVAL_MS);
    };

    poll();

    return () => {
      cancelled = true;
      clearPoll();
    };
  }, [retryToken]);

  return {
    ...state,
    isChecking,
    retry,
  };
}

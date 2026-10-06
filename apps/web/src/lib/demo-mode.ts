"use client";

import { useSyncExternalStore } from "react";

/** Shared contract for the survey, interview and focus-group sections. */
export const DEMO_MODE_STORAGE_KEY = "srl:demo-mode";
export const DEMO_LABEL = "Demo session - pre-recorded, no AI";
export const DEMO_READ_ONLY = "Demo (no AI): read-only";
const EVENT = "srl-demo-mode-change";
let fallback = false;
let storageFailed = false;

export function isDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  if (storageFailed) return fallback;
  try { return window.localStorage.getItem(DEMO_MODE_STORAGE_KEY) === "true"; }
  catch { return fallback; }
}

export function setDemoMode(value: boolean) {
  fallback = value;
  try { window.localStorage.setItem(DEMO_MODE_STORAGE_KEY, String(value)); storageFailed = false; }
  catch { storageFailed = true; }
  window.dispatchEvent(new Event(EVENT));
}

function subscribe(listener: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key === DEMO_MODE_STORAGE_KEY || event.key === null) listener();
  };
  window.addEventListener(EVENT, listener);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(EVENT, listener);
    window.removeEventListener("storage", storage);
  };
}

export function useDemoMode(): readonly [boolean, typeof setDemoMode] {
  return [useSyncExternalStore(subscribe, isDemoMode, () => false), setDemoMode] as const;
}

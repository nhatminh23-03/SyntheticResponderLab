"use client";

import { useStudy } from "@/providers/study-provider";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { DEMO_LABEL, DEMO_READ_ONLY, useDemoMode } from "@/lib/demo-mode";

export function DemoSwitch() {
  const [demo, setDemo] = useDemoMode();
  return <div className="border-b border-app-border px-6 py-2" aria-label="App mode">
    <label className="inline-flex items-center gap-2 text-sm">
      <input type="checkbox" role="switch" checked={demo} onChange={e => setDemo(e.target.checked)} />
      Demo (no AI)
    </label>
  </div>;
}

const ActivityContext = createContext<(busy: boolean) => void>(() => undefined);
export function useDemoActivity(busy: boolean, demoPlayback: boolean) {
  const report = useContext(ActivityContext);
  useEffect(() => {
    if (demoPlayback) return;
    report(busy);
    return () => report(false);
  }, [busy, demoPlayback, report]);
}

/** Keep live and demo state in separate mounted screens, including unfinished drafts. */
export function DemoScreens({ children }: { children: (demo: boolean) => ReactNode }) {
  const [demo] = useDemoMode();
  const { studyId } = useStudy();
  const [pending, setPending] = useState(false);
  const [opened, setOpened] = useState(demo);
  if (demo && !opened) setOpened(true);
  return <ActivityContext.Provider value={setPending}>
    {demo && pending ? <p role="status" className="px-6 py-3">
      A live operation is finishing. Any model request already sent may incur cost;
      its result stays in the live session. Further automatic batch calls are paused.
      Turn Demo off and select Resume batch to continue paid work.
    </p> : null}
    <div key={`live:${studyId}`} hidden={demo}>{children(false)}</div>
    {opened ? <div key={`demo:${studyId}`} hidden={!demo}>{children(true)}</div> : null}
  </ActivityContext.Provider>;
}

export function DemoNotice({ provisional }: { provisional?: boolean }) {
  return <div role="note" className="rounded-xl border border-app-border p-4">
    <p>{DEMO_LABEL}</p><p>Synthetic rehearsal - not PA3.5 live fieldwork</p>
    <p>{DEMO_READ_ONLY}. Playback cost: $0.</p>
    {provisional ? <p>Provisional hand-written example; real model recording pending.</p> : null}
  </div>;
}

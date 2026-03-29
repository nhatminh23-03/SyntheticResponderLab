"use client";

import { PropsWithChildren } from "react";

import { SectionRegistryProvider } from "@/providers/section-registry-provider";
import { StudyProvider } from "@/providers/study-provider";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <StudyProvider>
      <SectionRegistryProvider>{children}</SectionRegistryProvider>
    </StudyProvider>
  );
}

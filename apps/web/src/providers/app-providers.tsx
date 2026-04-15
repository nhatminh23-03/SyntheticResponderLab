"use client";

import { PropsWithChildren } from "react";

import { SectionRegistryProvider } from "@/providers/section-registry-provider";
import { StudyProvider } from "@/providers/study-provider";
import { ThemeProvider } from "@/providers/theme-provider";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <ThemeProvider>
      <StudyProvider>
        <SectionRegistryProvider>{children}</SectionRegistryProvider>
      </StudyProvider>
    </ThemeProvider>
  );
}

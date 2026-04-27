import { SignedIn, SignedOut } from "@clerk/nextjs";

import { AnalysisSection } from "@/components/sections/analysis-section";
import { AudienceSection } from "@/components/sections/audience-section";
import { ExperimentSection } from "@/components/sections/experiment-section";
import { InsightsSection } from "@/components/sections/insights-section";
import { InterviewInsightsSection } from "@/components/sections/interview-insights-section";
import { InterviewSynthesisSection } from "@/components/sections/interview-synthesis-section";
import { MainHeroSection } from "@/components/sections/main-hero-section";
import { MarketSection } from "@/components/sections/market-section";
import { ProductSection } from "@/components/sections/product-section";
import { ResearchBriefSection } from "@/components/sections/research-brief-section";
import { RunSimulationSection } from "@/components/sections/run-simulation-section";
import { StudyModeSection } from "@/components/sections/study-mode-section";
import { SurveySection } from "@/components/sections/survey-section";
import { BackendReadinessGate } from "@/components/ui/backend-readiness";
import { AppShell } from "@/components/ui/app-shell";
import { PublicLandingShell } from "@/components/ui/public-landing-shell";
import { AppProviders } from "@/providers/app-providers";
import { isClerkConfigured } from "@/lib/server-env";

function AuthenticatedApp() {
  return (
    <AppProviders>
      <AppShell>
        <MainHeroSection />
        <StudyModeSection />
        <AudienceSection />
        <ProductSection />
        <MarketSection />
        <SurveySection />
        <ExperimentSection />
        <RunSimulationSection />
        <AnalysisSection />
        <InsightsSection />
        <InterviewSynthesisSection />
        <ResearchBriefSection />
        <InterviewInsightsSection />
      </AppShell>
    </AppProviders>
  );
}

export default function HomePage() {
  if (!isClerkConfigured()) {
    return (
      <BackendReadinessGate>
        <AuthenticatedApp />
      </BackendReadinessGate>
    );
  }

  return (
    <>
      <SignedOut>
        <PublicLandingShell />
      </SignedOut>
      <SignedIn>
        <BackendReadinessGate>
          <AuthenticatedApp />
        </BackendReadinessGate>
      </SignedIn>
    </>
  );
}

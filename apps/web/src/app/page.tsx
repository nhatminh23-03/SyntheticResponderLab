import { AnalysisSection } from "@/components/sections/analysis-section";
import { AudienceSection } from "@/components/sections/audience-section";
import { ExperimentSection } from "@/components/sections/experiment-section";
import { InsightsSection } from "@/components/sections/insights-section";
import { MainHeroSection } from "@/components/sections/main-hero-section";
import { MarketSection } from "@/components/sections/market-section";
import { ProductSection } from "@/components/sections/product-section";
import { RunSimulationSection } from "@/components/sections/run-simulation-section";
import { StudyModeSection } from "@/components/sections/study-mode-section";
import { SurveySection } from "@/components/sections/survey-section";
import { AppShell } from "@/components/ui/app-shell";
import { AppProviders } from "@/providers/app-providers";

export default function HomePage() {
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
      </AppShell>
    </AppProviders>
  );
}

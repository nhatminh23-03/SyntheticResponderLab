import { BadgeChip } from "@/components/ui/badge-chip";
import { formatSectionIndex } from "@/lib/utils";

type SectionHeaderProps = {
  index: number;
  eyebrow: string;
  title: string;
  description: string;
};

export function SectionHeader({
  index,
  eyebrow,
  title,
  description,
}: SectionHeaderProps) {
  return (
    <div className="max-w-2xl">
      <div className="mb-4 flex flex-wrap items-center gap-2.5 sm:mb-5 sm:gap-3">
        <BadgeChip tone="gold">{formatSectionIndex(index)}</BadgeChip>
        <BadgeChip>{eyebrow}</BadgeChip>
      </div>
      <h2 className="font-display text-[2.45rem] font-medium leading-[0.95] tracking-[-0.05em] text-app-text sm:text-[2.9rem] md:text-[3.35rem] lg:text-[3.75rem]">
        {title}
      </h2>
      <p className="mt-4 max-w-xl text-[0.98rem] leading-7 text-app-muted sm:mt-5 sm:text-base md:text-[1.02rem] lg:text-lg">
        {description}
      </p>
    </div>
  );
}

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
      <div className="mb-5 flex items-center gap-3">
        <BadgeChip tone="gold">{formatSectionIndex(index)}</BadgeChip>
        <BadgeChip>{eyebrow}</BadgeChip>
      </div>
      <h2 className="font-display text-4xl font-medium tracking-[-0.04em] text-app-text md:text-5xl">
        {title}
      </h2>
      <p className="mt-5 max-w-xl text-base leading-7 text-app-muted md:text-lg">
        {description}
      </p>
    </div>
  );
}

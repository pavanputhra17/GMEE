import React from 'react';
import { LucideIcon } from 'lucide-react';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle: string;
  icon: LucideIcon;
  accentColor: 'cyan' | 'emerald' | 'violet' | 'amber' | 'rose';
  trend?: string;
  trendPositive?: boolean;
}

/**
 * Color discipline: cards are ink-on-paper by default.
 * The brand-red icon tile is reserved for the primary service card ('cyan'
 * slot); all other accents stay grayscale or quiet status tints.
 */
const colorStyles = {
  cyan: {
    tile: 'bg-hermes-red text-hermes-bone',
    value: 'text-hermes-bone'
  },
  emerald: {
    tile: 'bg-hermes-panel text-hermes-red-bright',
    value: 'text-hermes-bone'
  },
  violet: {
    tile: 'bg-hermes-panel text-hermes-red-bright',
    value: 'text-hermes-bone'
  },
  amber: {
    tile: 'bg-hermes-panel text-hermes-red-bright',
    value: 'text-hermes-bone'
  },
  rose: {
    tile: 'bg-hermes-red-bright text-hermes-bone',
    value: 'text-hermes-red'
  }
};

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  accentColor,
  trend,
  trendPositive = true
}) => {
  const styles = colorStyles[accentColor];

  return (
    <div className="card-brutal-dark card-brutal-hover p-5 flex flex-col justify-between relative overflow-hidden group">
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className={`p-2.5 border border-hermes-ink/90 ${styles.tile}`}>
            <Icon className="w-5 h-5" />
          </div>

          {trend && (
            <span className={`chip-brutal border-hermes-ink/40 ${
              trendPositive ? 'bg-emerald-400/15 text-emerald-300' : 'bg-hermes-red-bright/15 text-hermes-red-bright'
            }`}>
              {trend}
            </span>
          )}
        </div>

        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-hermes-bone/50 font-mono">
          {title}
        </span>

        <div className={`text-3xl md:text-4xl font-display mt-1 mb-1 tracking-tight tabular-nums ${styles.value}`}>
          {value}
        </div>
      </div>

      <p className="text-xs text-hermes-bone/55 font-medium border-t border-hermes-bone/12 pt-3 mt-3 flex items-center justify-between gap-2">
        <span className="truncate">{subtitle}</span>
        <span className={`w-1.5 h-1.5 shrink-0 transition-colors group-hover:bg-hermes-bone ${accentColor === 'rose' ? 'bg-hermes-red-bright' : 'bg-hermes-bone/30'}`} />
      </p>
    </div>
  );
};

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

const colorStyles = {
  cyan: {
    tile: 'bg-hermes-red text-white',
    value: 'text-hermes-ink'
  },
  emerald: {
    tile: 'bg-emerald-700 text-white',
    value: 'text-emerald-700'
  },
  violet: {
    tile: 'bg-violet-700 text-white',
    value: 'text-violet-700'
  },
  amber: {
    tile: 'bg-amber-500 text-black',
    value: 'text-amber-600'
  },
  rose: {
    tile: 'bg-rose-600 text-white',
    value: 'text-rose-600'
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
    <div className="card-brutal card-brutal-hover p-5 flex flex-col justify-between relative overflow-hidden group">
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className={`p-2.5 border border-black/90 ${styles.tile}`}>
            <Icon className="w-5 h-5" />
          </div>

          {trend && (
            <span className={`chip-brutal border-black/40 ${
              trendPositive ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
            }`}>
              {trend}
            </span>
          )}
        </div>

        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-black/50 font-mono">
          {title}
        </span>

        <div className={`text-3xl md:text-4xl font-display mt-1 mb-1 tracking-tight tabular-nums ${styles.value}`}>
          {value}
        </div>
      </div>

      <p className="text-xs text-black/60 font-medium border-t border-black/15 pt-3 mt-3 flex items-center justify-between gap-2">
        <span className="truncate">{subtitle}</span>
        <span className={`w-1.5 h-1.5 shrink-0 transition-colors group-hover:bg-black ${accentColor === 'rose' ? 'bg-rose-600' : accentColor === 'amber' ? 'bg-amber-500' : 'bg-black/30'}`} />
      </p>
    </div>
  );
};

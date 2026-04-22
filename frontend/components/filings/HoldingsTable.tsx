"use client";

import type { Holding, ChangeType } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { formatUsd, formatShares, formatDelta, cn } from "@/lib/utils";

const CHANGE_BADGE: Record<ChangeType, { label: string; variant: "new" | "increased" | "decreased" | "exited" | "secondary" }> = {
  new:       { label: "New",       variant: "new" },
  increased: { label: "↑ Added",  variant: "increased" },
  decreased: { label: "↓ Trimmed", variant: "decreased" },
  exited:    { label: "Exited",   variant: "exited" },
  unchanged: { label: "—",        variant: "secondary" },
};

interface Props {
  holdings: Holding[];
  highlightChanges?: boolean;
}

export function HoldingsTable({ holdings, highlightChanges = true }: Props) {
  if (holdings.length === 0) {
    return <p className="text-sm text-muted-foreground py-6 text-center">No holdings data.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Issuer</th>
            <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Shares</th>
            <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Value</th>
            <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Δ Shares</th>
            {highlightChanges && (
              <th className="text-right px-4 py-2.5 font-medium text-muted-foreground">Change</th>
            )}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const change = h.change_type ? CHANGE_BADGE[h.change_type] : null;
            const isExited = h.change_type === "exited";
            return (
              <tr
                key={h.id}
                className={cn(
                  "border-b border-border/50 hover:bg-accent/30 transition-colors",
                  isExited && "opacity-50"
                )}
              >
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    {h.ticker && (
                      <span className="font-mono text-xs font-bold text-primary">{h.ticker}</span>
                    )}
                    <span className="text-foreground truncate max-w-[200px]">{h.issuer_name}</span>
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">
                  {formatShares(h.shares)}
                </td>
                <td className="px-4 py-2.5 text-right font-mono">
                  {formatUsd(h.market_value_usd)}
                </td>
                <td className={cn(
                  "px-4 py-2.5 text-right font-mono text-xs",
                  h.shares_delta && h.shares_delta > 0 ? "text-emerald-400" : "",
                  h.shares_delta && h.shares_delta < 0 ? "text-red-400" : "text-muted-foreground"
                )}>
                  {formatDelta(h.shares_delta)}
                  {h.pct_delta != null && (
                    <span className="ml-1 text-muted-foreground">
                      ({h.pct_delta > 0 ? "+" : ""}{h.pct_delta}%)
                    </span>
                  )}
                </td>
                {highlightChanges && (
                  <td className="px-4 py-2.5 text-right">
                    {change && change.variant !== "secondary" && (
                      <Badge variant={change.variant}>{change.label}</Badge>
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

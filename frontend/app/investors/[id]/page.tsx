"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ChevronDown, ChevronRight } from "lucide-react";
import { investorsApi, holdingsApi, type Investor, type Filing, type Holding } from "@/lib/api";
import { FilingCard } from "@/components/filings/FilingCard";
import { HoldingsTable } from "@/components/filings/HoldingsTable";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function InvestorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const investorId = Number(id);

  const [investor, setInvestor] = useState<Investor | null>(null);
  const [filings, setFilings] = useState<Filing[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      investorsApi.get(investorId),
      investorsApi.filings(investorId),
    ]).then(([inv, fil]) => {
      setInvestor(inv);
      setFilings(fil);
    }).finally(() => setLoading(false));
  }, [investorId]);

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-10 w-64 rounded bg-card animate-pulse" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 rounded-lg bg-card animate-pulse" />
        ))}
      </div>
    );
  }

  if (!investor) {
    return <p className="text-muted-foreground">Investor not found.</p>;
  }

  const ACTIVIST_TYPES = new Set([
    "SC 13D","SC 13D/A","SC 13G","SC 13G/A",
    "SCHEDULE 13D","SCHEDULE 13D/A","SCHEDULE 13G","SCHEDULE 13G/A",
  ]);
  const activist = filings.filter((f) => ACTIVIST_TYPES.has(f.filing_type));
  const quarterly = filings.filter((f) => f.filing_type === "13F-HR");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">{investor.display_name ?? investor.name}</h1>
        <p className="text-xs text-muted-foreground font-mono mt-1">CIK {investor.cik}</p>
      </div>

      {/* 13D/G activist filings */}
      {activist.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Activist Filings (13D/G)
          </h2>
          <div className="space-y-2">
            {activist.map((f) => (
              <FilingCard key={f.id} filing={f} />
            ))}
          </div>
        </section>
      )}

      {/* 13F quarterly filings */}
      {quarterly.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Quarterly Holdings (13F)
          </h2>
          <div className="space-y-3">
            {quarterly.map((f) => (
              <QuarterlyFilingRow key={f.id} filing={f} />
            ))}
          </div>
        </section>
      )}

      {filings.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No filings yet. Trigger a sync or wait for the next scheduled run.
        </p>
      )}
    </div>
  );
}

/**
 * 13F filers with multiple managed sub-accounts report the same CUSIP once per
 * sub-account (different otherManager values). Aggregate them into a single row
 * per security so the table isn't full of duplicates.
 */
function aggregateHoldings(raw: Holding[]): Holding[] {
  const map = new Map<string, Holding>();
  for (const h of raw) {
    const key = h.cusip ?? `name:${h.issuer_name}`;
    const existing = map.get(key);
    if (!existing) {
      map.set(key, { ...h });
    } else {
      existing.shares = (existing.shares ?? 0) + (h.shares ?? 0);
      existing.market_value_usd = (existing.market_value_usd ?? 0) + (h.market_value_usd ?? 0);
      if (existing.shares_delta != null || h.shares_delta != null) {
        existing.shares_delta = (existing.shares_delta ?? 0) + (h.shares_delta ?? 0);
      }
      // Keep the most significant change_type across sub-accounts
      const rank: Record<string, number> = { new: 4, increased: 3, decreased: 2, exited: 1, unchanged: 0 };
      const eRank = existing.change_type ? (rank[existing.change_type] ?? 0) : -1;
      const hRank = h.change_type ? (rank[h.change_type] ?? 0) : -1;
      if (hRank > eRank) existing.change_type = h.change_type;
    }
  }
  // Sort by market value descending
  return Array.from(map.values()).sort((a, b) => (b.market_value_usd ?? 0) - (a.market_value_usd ?? 0));
}

function QuarterlyFilingRow({ filing }: { filing: Filing }) {
  const [open, setOpen] = useState(false);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loadingHoldings, setLoadingHoldings] = useState(false);

  const toggle = async () => {
    if (!open && holdings.length === 0) {
      setLoadingHoldings(true);
      holdingsApi.filingHoldings(filing.id)
        .then((raw) => setHoldings(aggregateHoldings(raw)))
        .finally(() => setLoadingHoldings(false));
    }
    setOpen((v) => !v);
  };

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-accent/30 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          {open ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
          <span className="text-sm font-medium">
            Q ending {formatDate(filing.period_of_report)}
          </span>
          <span className="text-xs text-muted-foreground">Filed {formatDate(filing.filing_date)}</span>
        </div>
        {filing.diff_summary && (
          <div className="flex gap-2">
            {filing.diff_summary.new > 0 && <Badge variant="new">+{filing.diff_summary.new}</Badge>}
            {filing.diff_summary.increased > 0 && <Badge variant="increased">↑{filing.diff_summary.increased}</Badge>}
            {filing.diff_summary.decreased > 0 && <Badge variant="decreased">↓{filing.diff_summary.decreased}</Badge>}
            {filing.diff_summary.exited > 0 && <Badge variant="exited">✕{filing.diff_summary.exited}</Badge>}
          </div>
        )}
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          {loadingHoldings ? (
            <div className="h-24 animate-pulse bg-muted/30 rounded" />
          ) : (
            <HoldingsTable holdings={holdings} />
          )}
        </div>
      )}
    </div>
  );
}

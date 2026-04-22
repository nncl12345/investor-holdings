"use client";

import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { holdingsApi, type Filing } from "@/lib/api";
import { FilingCard } from "@/components/filings/FilingCard";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

type Category = "" | "13D" | "13D/A" | "13G" | "13G/A";

const FILTERS: { label: string; value: Category }[] = [
  { label: "All", value: "" },
  { label: "13D (Activist)", value: "13D" },
  { label: "13D/A", value: "13D/A" },
  { label: "13G (Passive)", value: "13G" },
  { label: "13G/A", value: "13G/A" },
];

function matchesCategory(filing: Filing, category: Category): boolean {
  if (!category) return true;
  const t = filing.filing_type;
  if (category === "13D")   return t === "SC 13D"   || t === "SCHEDULE 13D";
  if (category === "13D/A") return t === "SC 13D/A" || t === "SCHEDULE 13D/A";
  if (category === "13G")   return t === "SC 13G"   || t === "SCHEDULE 13G";
  if (category === "13G/A") return t === "SC 13G/A" || t === "SCHEDULE 13G/A";
  return true;
}

export default function FeedPage() {
  const [filings, setFilings] = useState<Filing[]>([]);
  const [allFilings, setAllFilings] = useState<Filing[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<Category>("");
  const [ticker, setTicker] = useState("");
  const [tickerInput, setTickerInput] = useState("");

  useEffect(() => {
    setLoading(true);
    holdingsApi
      .feed({ ticker: ticker || undefined, limit: 100 })
      .then((data) => { setAllFilings(data); })
      .finally(() => setLoading(false));
  }, [ticker]);

  useEffect(() => {
    setFilings(allFilings.filter((f) => matchesCategory(f, category)));
  }, [allFilings, category]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Activist Feed</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Live 13D/G filings from SEC EDGAR — real-time activist and passive disclosures
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setCategory(f.value)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                category === f.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-secondary text-secondary-foreground hover:bg-accent"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <form
          className="flex gap-2 ml-auto"
          onSubmit={(e) => {
            e.preventDefault();
            setTicker(tickerInput.toUpperCase());
          }}
        >
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              placeholder="Filter by ticker…"
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              className="pl-8 w-40"
            />
          </div>
          {ticker && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => { setTicker(""); setTickerInput(""); }}
            >
              Clear
            </Button>
          )}
        </form>
      </div>

      {/* Feed */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-20 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : filings.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <p>No filings found.</p>
          <p className="text-xs mt-1">Add investors to start tracking, or wait for new filings to drop.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filings.map((f) => (
            <FilingCard key={f.id} filing={f} investorName={f.investor_name ?? undefined} />
          ))}
        </div>
      )}
    </div>
  );
}

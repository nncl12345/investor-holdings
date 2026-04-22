"use client";

import { useState } from "react";
import Link from "next/link";
import { ExternalLink, Sparkles, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { holdingsApi, type Filing, type FilingType } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { formatDate, formatNumber } from "@/lib/utils";

const ACTIVIST_TYPES: FilingType[] = [
  "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A",
  "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A",
];

const FILING_LABEL: Record<FilingType, string> = {
  "SC 13D": "13D",
  "SC 13D/A": "13D/A",
  "SC 13G": "13G",
  "SC 13G/A": "13G/A",
  "SCHEDULE 13D": "13D",
  "SCHEDULE 13D/A": "13D/A",
  "SCHEDULE 13G": "13G",
  "SCHEDULE 13G/A": "13G/A",
  "13F-HR": "13F",
  "13F-HR/A": "13F/A",
};

function filingVariant(type: FilingType) {
  if (type === "SC 13D" || type === "SC 13D/A" || type === "SCHEDULE 13D" || type === "SCHEDULE 13D/A") return "activist";
  if (type === "SC 13G" || type === "SC 13G/A" || type === "SCHEDULE 13G" || type === "SCHEDULE 13G/A") return "passive";
  return "secondary";
}

interface Props {
  filing: Filing;
  investorName?: string;
}

export function FilingCard({ filing: initialFiling, investorName }: Props) {
  const [filing, setFiling] = useState(initialFiling);
  const [researching, setResearching] = useState(false);
  const [researchOpen, setResearchOpen] = useState(!!initialFiling.research_summary);

  const resolvedInvestorName = investorName ?? filing.investor_name ?? null;
  const isActivist = ACTIVIST_TYPES.includes(filing.filing_type);

  const handleResearch = async () => {
    if (filing.research_summary) {
      setResearchOpen((v) => !v);
      return;
    }
    setResearching(true);
    setResearchOpen(true);
    try {
      const updated = await holdingsApi.researchFiling(filing.id);
      setFiling(updated);
    } catch (e) {
      console.error("Research failed", e);
    } finally {
      setResearching(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4 hover:border-primary/40 transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Company + ticker */}
          <div className="flex items-center gap-2 mb-1">
            {filing.subject_company_ticker && (
              <span className="font-mono text-sm font-bold text-primary">
                {filing.subject_company_ticker}
              </span>
            )}
            <span className="text-sm font-medium text-foreground truncate">
              {filing.subject_company_name ?? "—"}
            </span>
          </div>

          {/* Investor name */}
          {resolvedInvestorName && (
            <p className="text-xs text-muted-foreground mb-2">
              Filed by{" "}
              <Link
                href={`/investors/${filing.investor_id}`}
                className="text-foreground hover:text-primary transition-colors"
              >
                {resolvedInvestorName}
              </Link>
            </p>
          )}

          {/* CUSIP */}
          {filing.subject_company_cusip && (
            <p className="text-xs text-muted-foreground font-mono">
              CUSIP: {filing.subject_company_cusip}
            </p>
          )}
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="flex items-center gap-2">
            <Badge variant={filingVariant(filing.filing_type)}>
              {FILING_LABEL[filing.filing_type]}
            </Badge>
            {filing.raw_url && (
              <a
                href={filing.raw_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-primary transition-colors"
                title="View on EDGAR"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          <span className="text-xs text-muted-foreground">{formatDate(filing.filing_date)}</span>
        </div>
      </div>

      {/* 13D/G position details */}
      {isActivist && (filing.shares_owned != null || filing.pct_owned != null) && (
        <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-4 text-xs text-muted-foreground">
          {filing.pct_owned != null && (
            <span>
              <span className="text-foreground font-medium">{filing.pct_owned.toFixed(1)}%</span>
              {" "}of class
            </span>
          )}
          {filing.shares_owned != null && (
            <span>
              <span className="text-foreground font-medium">{formatNumber(filing.shares_owned)}</span>
              {" "}shares
            </span>
          )}
          <span className="text-emerald-500 font-medium">Long</span>
        </div>
      )}

      {/* Investment thesis — Groq summary or raw Item 4 */}
      {isActivist && (filing.transaction_summary || filing.transaction_purpose) && (
        <p className="mt-2 text-xs text-muted-foreground line-clamp-3 leading-relaxed">
          {filing.transaction_summary ?? filing.transaction_purpose}
        </p>
      )}

      {/* Deep research section */}
      {isActivist && (
        <div className="mt-3 pt-3 border-t border-border">
          <button
            onClick={handleResearch}
            disabled={researching}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-primary transition-colors disabled:opacity-50"
          >
            {researching ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Sparkles className="w-3.5 h-3.5" />
            )}
            {researching
              ? "Researching…"
              : filing.research_summary
              ? (researchOpen ? (
                  <><span>Hide analysis</span><ChevronUp className="w-3 h-3" /></>
                ) : (
                  <><span>Show analysis</span><ChevronDown className="w-3 h-3" /></>
                ))
              : "Research this filing"}
          </button>

          {researchOpen && (
            <div className="mt-2">
              {researching ? (
                <div className="h-16 rounded bg-muted/30 animate-pulse" />
              ) : filing.research_summary ? (
                <p className="text-xs text-muted-foreground leading-relaxed whitespace-pre-line">
                  {filing.research_summary}
                </p>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* 13F diff summary */}
      {!isActivist && filing.diff_summary && (
        <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-2">
          {filing.diff_summary.new > 0 && (
            <Badge variant="new">+{filing.diff_summary.new} new</Badge>
          )}
          {filing.diff_summary.increased > 0 && (
            <Badge variant="increased">↑ {filing.diff_summary.increased}</Badge>
          )}
          {filing.diff_summary.decreased > 0 && (
            <Badge variant="decreased">↓ {filing.diff_summary.decreased}</Badge>
          )}
          {filing.diff_summary.exited > 0 && (
            <Badge variant="exited">✕ {filing.diff_summary.exited} exited</Badge>
          )}
        </div>
      )}
    </div>
  );
}

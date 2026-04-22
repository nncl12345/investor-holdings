"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, RefreshCw } from "lucide-react";
import { investorsApi, type Investor } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function InvestorsPage() {
  const [investors, setInvestors] = useState<Investor[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [cik, setCik] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    investorsApi.list().then(setInvestors).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cik || !name) return;
    setSubmitting(true);
    try {
      await investorsApi.create({ cik: cik.padStart(10, "0"), name });
      setCik(""); setName(""); setShowForm(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Investors</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Tracked institutional investors — add by SEC CIK number
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="w-3.5 h-3.5" />
          Add investor
        </Button>
      </div>

      {showForm && (
        <form
          onSubmit={handleAdd}
          className="rounded-lg border border-border bg-card p-4 flex flex-wrap gap-3 items-end"
        >
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">CIK</label>
            <Input
              placeholder="e.g. 0001067983"
              value={cik}
              onChange={(e) => setCik(e.target.value)}
              className="w-40"
            />
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[160px]">
            <label className="text-xs text-muted-foreground">Display name</label>
            <Input
              placeholder="e.g. Berkshire Hathaway"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={submitting || !cik || !name}>
            {submitting ? "Adding…" : "Add"}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
            Cancel
          </Button>
        </form>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : investors.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">
          No investors tracked yet. Add one above.
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          {investors.map((inv, i) => (
            <div
              key={inv.id}
              className={`flex items-center justify-between px-4 py-3 hover:bg-accent/30 transition-colors ${
                i !== 0 ? "border-t border-border/50" : ""
              }`}
            >
              <div>
                <Link
                  href={`/investors/${inv.id}`}
                  className="font-medium text-foreground hover:text-primary transition-colors"
                >
                  {inv.display_name ?? inv.name}
                </Link>
                <p className="text-xs text-muted-foreground font-mono mt-0.5">CIK {inv.cik}</p>
              </div>
              <div className="flex items-center gap-3">
                {inv.latest_filing_date && (
                  <span className="text-xs text-muted-foreground">
                    Last filing: {formatDate(inv.latest_filing_date)}
                  </span>
                )}
                {inv.latest_filing_type && (
                  <Badge variant="secondary">{inv.latest_filing_type}</Badge>
                )}
                <SyncButton investorId={inv.id} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SyncButton({ investorId }: { investorId: number }) {
  const [syncing, setSyncing] = useState(false);
  const handleSync = async () => {
    setSyncing(true);
    try { await investorsApi.sync(investorId); }
    finally { setTimeout(() => setSyncing(false), 2000); }
  };
  return (
    <Button variant="ghost" size="icon" onClick={handleSync} title="Sync 13F filings" disabled={syncing}>
      <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
    </Button>
  );
}

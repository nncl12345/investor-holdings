"use client";

import { useEffect, useState } from "react";
import { Bell, BellOff, Plus, Trash2 } from "lucide-react";
import { alertsApi, type Alert } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ investor_id: "", ticker: "", filing_type_filter: "", webhook_url: "" });
  const [submitting, setSubmitting] = useState(false);

  const load = () => {
    setLoading(true);
    alertsApi.list().then(setAlerts).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await alertsApi.create({
        investor_id: form.investor_id ? Number(form.investor_id) : undefined,
        ticker: form.ticker || undefined,
        filing_type_filter: form.filing_type_filter || undefined,
        webhook_url: form.webhook_url || undefined,
      });
      setForm({ investor_id: "", ticker: "", filing_type_filter: "", webhook_url: "" });
      setShowForm(false);
      load();
    } finally {
      setSubmitting(false);
    }
  };

  const toggleEnabled = async (alert: Alert) => {
    await alertsApi.update(alert.id, { enabled: !alert.enabled });
    load();
  };

  const remove = async (id: number) => {
    await alertsApi.delete(id);
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Alerts</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Watch investors or tickers — fire a webhook when a matching filing drops
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="w-3.5 h-3.5" />
          New alert
        </Button>
      </div>

      {showForm && (
        <form
          onSubmit={handleCreate}
          className="rounded-lg border border-border bg-card p-4 space-y-3"
        >
          <p className="text-xs text-muted-foreground">Fill in at least one of investor ID or ticker.</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Investor ID</label>
              <Input
                placeholder="e.g. 1"
                value={form.investor_id}
                onChange={(e) => setForm((f) => ({ ...f, investor_id: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Ticker</label>
              <Input
                placeholder="e.g. AAPL"
                value={form.ticker}
                onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value.toUpperCase() }))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Filing type filter</label>
              <Input
                placeholder="e.g. SC 13D"
                value={form.filing_type_filter}
                onChange={(e) => setForm((f) => ({ ...f, filing_type_filter: e.target.value }))}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Webhook URL</label>
              <Input
                placeholder="https://…"
                value={form.webhook_url}
                onChange={(e) => setForm((f) => ({ ...f, webhook_url: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={submitting || (!form.investor_id && !form.ticker)}>
              {submitting ? "Creating…" : "Create"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>Cancel</Button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-card animate-pulse" />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground text-sm">
          No alerts set up. Create one above.
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          {alerts.map((alert, i) => (
            <div
              key={alert.id}
              className={`flex items-center justify-between px-4 py-3 ${i !== 0 ? "border-t border-border/50" : ""} ${!alert.enabled ? "opacity-50" : ""}`}
            >
              <div className="flex items-center gap-3">
                <Bell className="w-4 h-4 text-muted-foreground shrink-0" />
                <div>
                  <div className="flex items-center gap-2 text-sm">
                    {alert.ticker && (
                      <span className="font-mono font-bold text-primary">{alert.ticker}</span>
                    )}
                    {alert.investor_id && (
                      <span className="text-muted-foreground">Investor #{alert.investor_id}</span>
                    )}
                    {alert.filing_type_filter && (
                      <Badge variant="secondary">{alert.filing_type_filter}</Badge>
                    )}
                    {!alert.enabled && <Badge variant="secondary">Paused</Badge>}
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {alert.webhook_url
                      ? `→ ${alert.webhook_url.slice(0, 50)}…`
                      : "No webhook — logged only"}
                    {alert.last_triggered_at && ` · Last fired ${formatDate(alert.last_triggered_at)}`}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => toggleEnabled(alert)}
                  title={alert.enabled ? "Pause" : "Enable"}
                >
                  {alert.enabled
                    ? <Bell className="w-3.5 h-3.5" />
                    : <BellOff className="w-3.5 h-3.5" />}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(alert.id)}
                  title="Delete"
                  className="text-destructive hover:text-destructive"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

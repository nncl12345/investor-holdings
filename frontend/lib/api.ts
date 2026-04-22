/**
 * Typed API client — thin fetch wrapper over the FastAPI backend.
 * All requests go through Next.js rewrites at /api/* → localhost:8000/*
 */

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types (mirroring the Pydantic schemas)
// ---------------------------------------------------------------------------

export type FilingType =
  | "SC 13D"
  | "SC 13D/A"
  | "SC 13G"
  | "SC 13G/A"
  | "SCHEDULE 13D"
  | "SCHEDULE 13D/A"
  | "SCHEDULE 13G"
  | "SCHEDULE 13G/A"
  | "13F-HR"
  | "13F-HR/A";

export type ChangeType =
  | "new"
  | "increased"
  | "decreased"
  | "exited"
  | "unchanged";

export interface Investor {
  id: number;
  cik: string;
  name: string;
  display_name: string | null;
  created_at: string;
  latest_filing_date: string | null;
  latest_filing_type: string | null;
}

export interface Holding {
  id: number;
  issuer_name: string;
  ticker: string | null;
  cusip: string | null;
  shares: number | null;
  market_value_usd: number | null;
  pct_of_class: number | null;
  change_type: ChangeType | null;
  shares_delta: number | null;
  pct_delta: number | null;
}

export interface DiffSummary {
  new: number;
  increased: number;
  decreased: number;
  exited: number;
  unchanged: number;
}

export interface Filing {
  id: number;
  investor_id: number;
  filing_type: FilingType;
  accession_number: string;
  filing_date: string;
  period_of_report: string | null;
  subject_company_name: string | null;
  subject_company_ticker: string | null;
  subject_company_cusip: string | null;
  raw_url: string | null;
  created_at: string;
  holdings: Holding[];
  diff_summary: DiffSummary | null;
  investor_name: string | null;
  shares_owned: number | null;
  pct_owned: number | null;
  transaction_purpose: string | null;
  transaction_summary: string | null;
  research_summary: string | null;
}

export interface Alert {
  id: number;
  investor_id: number | null;
  ticker: string | null;
  filing_type_filter: string | null;
  enabled: boolean;
  webhook_url: string | null;
  last_triggered_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Investors
// ---------------------------------------------------------------------------

export const investorsApi = {
  list: () => request<Investor[]>("/investors"),
  get: (id: number) => request<Investor>(`/investors/${id}`),
  create: (body: { cik: string; name: string; display_name?: string }) =>
    request<Investor>("/investors", { method: "POST", body: JSON.stringify(body) }),
  filings: (id: number, filingType?: string) => {
    const qs = filingType ? `?filing_type=${encodeURIComponent(filingType)}` : "";
    return request<Filing[]>(`/investors/${id}/filings${qs}`);
  },
  sync: (id: number) =>
    request<{ queued: boolean; cik: string }>(`/investors/${id}/sync`, { method: "POST" }),
};

// ---------------------------------------------------------------------------
// Holdings / Feed
// ---------------------------------------------------------------------------

export const holdingsApi = {
  feed: (params?: { filing_type?: string; ticker?: string; skip?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.filing_type) qs.set("filing_type", params.filing_type);
    if (params?.ticker) qs.set("ticker", params.ticker);
    if (params?.skip != null) qs.set("skip", String(params.skip));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    return request<Filing[]>(`/holdings/feed?${qs}`);
  },
  getFiling: (id: number) => request<Filing>(`/holdings/filings/${id}`),
  researchFiling: (id: number) => request<Filing>(`/holdings/filings/${id}/research`, { method: "POST" }),
  filingHoldings: (id: number, changeType?: ChangeType) => {
    const qs = changeType ? `?change_type=${changeType}` : "";
    return request<Holding[]>(`/holdings/filings/${id}/holdings${qs}`);
  },
  search: (ticker: string) =>
    request<Holding[]>(`/holdings/search?ticker=${encodeURIComponent(ticker)}`),
};

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export const alertsApi = {
  list: () => request<Alert[]>("/alerts"),
  create: (body: {
    investor_id?: number;
    ticker?: string;
    filing_type_filter?: string;
    webhook_url?: string;
  }) => request<Alert>("/alerts", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: { enabled?: boolean; webhook_url?: string }) =>
    request<Alert>(`/alerts/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (id: number) =>
    request<void>(`/alerts/${id}`, { method: "DELETE" }),
};

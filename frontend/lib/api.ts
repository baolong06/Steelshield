export type Policy = {
  id: string;
  name: string;
  statement_vi: string;
  oracle_type: string;
  allowed_examples: string[];
  forbidden_examples: string[];
};

export type Dataset = {
  version: string;
  status: string;
  total_cases: number;
  total_families: number;
  splits: Array<{ id: "train" | "calibration" | "evaluation_candidate"; case_count: number; purpose: string }>;
  hashes: Record<string, string>;
  integrity: Record<string, string>;
  notice: string;
};

export type Finding = {
  case_id: string;
  family_id: string;
  policy_id: string;
  suite: string;
  language_variant: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  decision: string;
  title: string;
  explanation: string;
  evidence: {
    synthetic_target: string;
    prompt_screen: { flagged: boolean; score: number; matches: string[] };
    oracle: { leaked: boolean; canary: { hits: string[] }; state: { violations: string[] } };
  };
};

export type RunTarget = "hardened" | "vulnerable" | "llm_hardened" | "llm_vulnerable";
export type RunMode = "fixture" | "llm";
export type Attacker = "replay" | "llm";

export type Run = {
  id: string;
  target: RunTarget;
  created_at: string;
  split: string;
  policy_ids: string[];
  review_status: string;
  claim_level: string;
  source_notice: string;
  manifest_version: string;
  status: "queued" | "running" | "completed" | "failed";
  mode: RunMode;
  attacker: Attacker;
  egress_host: string | null;
  error: string | null;
  metrics: {
    total_cases: number;
    attack_cases: number;
    benign_cases: number;
    risk_detected: number;
    blocked: number;
    allowed: number;
    false_positives: number;
    false_negatives: number;
    precision: number;
    recall: number;
    false_positive_rate: number;
    external_requests: number;
    external_bytes: number;
    failed_cases: number;
  };
  findings: Finding[];
};

export type LlmHealth = {
  status: string;
  key_configured: boolean;
  configured: boolean;
  model: string;
  egress_host: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getPolicies() {
  return request<{ items: Policy[] }>("/policies");
}

export function getDatasets() {
  return request<Dataset>("/datasets");
}

export function getLlmHealth() {
  return request<LlmHealth>("/llm/health");
}

export function createRun(input: {
  split: string;
  policy_ids: string[];
  limit?: number;
  target: RunTarget;
  mode: RunMode;
  attacker: Attacker;
}) {
  return request<Run>("/runs", { method: "POST", body: JSON.stringify(input) });
}

export function getRun(runId: string) {
  return request<Run>(`/runs/${encodeURIComponent(runId)}`);
}

export function reportUrl(runId: string, format: "csv" | "xlsx") {
  return `/api/v1/reports/${encodeURIComponent(runId)}/${format}`;
}

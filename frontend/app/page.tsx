"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { FindingsTable } from "@/components/findings-table";
import { RunWizard } from "@/components/run-wizard";
import { TransparencyCards } from "@/components/transparency-cards";
import { getDatasets, getPolicies, getRun, reportUrl, type Dataset, type Policy, type Run } from "@/lib/api";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForRun(run: Run): Promise<Run> {
  let current = run;
  for (let attempt = 0; attempt < 120; attempt += 1) {
    if (current.status !== "queued" && current.status !== "running") {
      return current;
    }
    await sleep(1500);
    current = await getRun(current.id);
  }
  return current;
}

export default function DashboardPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [datasets, setDatasets] = useState<Dataset | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    Promise.all([getPolicies(), getDatasets()])
      .then(([policyResponse, datasetResponse]) => {
        setPolicies(policyResponse.items);
        setDatasets(datasetResponse);
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Không thể kết nối backend local."));
  }, []);

  async function handleComplete(next: Run) {
    window.sessionStorage.setItem("steelshield-last-run", JSON.stringify(next));
    setRun(next);
    if (next.status === "queued" || next.status === "running") {
      setPolling(true);
      try {
        const finished = await waitForRun(next);
        window.sessionStorage.setItem("steelshield-last-run", JSON.stringify(finished));
        setRun(finished);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Không theo dõi được run.");
      } finally {
        setPolling(false);
      }
    }
  }

  const egressLabel = run?.mode === "llm"
    ? `Server-configured egress → ${run.egress_host ?? "unavailable"}`
    : "Offline · 0 external request";

  return (
    <AppShell>
      <section className="hero">
        <p className="eyebrow">Steelshield · Agent control plane</p>
        <h1>Đo hành vi policy bằng canary và state oracle.</h1>
        <p>
          Fixture chạy hoàn toàn local. LLM mode cho attacker/target gọi HTTPS gateway do server cấu hình,
          tool chỉ là sandbox synthetic. Không quét chatbot ngoài, không nhận URL target,
          không tự nhận là bằng chứng production hay competition.
        </p>
      </section>
      <TransparencyCards />
      {error && <p className="notice" role="alert">Backend local: {error}</p>}
      {datasets && (
        <RunWizard
          policies={policies}
          datasets={datasets}
          onComplete={handleComplete}
        />
      )}
      {!datasets && !error && <p className="empty">Đang tải catalog local…</p>}
      {run && (
        <section style={{ marginTop: "1rem" }}>
          <div className="stat-row">
            <div className="stat"><strong>{run.status}</strong><span>{polling ? "đang chờ worker" : run.mode}</span></div>
            <div className="stat"><strong>{run.metrics.total_cases}</strong><span>synthetic cases</span></div>
            <div className="stat"><strong>{run.metrics.blocked}</strong><span>attacks blocked</span></div>
            <div className="stat"><strong>{run.metrics.allowed}</strong><span>benign allowed</span></div>
            <div className="stat"><strong>{run.metrics.failed_cases ?? 0}</strong><span>failed / not-run</span></div>
            <div className="stat"><strong>{run.metrics.external_requests}</strong><span>{egressLabel}</span></div>
          </div>
          <div className="panel" style={{ marginTop: "1rem" }}>
            <p className="eyebrow">Run {run.id}</p>
            <h2>{run.claim_level}</h2>
            <p>{run.source_notice}</p>
            {run.error && <p className="notice" role="alert">{run.error}</p>}
            <div style={{ display: "flex", gap: "0.75rem", margin: "0.9rem 0" }}>
              <a className="primary" style={{ display: "inline-block" }} href={`/runs/${run.id}`}>Xem run</a>
              <a className="primary" style={{ display: "inline-block" }} href={reportUrl(run.id, "csv")}>Tải CSV</a>
              <a className="primary" style={{ display: "inline-block" }} href={reportUrl(run.id, "xlsx")}>Tải Excel</a>
            </div>
            <FindingsTable findings={run.findings} />
          </div>
        </section>
      )}
    </AppShell>
  );
}

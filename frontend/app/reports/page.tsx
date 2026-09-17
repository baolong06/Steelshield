"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { reportUrl, type Run } from "@/lib/api";

export default function ReportsPage() {
  const [run, setRun] = useState<Run | null>(null);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const stored = window.sessionStorage.getItem("steelshield-last-run");
    if (stored) {
      const parsed = JSON.parse(stored) as Run;
      setRun(parsed);
      setRunId(parsed.id);
    }
  }, []);

  function openReport(format: "csv" | "xlsx") {
    if (!runId.trim()) { setError("Nhập run ID từ Dashboard trước khi export."); return; }
    window.location.assign(reportUrl(runId.trim(), format));
  }

  return (
    <AppShell>
      <section className="hero"><p className="eyebrow">Report export</p><h1>Xuất evidence local, có provenance.</h1><p>CSV và Excel ghi rõ version, review status, claim level, metrics, findings; ô text có bảo vệ formula injection.</p></section>
      <section className="panel">
        <label>Run ID <input value={runId} placeholder="run-…" onChange={(event) => setRunId(event.target.value)} /></label>
        {run && <p style={{ marginTop: "0.75rem" }}>{run.claim_level}</p>}
        <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}><button className="primary" type="button" onClick={() => openReport("csv")}>Tải CSV</button><button className="primary" type="button" onClick={() => openReport("xlsx")}>Tải Excel</button></div>
        {error && <p role="alert" style={{ color: "#ffb4c8", marginTop: "0.75rem" }}>{error}</p>}
      </section>
    </AppShell>
  );
}

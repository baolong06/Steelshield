import type { Finding } from "@/lib/api";
import { SeverityBadge } from "./severity-badge";

export function FindingsTable({ findings }: { findings: Finding[] }) {
  if (!findings.length) {
    return <p className="empty">Không có finding. Đây không phải kết luận an toàn cho hệ thống thật.</p>;
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Case</th>
            <th>Policy</th>
            <th>Suite / ngôn ngữ</th>
            <th>Severity</th>
            <th>Verdict</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => (
            <tr key={finding.case_id}>
              <td>
                <strong>{finding.case_id}</strong>
                <span>{finding.title}</span>
              </td>
              <td>{finding.policy_id}</td>
              <td>
                {finding.suite}
                <span>{finding.language_variant}</span>
              </td>
              <td><SeverityBadge severity={finding.severity} /></td>
              <td>{finding.decision}</td>
              <td>
                {finding.evidence.oracle.leaked ? "Oracle xác nhận leak/state transition" : "Prompt rule match"}
                {finding.evidence.oracle.state.violations.length > 0 && (
                  <span>{finding.evidence.oracle.state.violations.join(", ")}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

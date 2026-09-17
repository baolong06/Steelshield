import type { Finding } from "@/lib/api";

export function SeverityBadge({ severity }: { severity: Finding["severity"] }) {
  return <span className={`severity severity-${severity}`}>{severity}</span>;
}

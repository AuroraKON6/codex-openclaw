import fs from "node:fs";
import path from "node:path";

const RUN_ID_PATTERN = /^\d{8}_\d{6}_\d{3}$/;
const MAX_JSON_BYTES = 2 * 1024 * 1024;

function containedPath(root, ...parts) {
  const resolvedRoot = path.resolve(root);
  const candidate = path.resolve(resolvedRoot, ...parts);
  const relative = path.relative(resolvedRoot, candidate);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Path escapes the quant workspace");
  }
  return candidate;
}

function readJsonObject(filePath) {
  const stat = fs.lstatSync(filePath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > MAX_JSON_BYTES) {
    throw new Error(`Unsafe or oversized JSON artifact: ${path.basename(filePath)}`);
  }
  const value = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Expected a JSON object: ${path.basename(filePath)}`);
  }
  return value;
}

function optionalJson(runDir, ...parts) {
  const filePath = containedPath(runDir, ...parts);
  return fs.existsSync(filePath) ? readJsonObject(filePath) : {};
}

function severityFromAlerts(alertDocument) {
  const rank = { INFO: 0, WARNING: 1, ERROR: 2, CRITICAL: 3 };
  const alerts = Array.isArray(alertDocument.alerts) ? alertDocument.alerts : [];
  return alerts.reduce((current, alert) => {
    const severity = String(alert?.severity || "INFO").toUpperCase();
    return (rank[severity] ?? 0) > (rank[current] ?? 0) ? severity : current;
  }, "INFO");
}

function summarizeRun(runDir, state) {
  const alerts = optionalJson(runDir, "operations", "alerts.json");
  const candidate = optionalJson(runDir, "release", "release_candidate.json");
  const registry = state.business_controls?.experiment_registry_gate || {};
  return {
    run_id: String(state.run_id || path.basename(runDir)),
    mock: state.mock === true,
    runtime: String(state.runtime || "unknown"),
    status: String(state.status || "unknown"),
    agents: `${Number(state.success_count || 0)}/${Number(state.total_agents || 0)}`,
    data_mode: String(state.data_mode || "unknown"),
    total_tokens: Number(state.model_usage?.total_tokens || 0),
    estimated_cost_usd: Number(state.model_usage?.estimated_cost_usd || 0),
    release_status: String(candidate.status || "NOT_PREPARED"),
    experiment_registry_status: String(registry.status || "unavailable"),
    experiment_registry_id: String(registry.registry_id || "N/A"),
    experiment_ledger_integrity: registry.ledger_integrity_ok === true,
    alert_severity: severityFromAlerts(alerts),
    alert_count: Array.isArray(alerts.alerts) ? alerts.alerts.length : 0,
  };
}

export function collectQuantOpsStatus(cwd) {
  const workspace = path.resolve(cwd);
  const runsRoot = containedPath(workspace, "runs");
  const status = {
    schema_version: 1,
    mode: "interactive_operator_read_only",
    production_extensions_enabled: false,
    latest_real: null,
    latest_mock: null,
    disclaimer: "Operational metadata only; no market analysis or trading advice.",
  };
  if (!fs.existsSync(runsRoot)) return status;
  const rootStat = fs.lstatSync(runsRoot);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) {
    throw new Error("Runs root is not a safe directory");
  }

  const entries = fs
    .readdirSync(runsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && !entry.isSymbolicLink() && RUN_ID_PATTERN.test(entry.name))
    .sort((left, right) => right.name.localeCompare(left.name));

  for (const entry of entries) {
    const runDir = containedPath(runsRoot, entry.name);
    const statePath = containedPath(runDir, "state.json");
    if (!fs.existsSync(statePath)) continue;
    const state = readJsonObject(statePath);
    const summary = summarizeRun(runDir, state);
    if (summary.mock && !status.latest_mock) status.latest_mock = summary;
    if (!summary.mock && !status.latest_real) status.latest_real = summary;
    if (status.latest_real && status.latest_mock) break;
  }
  return status;
}

function formatRun(label, run) {
  if (!run) return `${label}: none`;
  const mockLabel = run.mock ? " [MOCK]" : "";
  return `${label}: ${run.run_id}${mockLabel} | ${run.status} | ${run.agents} | ${run.release_status} | experiment:${run.experiment_registry_status}`;
}

export default function quantOpsReadonlyExtension(pi) {
  pi.registerCommand("quant-status", {
    description: "Show read-only real/mock pipeline and release status",
    handler: async (args, ctx) => {
      if (args.trim().toLowerCase() === "clear") {
        ctx.ui.setWidget("quant-ops-readonly", undefined);
        ctx.ui.notify("Quant status cleared", "info");
        return;
      }
      try {
        const status = collectQuantOpsStatus(ctx.cwd);
        const real = status.latest_real;
        const lines = [
          "Quant Ops — read-only operator view",
          formatRun("REAL", real),
          formatRun("MOCK", status.latest_mock),
          `REAL alerts: ${real?.alert_severity || "N/A"} (${real?.alert_count || 0}) | tokens: ${real?.total_tokens || 0}`,
          "Production Agent extensions remain disabled. No market conclusions are displayed.",
        ];
        ctx.ui.setWidget("quant-ops-readonly", lines);
        ctx.ui.notify("Read-only quant status refreshed", real?.alert_severity === "CRITICAL" ? "warning" : "info");
      } catch (error) {
        ctx.ui.notify(`Quant status failed: ${error instanceof Error ? error.message : String(error)}`, "error");
      }
    },
  });
}

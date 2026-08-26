import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldAlert, ShieldCheck, ShieldOff, RefreshCw, AlertTriangle,
  CheckCircle2, XCircle, TrendingDown, Zap, Target, Activity,
  BarChart3, Lock, Unlock, FlaskConical
} from "lucide-react";

const VIRTUAL_API_BASE = import.meta.env.VITE_VIRTUAL_API_URL || "http://localhost:8001";

async function fetchRiskState() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/risk/state`);
    return res.ok ? res.json() : null;
  } catch { return null; }
}

async function fetchRiskConfig() {
  try {
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/risk/config`);
    return res.ok ? res.json() : null;
  } catch { return null; }
}

async function auditGate(params) {
  try {
    const sp = new URLSearchParams(params);
    const res = await fetch(`${VIRTUAL_API_BASE}/api/v1/virtual-trader/risk/audit-gate?${sp}`, { method: "POST" });
    return res.ok ? res.json() : null;
  } catch { return null; }
}

// ─── Risk Level Badge ────────────────────────────────────────────────────────

function RiskLevelBadge({ level, large = false }) {
  const cfg = {
    GREEN:   { cls: "bg-emerald-50 border-emerald-300 text-emerald-800", icon: ShieldCheck, label: "GREEN — All Clear" },
    AMBER:   { cls: "bg-amber-50 border-amber-300 text-amber-800",       icon: ShieldAlert, label: "AMBER — Caution" },
    RED:     { cls: "bg-red-50 border-red-300 text-red-700",             icon: ShieldAlert, label: "RED — High Risk" },
    HALTED:  { cls: "bg-red-100 border-red-400 text-red-900",            icon: ShieldOff,   label: "HALTED — Betting Suspended" },
    UNKNOWN: { cls: "bg-slate-100 border-slate-300 text-slate-600",      icon: ShieldAlert, label: "UNKNOWN" },
  };
  const { cls, icon: Icon, label } = cfg[level] || cfg.UNKNOWN;
  return (
    <div className={`flex items-center gap-2 border rounded-xl px-4 py-2.5 ${cls} ${large ? "text-sm font-black" : "text-xs font-bold"}`}>
      <Icon className={large ? "w-5 h-5" : "w-4 h-4"} />
      {label}
    </div>
  );
}

// ─── Gate Row ────────────────────────────────────────────────────────────────

function GateRow({ name, data }) {
  const passed = data?.status === "PASS";
  return (
    <div className={`flex items-center justify-between px-4 py-3 rounded-xl border ${
      passed ? "bg-emerald-50/50 border-emerald-100" : "bg-red-50 border-red-200"
    }`}>
      <div className="flex items-center gap-2.5">
        {passed
          ? <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          : <XCircle className="w-4 h-4 text-red-600 shrink-0" />
        }
        <span className="text-xs font-bold text-slate-700">{name}</span>
      </div>
      <div className="text-xs text-slate-500 font-mono text-right">
        {data?.value_pct != null && (
          <span className={data.status === "FAIL" ? "text-red-600 font-bold" : ""}>
            {data.value_pct}% / {data.limit_pct}%
          </span>
        )}
        {data?.value != null && data?.limit != null && (
          <span className={data.status === "FAIL" ? "text-red-600 font-bold" : ""}>
            {data.value} / {data.limit}
          </span>
        )}
        {data?.value === true || data?.value === false ? (
          <span className={data.value ? "text-red-600 font-bold" : "text-emerald-600"}>{String(data.value)}</span>
        ) : null}
      </div>
    </div>
  );
}

// ─── Progress Bar ────────────────────────────────────────────────────────────

function LimitBar({ label, value, limit, unit = "%", color = "blue" }) {
  const pct = limit > 0 ? Math.min(100, (value / limit) * 100) : 0;
  const barColor = pct >= 100 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : `bg-${color}-500`;
  return (
    <div>
      <div className="flex justify-between text-xs font-semibold mb-1">
        <span className="text-slate-600">{label}</span>
        <span className={pct >= 80 ? "text-red-600 font-bold" : "text-slate-500"}>
          {value}{unit} / {limit}{unit}
        </span>
      </div>
      <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ─── Kelly Calculator ────────────────────────────────────────────────────────

function KellyCalculator({ available }) {
  const [prob, setProb] = useState(0.65);
  const [odds, setOdds] = useState(1.85);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const calculate = async () => {
    setLoading(true);
    const res = await auditGate({ model_prob: prob, market_prob: prob - 0.05, odds });
    setResult(res);
    setLoading(false);
  };

  const b = odds - 1;
  const q = 1 - prob;
  const kellyFull = b > 0 ? (b * prob - q) / b : 0;
  const kellyHalf = kellyFull * 0.5;
  const stake = Math.max(0.5, Math.round(available * kellyHalf * 100) / 100);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <FlaskConical className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-bold text-slate-800">Kelly Stake Calculator</h3>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">
            Model Probability: <span className="text-blue-600">{(prob * 100).toFixed(0)}%</span>
          </label>
          <input type="range" min="0.3" max="0.95" step="0.01"
            value={prob} onChange={(e) => setProb(parseFloat(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">
            Decimal Odds: <span className="text-blue-600">{parseFloat(odds).toFixed(2)}</span>
          </label>
          <input type="range" min="1.10" max="5.0" step="0.05"
            value={odds} onChange={(e) => setOdds(parseFloat(e.target.value))}
            className="w-full accent-blue-600"
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <div className="bg-slate-50 rounded-xl p-3 border border-slate-200">
          <div className="text-xs text-slate-500 mb-1">Full Kelly</div>
          <div className={`text-lg font-black ${kellyFull > 0 ? "text-slate-800" : "text-red-500"}`}>
            {(kellyFull * 100).toFixed(2)}%
          </div>
        </div>
        <div className="bg-blue-50 rounded-xl p-3 border border-blue-200">
          <div className="text-xs text-blue-600 mb-1">½ Kelly (applied)</div>
          <div className="text-lg font-black text-blue-800">
            {(kellyHalf * 100).toFixed(2)}%
          </div>
        </div>
        <div className="bg-emerald-50 rounded-xl p-3 border border-emerald-200">
          <div className="text-xs text-emerald-600 mb-1">Computed Stake</div>
          <div className="text-lg font-black text-emerald-800">
            ₦{stake.toFixed(2)}
          </div>
        </div>
      </div>

      <div className="text-xs text-slate-400 font-mono bg-slate-50 p-3 rounded-lg">
        f* = (b·p − q) / b = ({b.toFixed(2)}×{prob.toFixed(2)} − {q.toFixed(2)}) / {b.toFixed(2)} = <span className="text-blue-600 font-bold">{kellyFull.toFixed(4)}</span>
        <br />½·f* × ₦{available?.toLocaleString("en-GB", {maximumFractionDigits: 0})} available = <span className="text-emerald-600 font-bold">₦{stake.toFixed(2)}</span>
      </div>

      {result && (
        <div className={`text-xs rounded-lg px-3 py-2 font-medium ${
          result.action === "ALLOW" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" :
          result.action === "BLOCK" ? "bg-red-50 text-red-700 border border-red-200" :
          "bg-amber-50 text-amber-700 border border-amber-200"
        }`}>
          Gate Audit: <strong>{result.action}</strong> — {result.reason}
        </div>
      )}

      <button
        onClick={calculate}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 text-xs font-bold px-4 py-2 bg-slate-900 text-white rounded-xl hover:bg-slate-700 transition-all disabled:opacity-60"
      >
        {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
        Run Gate Audit
      </button>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function VirtualRiskEngine() {
  const [state, setRiskState] = useState(null);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    const [s, c] = await Promise.all([fetchRiskState(), fetchRiskConfig()]);
    setRiskState(s);
    setConfig(c);
    setLastUpdate(new Date());
    if (!quiet) setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(() => load(true), 8000);
    return () => clearInterval(interval);
  }, [load]);

  const gates = state?.gates || {};
  const bankroll = state?.bankroll_snapshot || {};
  const limits = config?.limits || {};
  const kelly = config?.kelly || {};

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-base font-black text-slate-900 tracking-tight">
            Phase 6 · Risk Engine
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            9-gate pre-bet filter · Kelly stake sizing · Autonomous drawdown protection.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdate && <span className="text-xs text-slate-400">{lastUpdate.toLocaleTimeString()}</span>}
          <button onClick={() => load()} disabled={loading}
            className="flex items-center gap-1.5 text-xs font-bold px-3 py-2 border border-slate-200 rounded-lg hover:bg-slate-50 transition-all">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Current Risk Level */}
      {state && (
        <div className="flex items-center gap-4 flex-wrap">
          <RiskLevelBadge level={state.risk_level} large />
          {state.is_halted && (
            <div className="flex items-center gap-2 text-xs text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded-xl font-bold">
              <Lock className="w-3.5 h-3.5" />
              Bet firing is SUSPENDED until risk conditions resolve.
            </div>
          )}
          {!state.is_halted && state.risk_level === "GREEN" && (
            <div className="flex items-center gap-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-2 rounded-xl font-bold">
              <Unlock className="w-3.5 h-3.5" />
              All gates clear — paper bets firing normally.
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Left: Gates + Limits */}
        <div className="space-y-4">
          {/* Gate Status Panel */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-blue-600" />
              Risk Gate Status
            </h3>
            <div className="space-y-2">
              <GateRow name="G1 — Kill Switch" data={gates.G1_kill_switch} />
              <GateRow name="G3 — Daily Loss Limit" data={gates.G3_daily_loss} />
              <GateRow name="G4 — Max Drawdown" data={gates.G4_drawdown} />
              <GateRow name="G5 — Consecutive Losses" data={gates.G5_consecutive_losses} />
              <GateRow name="G6 — Open Exposure" data={gates.G6_open_exposure} />
            </div>
          </div>

          {/* Limit Meters */}
          {config && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-4">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <Activity className="w-4 h-4 text-blue-600" />
                Limit Utilisation
              </h3>
              <LimitBar
                label="Daily Loss"
                value={Math.abs(Math.min(0, bankroll.today_pl || 0))}
                limit={((bankroll.current_balance || 0) * limits.max_daily_loss_pct) / 100}
                unit=" ₦"
                color="red"
              />
              <LimitBar
                label="Drawdown"
                value={parseFloat((state?.gates?.G4_drawdown?.value_pct || 0).toFixed(1))}
                limit={kelly.max_drawdown_block_pct || 20}
                unit="%"
                color="orange"
              />
              <LimitBar
                label="Consecutive Losses"
                value={bankroll.consecutive_losses || 0}
                limit={limits.max_consecutive_losses || 5}
                unit=""
                color="amber"
              />
              <LimitBar
                label="Open Exposure"
                value={parseFloat((state?.gates?.G6_open_exposure?.value_pct || 0).toFixed(1))}
                limit={limits.max_open_exposure_pct || 3}
                unit="%"
                color="blue"
              />
            </div>
          )}
        </div>

        {/* Right: Bankroll snapshot + Kelly config + Calculator */}
        <div className="space-y-4">
          {/* Bankroll Snapshot */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-600" />
              Live Bankroll Snapshot
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "Current Balance", value: `₦${(bankroll.current_balance || 0).toLocaleString("en-GB", { minimumFractionDigits: 2 })}`, color: "slate" },
                { label: "Available", value: `₦${(bankroll.available_balance || 0).toLocaleString("en-GB", { minimumFractionDigits: 2 })}`, color: "green" },
                { label: "Open Exposure", value: `₦${(bankroll.total_exposure || 0).toFixed(2)}`, color: "amber" },
                { label: "Today P&L", value: `${(bankroll.today_pl || 0) >= 0 ? "+" : ""}₦${(bankroll.today_pl || 0).toFixed(2)}`, color: (bankroll.today_pl || 0) >= 0 ? "green" : "red" },
                { label: "Cumulative ROI", value: `${(bankroll.cumulative_roi_pct || 0) >= 0 ? "+" : ""}${bankroll.cumulative_roi_pct || 0}%`, color: (bankroll.cumulative_roi_pct || 0) >= 0 ? "green" : "red" },
                { label: "Loss Streak", value: bankroll.consecutive_losses || 0, color: (bankroll.consecutive_losses || 0) >= 3 ? "red" : "slate" },
              ].map(({ label, value, color }) => {
                const palette = { green: "bg-emerald-50 text-emerald-800", red: "bg-red-50 text-red-800", amber: "bg-amber-50 text-amber-800", slate: "bg-slate-50 text-slate-800" };
                return (
                  <div key={label} className={`rounded-xl border px-3 py-2.5 ${palette[color] || palette.slate}`}>
                    <div className="text-xs opacity-60 font-semibold mb-0.5">{label}</div>
                    <div className="text-base font-black">{value}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Risk Config */}
          {config && (
            <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
              <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <Target className="w-4 h-4 text-blue-600" />
                Risk Configuration
              </h3>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ["Max Daily Loss", `${limits.max_daily_loss_pct}%`],
                  ["Max Single Stake", `${limits.max_single_stake_pct}%`],
                  ["Max Consec. Losses", limits.max_consecutive_losses],
                  ["Max Exposure", `${limits.max_open_exposure_pct}%`],
                  ["Min Edge Threshold", `${(limits.min_edge_threshold * 100).toFixed(1)}%`],
                  ["½ Kelly Fraction", `${kelly.half_kelly_fraction * 100}%`],
                  ["Min Stake", `₦${kelly.min_stake}`],
                  ["Drawdown Block", `${kelly.max_drawdown_block_pct}%`],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between bg-slate-50 rounded-lg px-2.5 py-1.5">
                    <span className="text-slate-500">{k}</span>
                    <span className="font-bold text-slate-800">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Kelly Calculator */}
          <KellyCalculator available={bankroll.available_balance || 100000} />
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef } from "react";
import {
  Play, RefreshCw, ChevronDown, ChevronUp, TrendingUp, TrendingDown,
  Target, BarChart3, Activity, Layers, AlertTriangle, CheckCircle2,
  XCircle, Clock, Zap, Shield, RotateCcw
} from "lucide-react";
import {
  fetchBacktestDataAvailability,
  fetchBacktestLeagues,
  runBacktest,
  runWalkForward,
} from "../api/virtualClient";

// ─── Small utility components ───────────────────────────────────────────────

function StatCard({ label, value, sub, color = "slate", icon: Icon, trend }) {
  const colorMap = {
    green: "bg-emerald-50 border-emerald-200 text-emerald-700",
    red: "bg-red-50 border-red-200 text-red-700",
    blue: "bg-blue-50 border-blue-200 text-blue-700",
    amber: "bg-amber-50 border-amber-200 text-amber-700",
    purple: "bg-purple-50 border-purple-200 text-purple-700",
    slate: "bg-slate-50 border-slate-200 text-slate-700",
  };
  const cls = colorMap[color] || colorMap.slate;
  return (
    <div className={`rounded-xl border p-4 flex flex-col gap-1 ${cls}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-70">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-50" />}
      </div>
      <div className="text-2xl font-black tracking-tight">{value}</div>
      {sub && <div className="text-xs opacity-60 font-medium">{sub}</div>}
      {trend != null && (
        <div className={`text-xs font-bold flex items-center gap-1 ${trend >= 0 ? "text-emerald-600" : "text-red-600"}`}>
          {trend >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          {trend >= 0 ? "+" : ""}{trend}%
        </div>
      )}
    </div>
  );
}

function Badge({ text, type = "neutral" }) {
  const cls = {
    win: "bg-emerald-100 text-emerald-800 border-emerald-200",
    loss: "bg-red-100 text-red-800 border-red-200",
    bet: "bg-blue-100 text-blue-800 border-blue-200",
    neutral: "bg-slate-100 text-slate-700 border-slate-200",
  }[type] || "bg-slate-100 text-slate-700 border-slate-200";
  return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold border ${cls}`}>{text}</span>;
}

function EquityCurve({ curve }) {
  const svgRef = useRef(null);
  if (!curve || curve.length === 0) return null;

  const W = 600, H = 150;
  const values = curve.map((p) => p.balance);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;

  const pts = values.map((v, i) => {
    const x = (i / Math.max(values.length - 1, 1)) * W;
    const y = H - ((v - minV) / range) * (H - 20) - 10;
    return `${x},${y}`;
  });
  const pathD = `M ${pts.join(" L ")}`;
  const areaD = `M 0,${H} L ${pts.join(" L ")} L ${W},${H} Z`;

  const isPositive = values[values.length - 1] >= values[0];
  const lineColor = isPositive ? "#10b981" : "#ef4444";
  const areaColor = isPositive ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.10)";

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 120 }}>
        <path d={areaD} fill={areaColor} />
        <path d={pathD} fill="none" stroke={lineColor} strokeWidth="2" strokeLinejoin="round" />
        {/* start/end dots */}
        <circle cx={pts[0].split(",")[0]} cy={pts[0].split(",")[1]} r="3" fill={lineColor} />
        <circle
          cx={pts[pts.length - 1].split(",")[0]}
          cy={pts[pts.length - 1].split(",")[1]}
          r="4"
          fill={lineColor}
          stroke="white"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  );
}

// ─── Config Panel ────────────────────────────────────────────────────────────

function ConfigPanel({ config, setConfig, leagues, onRunBacktest, onRunWalkForward, loading, availability }) {
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-5 shadow-sm">
      <div className="flex items-center gap-2">
        <Shield className="w-4 h-4 text-blue-600" />
        <h3 className="text-sm font-bold text-slate-800">Simulation Parameters</h3>
        <span className="ml-auto text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
          Strict No-Leakage Mode
        </span>
      </div>

      {/* Availability banner */}
      {availability && (
        <div className={`text-xs rounded-lg px-3 py-2 font-medium flex items-center gap-2 ${
          availability.sufficient_for_backtest
            ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
            : "bg-amber-50 text-amber-700 border border-amber-200"
        }`}>
          {availability.sufficient_for_backtest
            ? <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            : <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          }
          {availability.total_settled_events} settled events available
          {availability.earliest_date && ` · ${availability.earliest_date?.slice(0, 10)} → ${availability.latest_date?.slice(0, 10)}`}
          {!availability.sufficient_for_backtest && ` (need ≥ ${availability.minimum_required})`}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {/* League */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">League</label>
          <select
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.leagueId || ""}
            onChange={(e) => setConfig((c) => ({ ...c, leagueId: e.target.value || null }))}
          >
            <option value="">All Leagues</option>
            {leagues.map((lg) => (
              <option key={lg.id} value={lg.id}>{lg.name}</option>
            ))}
          </select>
        </div>

        {/* Start Date */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Start Date</label>
          <input
            type="date"
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.startDate || ""}
            onChange={(e) => setConfig((c) => ({ ...c, startDate: e.target.value || null }))}
          />
        </div>

        {/* End Date */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">End Date</label>
          <input
            type="date"
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.endDate || ""}
            onChange={(e) => setConfig((c) => ({ ...c, endDate: e.target.value || null }))}
          />
        </div>

        {/* Stake */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Stake / Bet (₦)</label>
          <input
            type="number"
            min="0.5" max="500" step="0.5"
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.stakePerBet}
            onChange={(e) => setConfig((c) => ({ ...c, stakePerBet: parseFloat(e.target.value) }))}
          />
        </div>

        {/* Bankroll */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Starting Bankroll (₦)</label>
          <input
            type="number"
            min="100" step="50"
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.startingBankroll}
            onChange={(e) => setConfig((c) => ({ ...c, startingBankroll: parseFloat(e.target.value) }))}
          />
        </div>

        {/* Walk-Forward Windows */}
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">Walk-Forward Windows</label>
          <input
            type="number"
            min="2" max="20"
            className="w-full text-xs border border-slate-200 rounded-lg px-2.5 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
            value={config.nWindows}
            onChange={(e) => setConfig((c) => ({ ...c, nWindows: parseInt(e.target.value) }))}
          />
        </div>
      </div>

      {/* Threshold sliders */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">
            Min Edge: <span className="text-blue-600">{(config.minEdge * 100).toFixed(1)}%</span>
          </label>
          <input type="range" min="0" max="0.2" step="0.005"
            value={config.minEdge}
            onChange={(e) => setConfig((c) => ({ ...c, minEdge: parseFloat(e.target.value) }))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">
            Min Model P: <span className="text-blue-600">{(config.minModelProb * 100).toFixed(0)}%</span>
          </label>
          <input type="range" min="0.3" max="0.95" step="0.01"
            value={config.minModelProb}
            onChange={(e) => setConfig((c) => ({ ...c, minModelProb: parseFloat(e.target.value) }))}
            className="w-full accent-blue-600"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 block mb-1">
            Min Odds: <span className="text-blue-600">{parseFloat(config.minOdds).toFixed(2)}</span>
          </label>
          <input type="range" min="1.0" max="5.0" step="0.05"
            value={config.minOdds}
            onChange={(e) => setConfig((c) => ({ ...c, minOdds: parseFloat(e.target.value) }))}
            className="w-full accent-blue-600"
          />
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3 pt-1">
        <button
          id="btn-run-backtest"
          onClick={onRunBacktest}
          disabled={loading}
          className="flex-1 flex items-center justify-center gap-2 bg-slate-900 text-white text-xs font-bold px-4 py-2.5 rounded-xl hover:bg-slate-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Run Full Backtest
        </button>
        <button
          id="btn-run-walkforward"
          onClick={onRunWalkForward}
          disabled={loading}
          className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white text-xs font-bold px-4 py-2.5 rounded-xl hover:bg-blue-700 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5" />}
          Walk-Forward Analysis
        </button>
      </div>
    </div>
  );
}

// ─── Results Panel ───────────────────────────────────────────────────────────

function MetricsSummary({ metrics, title }) {
  const s = metrics?.summary;
  const r = metrics?.risk_metrics;
  if (!s) return null;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
        <BarChart3 className="w-4 h-4 text-blue-600" />
        {title}
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Total Bets"
          value={s.total_bets}
          sub={`${s.wins}W / ${s.losses}L`}
          icon={Activity}
          color="slate"
        />
        <StatCard
          label="Hit Rate"
          value={`${s.hit_rate_pct}%`}
          sub="Win rate on BET signals"
          icon={Target}
          color={s.hit_rate_pct >= 50 ? "green" : "red"}
        />
        <StatCard
          label="ROI"
          value={`${s.roi_pct >= 0 ? "+" : ""}${s.roi_pct}%`}
          sub={`Total P&L: ₦${s.total_profit_loss >= 0 ? "+" : ""}${s.total_profit_loss}`}
          icon={TrendingUp}
          color={s.roi_pct >= 0 ? "green" : "red"}
        />
        <StatCard
          label="Profit Factor"
          value={isFinite(s.profit_factor) ? s.profit_factor?.toFixed(2) : "∞"}
          sub="Gross Win / Gross Loss"
          icon={Zap}
          color={s.profit_factor >= 1.2 ? "green" : s.profit_factor >= 1 ? "amber" : "red"}
        />
        <StatCard
          label="Sharpe Ratio"
          value={r?.sharpe_ratio?.toFixed(3)}
          sub="Risk-adjusted return"
          icon={Shield}
          color={r?.sharpe_ratio >= 1 ? "green" : r?.sharpe_ratio >= 0 ? "amber" : "red"}
        />
        <StatCard
          label="Max Drawdown"
          value={`${(r?.max_drawdown_pct * 100).toFixed(1)}%`}
          sub={`Peak-to-trough: ₦${r?.max_drawdown_abs}`}
          icon={TrendingDown}
          color={r?.max_drawdown_pct <= 0.1 ? "green" : r?.max_drawdown_pct <= 0.2 ? "amber" : "red"}
        />
        <StatCard
          label="Kelly Fraction"
          value={`${r?.kelly_pct?.toFixed(1)}%`}
          sub="Optimal stake size (½ Kelly)"
          icon={Target}
          color="blue"
        />
        <StatCard
          label="Bankroll"
          value={`₦${s.ending_bankroll}`}
          sub={`Started at ₦${s.starting_bankroll}`}
          trend={s.bankroll_growth_pct}
          color={s.bankroll_growth_pct >= 0 ? "green" : "red"}
        />
      </div>

      {/* Equity Curve */}
      {metrics?.equity_curve?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs font-bold text-slate-600 mb-2 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5" />
            Equity Curve
          </div>
          <EquityCurve curve={metrics.equity_curve} />
          <div className="flex justify-between text-xs text-slate-400 mt-1">
            <span>Start: ₦{metrics.equity_curve[0]?.balance}</span>
            <span>End: ₦{metrics.equity_curve[metrics.equity_curve.length - 1]?.balance}</span>
          </div>
        </div>
      )}

      {/* Strategy Breakdown */}
      {metrics?.strategy_breakdown?.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 text-xs font-bold text-slate-700">
            Strategy Breakdown
          </div>
          <div className="divide-y divide-slate-50">
            {metrics.strategy_breakdown.map((row) => (
              <div key={row.label} className="px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="font-medium text-slate-700 truncate max-w-[180px]">{row.label}</span>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-slate-500">{row.total_bets} bets</span>
                  <span className="text-slate-500">{row.hit_rate_pct}% win</span>
                  <span className={`font-bold ${row.total_profit_loss >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                    {row.total_profit_loss >= 0 ? "+" : ""}₦{row.total_profit_loss}
                  </span>
                  <span className={`font-bold ${row.roi_pct >= 0 ? "text-emerald-600" : "text-red-500"}`}>
                    ({row.roi_pct >= 0 ? "+" : ""}{row.roi_pct}% ROI)
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BetLogTable({ bets }) {
  const [expanded, setExpanded] = useState(false);
  const display = expanded ? bets : bets.slice(0, 20);

  if (!bets || bets.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400 text-sm">
        No BET signals fired in this simulation window.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-700">{bets.length} Executed Bets</span>
        {bets.length > 20 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 font-semibold flex items-center gap-1 hover:underline"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Show less" : `Show all ${bets.length}`}
          </button>
        )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-xs min-w-[700px]">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="text-left px-3 py-2.5 text-slate-600 font-semibold">Match</th>
              <th className="text-left px-3 py-2.5 text-slate-600 font-semibold">Market</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Odds</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Edge</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Result</th>
              <th className="text-right px-3 py-2.5 text-slate-600 font-semibold">P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {display.map((bet, i) => (
              <tr key={i} className={`hover:bg-slate-50 transition-colors ${bet.outcome === "WIN" ? "bg-emerald-50/30" : "bg-red-50/20"}`}>
                <td className="px-3 py-2 font-medium text-slate-800 whitespace-nowrap">
                  {bet.home_team} v {bet.away_team}
                  <span className="ml-2 text-slate-400 font-normal">({bet.result_score})</span>
                </td>
                <td className="px-3 py-2 text-slate-600 whitespace-nowrap">{bet.selection}</td>
                <td className="px-3 py-2 text-center font-mono text-slate-700">{bet.odds}</td>
                <td className="px-3 py-2 text-center font-mono text-blue-600">+{(bet.edge * 100).toFixed(1)}%</td>
                <td className="px-3 py-2 text-center">
                  <Badge
                    text={bet.outcome}
                    type={bet.outcome === "WIN" ? "win" : "loss"}
                  />
                </td>
                <td className={`px-3 py-2 text-right font-bold font-mono ${bet.profit_loss >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {bet.profit_loss >= 0 ? "+" : ""}₦{bet.profit_loss}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function WalkForwardWindows({ windows }) {
  if (!windows || windows.length === 0) return null;
  return (
    <div className="space-y-3">
      <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">Out-of-Sample Windows</h4>
      <div className="grid gap-3">
        {windows.map((w) => {
          const s = w.metrics?.summary;
          const isPositive = s?.roi_pct >= 0;
          return (
            <div key={w.window} className={`border rounded-xl p-4 ${isPositive ? "border-emerald-200 bg-emerald-50/40" : "border-red-200 bg-red-50/30"}`}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-slate-800">Window {w.window}</span>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span>{w.window_start?.slice(0, 10)}</span>
                  <span>→</span>
                  <span>{w.window_end?.slice(0, 10)}</span>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-3">
                <div className="text-center">
                  <div className="text-xs text-slate-500">Train Size</div>
                  <div className="text-sm font-bold text-slate-700">{w.train_size}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">Test Events</div>
                  <div className="text-sm font-bold text-slate-700">{w.test_size}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">Bets Fired</div>
                  <div className="text-sm font-bold text-slate-700">{s?.total_bets || 0}</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">Hit Rate</div>
                  <div className={`text-sm font-bold ${s?.hit_rate_pct >= 50 ? "text-emerald-600" : "text-red-600"}`}>{s?.hit_rate_pct || 0}%</div>
                </div>
                <div className="text-center">
                  <div className="text-xs text-slate-500">ROI</div>
                  <div className={`text-sm font-bold ${isPositive ? "text-emerald-600" : "text-red-600"}`}>
                    {s?.roi_pct >= 0 ? "+" : ""}{s?.roi_pct || 0}%
                  </div>
                </div>
              </div>
              {w.metrics?.equity_curve?.length > 0 && (
                <div className="mt-2">
                  <EquityCurve curve={w.metrics.equity_curve} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function VirtualBacktest() {
  const [config, setConfig] = useState({
    leagueId: null,
    startDate: null,
    endDate: null,
    stakePerBet: 10,
    startingBankroll: 1000,
    minEdge: 0.035,
    minModelProb: 0.65,
    minOdds: 1.25,
    nWindows: 5,
  });

  const [leagues, setLeagues] = useState([]);
  const [availability, setAvailability] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeMode, setActiveMode] = useState(null); // "backtest" | "walkforward"
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("summary"); // "summary" | "bets" | "windows"

  useEffect(() => {
    fetchBacktestLeagues().then((r) => setLeagues(r?.leagues || []));
    fetchBacktestDataAvailability().then((r) => setAvailability(r));
  }, []);

  const handleRunBacktest = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setActiveMode("backtest");
    try {
      const data = await runBacktest(config);
      if (!data) throw new Error("No response from server");
      setResult(data);
      setActiveTab("summary");
    } catch (e) {
      setError(e.message || "Backtest failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRunWalkForward = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setActiveMode("walkforward");
    try {
      const data = await runWalkForward(config);
      if (!data) throw new Error("No response from server");
      setResult(data);
      setActiveTab("summary");
    } catch (e) {
      setError(e.message || "Walk-forward failed");
    } finally {
      setLoading(false);
    }
  };

  const metrics = activeMode === "walkforward" ? result?.aggregate_metrics : result?.metrics;
  const bets = activeMode === "walkforward"
    ? (result?.windows?.flatMap((w) => w.settled_bets || []) || [])
    : (result?.settled_bets || []);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-black text-slate-900 tracking-tight">
            Phase 4 · Backtesting & Walk-Forward Engine
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Simulate historical strategy performance with strict temporal isolation — no future data ever used.
          </p>
        </div>
        {result && (
          <button
            onClick={() => { setResult(null); setError(null); setActiveMode(null); }}
            className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 transition-all"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reset
          </button>
        )}
      </div>

      {/* Config */}
      <ConfigPanel
        config={config}
        setConfig={setConfig}
        leagues={leagues}
        onRunBacktest={handleRunBacktest}
        onRunWalkForward={handleRunWalkForward}
        loading={loading}
        availability={availability}
      />

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center gap-3 py-12 text-slate-500 text-sm">
          <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
          <span className="font-medium">
            {activeMode === "walkforward" ? "Running walk-forward analysis..." : "Simulating historical trades..."}
          </span>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm">
          <XCircle className="w-4 h-4 shrink-0" />
          <span className="font-medium">{error}</span>
        </div>
      )}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4">
          {/* Mode badge + summary line */}
          <div className="flex items-center gap-3">
            <Badge
              text={activeMode === "walkforward" ? "Walk-Forward OOS" : "Full Backtest"}
              type="bet"
            />
            <span className="text-xs text-slate-500">
              {result.events_processed ?? result.total_events ?? "?"} events processed
              {result.events_skipped != null && ` · ${result.events_skipped} skipped (warm-up)`}
            </span>
            {result.error && (
              <span className="text-xs text-amber-600 font-medium flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                {result.error}
              </span>
            )}
          </div>

          {/* Sub-tabs */}
          <div className="flex gap-2 border-b border-slate-100">
            {["summary", "bets", ...(activeMode === "walkforward" ? ["windows"] : [])].map((t) => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                className={`text-xs font-bold px-3 py-2 capitalize border-b-2 transition-all ${
                  activeTab === t
                    ? "border-blue-600 text-blue-700"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                {t === "bets" ? `Bet Log (${bets.filter(b => b.signal === "BET").length})` : t}
              </button>
            ))}
          </div>

          {activeTab === "summary" && metrics && (
            <MetricsSummary metrics={metrics} title={
              activeMode === "walkforward"
                ? "Aggregate Out-of-Sample Performance"
                : "Full Backtest Results"
            } />
          )}

          {activeTab === "bets" && (
            <BetLogTable bets={bets.filter(b => b.signal === "BET")} />
          )}

          {activeTab === "windows" && activeMode === "walkforward" && (
            <WalkForwardWindows windows={result.windows} />
          )}
        </div>
      )}
    </div>
  );
}

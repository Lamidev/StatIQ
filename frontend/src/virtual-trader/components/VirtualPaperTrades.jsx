import React, { useState, useEffect, useCallback } from "react";
import {
  TrendingUp, TrendingDown, Activity, Target, Zap, RefreshCw,
  CheckCircle2, XCircle, Clock, AlertTriangle, Play, RotateCcw,
  Wallet, BarChart3, Flame, Shield, ChevronDown, ChevronUp
} from "lucide-react";
import {
  fetchPaperBankroll,
  fetchOpenBets,
  fetchBetHistory,
  fetchPaperSessionStats,
  manualFireBets,
  manualSettle,
  resetBankroll,
} from "../api/virtualClient";

// ─── Utility components ──────────────────────────────────────────────────────

function StatTile({ label, value, sub, color = "slate", icon: Icon, flash }) {
  const palette = {
    green: "bg-emerald-50 border-emerald-200 text-emerald-800",
    red: "bg-red-50 border-red-200 text-red-800",
    blue: "bg-blue-50 border-blue-200 text-blue-800",
    amber: "bg-amber-50 border-amber-200 text-amber-800",
    purple: "bg-purple-50 border-purple-200 text-purple-800",
    slate: "bg-slate-50 border-slate-200 text-slate-800",
  };
  return (
    <div className={`rounded-xl border p-4 ${palette[color] || palette.slate} ${flash ? "animate-pulse" : ""}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-60">{label}</span>
        {Icon && <Icon className="w-4 h-4 opacity-40" />}
      </div>
      <div className="text-2xl font-black tracking-tight">{value}</div>
      {sub && <div className="text-xs opacity-60 font-medium mt-0.5">{sub}</div>}
    </div>
  );
}

function OutcomeBadge({ outcome }) {
  if (!outcome) return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border bg-amber-50 text-amber-700 border-amber-200"><Clock className="w-3 h-3" />OPEN</span>;
  if (outcome === "WIN") return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border bg-emerald-50 text-emerald-700 border-emerald-200"><CheckCircle2 className="w-3 h-3" />WIN</span>;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border bg-red-50 text-red-700 border-red-200"><XCircle className="w-3 h-3" />LOSS</span>;
}

function StreakBadge({ streak }) {
  if (!streak || streak.count === 0) return null;
  const isWin = streak.type === "win";
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold ${
      isWin ? "bg-emerald-50 border border-emerald-200 text-emerald-700" : "bg-red-50 border border-red-200 text-red-700"
    }`}>
      <Flame className="w-3.5 h-3.5" />
      {streak.count} {streak.type === "win" ? "Win" : "Loss"} Streak
    </div>
  );
}

// ─── Bankroll Panel ──────────────────────────────────────────────────────────

function BankrollPanel({ bankroll, onReset, resetting }) {
  if (!bankroll) return (
    <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 text-center text-slate-400 text-sm">
      Connecting to bankroll...
    </div>
  );

  const plPositive = bankroll.total_profit_loss >= 0;
  const roiPositive = bankroll.cumulative_roi_pct >= 0;

  return (
    <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl p-5 text-white shadow-lg">
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Paper Bankroll</div>
          <div className="text-4xl font-black tracking-tight">
            ₦{bankroll.current_balance?.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-sm text-slate-400 mt-0.5">
            Started at ₦{bankroll.starting_balance?.toLocaleString("en-GB", { minimumFractionDigits: 2 })}
          </div>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-black ${plPositive ? "text-emerald-400" : "text-red-400"}`}>
            {plPositive ? "+" : ""}₦{Math.abs(bankroll.total_profit_loss)?.toLocaleString("en-GB", { minimumFractionDigits: 2 })}
          </div>
          <div className={`text-sm font-bold ${roiPositive ? "text-emerald-400" : "text-red-400"}`}>
            {roiPositive ? "+" : ""}{bankroll.cumulative_roi_pct}% ROI
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="bg-white/10 rounded-lg px-3 py-2">
          <div className="text-xs text-slate-400 mb-0.5">Total Bets</div>
          <div className="text-lg font-bold">{bankroll.total_bets}</div>
        </div>
        <div className="bg-white/10 rounded-lg px-3 py-2">
          <div className="text-xs text-slate-400 mb-0.5">Hit Rate</div>
          <div className={`text-lg font-bold ${bankroll.win_rate_pct >= 50 ? "text-emerald-400" : "text-red-400"}`}>
            {bankroll.win_rate_pct}%
          </div>
        </div>
        <div className="bg-white/10 rounded-lg px-3 py-2">
          <div className="text-xs text-slate-400 mb-0.5">Open Exposure</div>
          <div className="text-lg font-bold text-amber-400">
            ₦{bankroll.total_exposure?.toFixed(2)}
          </div>
        </div>
        <div className="bg-white/10 rounded-lg px-3 py-2">
          <div className="text-xs text-slate-400 mb-0.5">Max Drawdown</div>
          <div className={`text-lg font-bold ${bankroll.max_drawdown_pct <= 5 ? "text-emerald-400" : "text-red-400"}`}>
            {bankroll.max_drawdown_pct}%
          </div>
        </div>
      </div>

      {/* Available balance bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-slate-400 mb-1">
          <span>Available: ₦{bankroll.available_balance?.toFixed(2)}</span>
          <span>Exposed: ₦{bankroll.total_exposure?.toFixed(2)}</span>
        </div>
        <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
          <div
            className="h-full bg-emerald-400 rounded-full transition-all duration-500"
            style={{ width: `${Math.min(100, (bankroll.available_balance / bankroll.current_balance) * 100)}%` }}
          />
        </div>
      </div>

      <button
        onClick={onReset}
        disabled={resetting}
        className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-red-400 transition-colors mt-1"
      >
        {resetting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
        Reset Bankroll
      </button>
    </div>
  );
}

// ─── Session Stats Bar ───────────────────────────────────────────────────────

function SessionBar({ stats }) {
  if (!stats) return null;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="text-xs text-slate-500 font-semibold">Today:</div>
      <StatTile label="Bets" value={stats.today_bets} color="slate" />
      <StatTile label="Hit Rate" value={`${stats.today_hit_rate_pct}%`} color={stats.today_hit_rate_pct >= 50 ? "green" : "red"} />
      <StatTile label="P&L" value={`${stats.today_profit_loss >= 0 ? "+" : ""}₦${stats.today_profit_loss}`} color={stats.today_profit_loss >= 0 ? "green" : "red"} />
      <StatTile label="Open" value={stats.open_bets} color="amber" icon={Clock} />
      <StreakBadge streak={stats.current_streak} />
    </div>
  );
}

// ─── Bet Table ───────────────────────────────────────────────────────────────

function BetTable({ bets, emptyMessage, showOutcome = true }) {
  const [expanded, setExpanded] = useState(false);
  const display = expanded ? bets : bets.slice(0, 15);

  if (!bets || bets.length === 0) {
    return (
      <div className="text-center py-10 text-slate-400 text-sm flex flex-col items-center gap-2">
        <Clock className="w-6 h-6 opacity-40" />
        {emptyMessage || "No bets to display."}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-xs min-w-[640px]">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-3 py-2.5 text-slate-600 font-semibold">Match</th>
              <th className="text-left px-3 py-2.5 text-slate-600 font-semibold">Selection</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Odds</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Stake</th>
              <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Confidence</th>
              {showOutcome && <th className="text-center px-3 py-2.5 text-slate-600 font-semibold">Outcome</th>}
              <th className="text-right px-3 py-2.5 text-slate-600 font-semibold">P&L</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {display.map((bet) => (
              <tr
                key={bet.bet_id}
                className={`hover:bg-slate-50 transition-colors ${
                  bet.outcome === "WIN" ? "bg-emerald-50/20" :
                  bet.outcome === "LOSS" ? "bg-red-50/20" : ""
                }`}
              >
                <td className="px-3 py-2.5 font-medium text-slate-800 whitespace-nowrap">
                  <div>{bet.home_team} v {bet.away_team}</div>
                  <div className="text-slate-400 text-xs font-normal">{bet.league_name}</div>
                </td>
                <td className="px-3 py-2.5 text-slate-600 whitespace-nowrap">
                  <div>{bet.selection}</div>
                  <div className="text-slate-400 text-xs">{bet.strategy_code}</div>
                </td>
                <td className="px-3 py-2.5 text-center font-mono text-slate-800">{bet.odds}</td>
                <td className="px-3 py-2.5 text-center font-mono text-slate-700">₦{bet.stake?.toFixed(2)}</td>
                <td className="px-3 py-2.5 text-center">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                    bet.confidence === "HIGH" ? "bg-emerald-100 text-emerald-700" :
                    bet.confidence === "MEDIUM" ? "bg-blue-100 text-blue-700" :
                    "bg-slate-100 text-slate-600"
                  }`}>
                    {bet.confidence || "—"}
                  </span>
                </td>
                {showOutcome && (
                  <td className="px-3 py-2.5 text-center">
                    <OutcomeBadge outcome={bet.outcome} />
                  </td>
                )}
                <td className={`px-3 py-2.5 text-right font-bold font-mono ${
                  bet.profit_loss == null ? "text-amber-500" :
                  bet.profit_loss > 0 ? "text-emerald-600" : "text-red-600"
                }`}>
                  {bet.profit_loss != null
                    ? `${bet.profit_loss > 0 ? "+" : ""}₦${bet.profit_loss.toFixed(2)}`
                    : `+₦${bet.potential_return?.toFixed(2)}`
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {bets.length > 15 && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full text-xs text-blue-600 font-semibold py-2 flex items-center justify-center gap-1 hover:underline"
        >
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          {expanded ? "Show less" : `Show all ${bets.length} bets`}
        </button>
      )}
    </div>
  );
}

// ─── History Summary Bar ─────────────────────────────────────────────────────

function HistorySummary({ history }) {
  if (!history) return null;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
      <StatTile label="Settled Bets" value={history.count} icon={Activity} color="slate" />
      <StatTile
        label="Hit Rate"
        value={history.count > 0 ? `${((history.wins / history.count) * 100).toFixed(1)}%` : "—"}
        sub={`${history.wins}W / ${history.losses}L`}
        icon={Target}
        color={history.count > 0 && history.wins / history.count >= 0.5 ? "green" : "red"}
      />
      <StatTile
        label="Total P&L"
        value={`${history.total_profit_loss >= 0 ? "+" : ""}₦${Math.abs(history.total_profit_loss).toFixed(2)}`}
        icon={TrendingUp}
        color={history.total_profit_loss >= 0 ? "green" : "red"}
      />
      <StatTile
        label="Wins / Losses"
        value={`${history.wins} / ${history.losses}`}
        icon={Zap}
        color="blue"
      />
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function VirtualPaperTrades() {
  const [bankroll, setBankroll] = useState(null);
  const [openBets, setOpenBets] = useState({ count: 0, bets: [] });
  const [history, setHistory] = useState({ count: 0, bets: [], wins: 0, losses: 0, total_profit_loss: 0 });
  const [sessionStats, setSessionStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // "fire" | "settle" | "reset"
  const [tab, setTab] = useState("open"); // "open" | "history"
  const [lastRefresh, setLastRefresh] = useState(null);
  const [actionMsg, setActionMsg] = useState(null);

  const loadAll = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    const [br, ob, hist, stats] = await Promise.all([
      fetchPaperBankroll(),
      fetchOpenBets(50),
      fetchBetHistory(100),
      fetchPaperSessionStats(),
    ]);
    setBankroll(br);
    setOpenBets(ob || { count: 0, bets: [] });
    setHistory(hist || { count: 0, bets: [], wins: 0, losses: 0, total_profit_loss: 0 });
    setSessionStats(stats);
    setLastRefresh(new Date());
    if (!quiet) setLoading(false);
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(() => loadAll(true), 10000); // refresh every 10s
    return () => clearInterval(interval);
  }, [loadAll]);

  const handleFire = async () => {
    setActionLoading("fire");
    const res = await manualFireBets();
    setActionMsg(res
      ? `✅ Fired ${res.result?.placed || 0} bets, skipped ${res.result?.skipped || 0}.`
      : "❌ Failed to fire bets.");
    await loadAll(true);
    setActionLoading(null);
    setTimeout(() => setActionMsg(null), 5000);
  };

  const handleSettle = async () => {
    setActionLoading("settle");
    const res = await manualSettle();
    setActionMsg(res
      ? `✅ Settled: ${res.result?.won || 0} won, ${res.result?.lost || 0} lost, ${res.result?.unsettled || 0} pending.`
      : "❌ Settlement failed.");
    await loadAll(true);
    setActionLoading(null);
    setTimeout(() => setActionMsg(null), 5000);
  };

  const handleReset = async () => {
    if (!confirm("Reset the bankroll to starting balance? This will void all open bets.")) return;
    setActionLoading("reset");
    const res = await resetBankroll();
    setActionMsg(res ? `✅ ${res.message}` : "❌ Reset failed.");
    await loadAll(true);
    setActionLoading(null);
    setTimeout(() => setActionMsg(null), 5000);
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-base font-black text-slate-900 tracking-tight">
            Phase 5 · Paper Trading Ledger
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Autonomous live bet simulation — signals fire and settle in real-time.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-xs text-slate-400">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => loadAll()}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs font-bold px-3 py-2 border border-slate-200 rounded-lg text-slate-600 hover:bg-slate-50 transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Action feedback */}
      {actionMsg && (
        <div className="text-xs font-medium px-4 py-2.5 rounded-xl border bg-blue-50 text-blue-700 border-blue-200">
          {actionMsg}
        </div>
      )}

      {/* Manual controls */}
      <div className="flex flex-wrap gap-3">
        <button
          id="btn-fire-bets"
          onClick={handleFire}
          disabled={!!actionLoading}
          className="flex items-center gap-2 bg-slate-900 text-white text-xs font-bold px-4 py-2 rounded-xl hover:bg-slate-700 transition-all disabled:opacity-60"
        >
          {actionLoading === "fire" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          Fire Bets Now
        </button>
        <button
          id="btn-settle"
          onClick={handleSettle}
          disabled={!!actionLoading}
          className="flex items-center gap-2 bg-blue-600 text-white text-xs font-bold px-4 py-2 rounded-xl hover:bg-blue-700 transition-all disabled:opacity-60"
        >
          {actionLoading === "settle" ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
          Settle Open Bets
        </button>
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-400">
          <Shield className="w-3.5 h-3.5" />
          Auto-running every 30s / 15s
        </div>
      </div>

      {/* Bankroll */}
      <BankrollPanel bankroll={bankroll} onReset={handleReset} resetting={actionLoading === "reset"} />

      {/* Session Stats */}
      {sessionStats && (
        <div className="bg-white border border-slate-200 rounded-xl p-4">
          <div className="text-xs font-bold text-slate-600 uppercase tracking-wider mb-3">Today's Session</div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatTile label="Bets Today" value={sessionStats.today_bets} icon={Activity} />
            <StatTile label="Hit Rate" value={`${sessionStats.today_hit_rate_pct}%`} icon={Target} color={sessionStats.today_hit_rate_pct >= 50 ? "green" : "red"} />
            <StatTile label="Today P&L" value={`${sessionStats.today_profit_loss >= 0 ? "+" : ""}₦${sessionStats.today_profit_loss}`} icon={TrendingUp} color={sessionStats.today_profit_loss >= 0 ? "green" : "red"} />
            <StatTile label="Today ROI" value={`${sessionStats.today_roi_pct >= 0 ? "+" : ""}${sessionStats.today_roi_pct}%`} icon={BarChart3} color={sessionStats.today_roi_pct >= 0 ? "green" : "red"} />
            <StatTile label="Open Bets" value={sessionStats.open_bets} icon={Clock} color="amber" />
          </div>
          {sessionStats.current_streak?.count > 0 && (
            <div className="mt-3">
              <StreakBadge streak={sessionStats.current_streak} />
            </div>
          )}
        </div>
      )}

      {/* Bet Tabs */}
      <div className="space-y-3">
        <div className="flex gap-1 border-b border-slate-100">
          <button
            onClick={() => setTab("open")}
            className={`text-xs font-bold px-3 py-2 border-b-2 transition-all ${
              tab === "open" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Open Bets ({openBets.count})
          </button>
          <button
            onClick={() => setTab("history")}
            className={`text-xs font-bold px-3 py-2 border-b-2 transition-all ${
              tab === "history" ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Trade History ({history.count})
          </button>
        </div>

        {tab === "open" && (
          <BetTable
            bets={openBets.bets}
            emptyMessage="No open bets. Worker fires every 30 seconds when BET signals are found."
            showOutcome={false}
          />
        )}

        {tab === "history" && (
          <>
            <HistorySummary history={history} />
            <BetTable
              bets={history.bets}
              emptyMessage="No settled bets yet. Bets settle automatically when results are ingested."
              showOutcome={true}
            />
          </>
        )}
      </div>
    </div>
  );
}

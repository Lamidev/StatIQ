import React, { useState, useEffect } from "react";
import { 
  Bot, 
  Power, 
  Send, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  TrendingUp, 
  ShieldCheck, 
  Sparkles, 
  RefreshCw, 
  Copy, 
  Check,
  ExternalLink,
  Sliders,
  Bell,
  Ticket,
  ChevronRight,
  Flame,
  ArrowUpRight,
  Trash2
} from "lucide-react";
import { 
  fetchFrontTestStatus, 
  toggleFrontTestAutomation, 
  updateFrontTestConfig, 
  triggerImmediateFrontTestScan, 
  sendTelegramTestPing,
  resetFrontTestLedger
} from "../api/virtualClient";


export default function VirtualFrontTesting() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [copiedCode, setCopiedCode] = useState("");
  const [toastMessage, setToastMessage] = useState("");
  const [activeViewTab, setActiveViewTab] = useState("active"); // 'active' | 'history'

  // Strategy Presets
  const [targetOdds, setTargetOdds] = useState(2.0);
  const [preferredMarket, setPreferredMarket] = useState("ALL");
  const [enablePerLeague, setEnablePerLeague] = useState(true);
  const [enableMasterSlip, setEnableMasterSlip] = useState(true);
  const [activeLeagues, setActiveLeagues] = useState(["Master Multi-League", "England Virtual"]);

  const AVAILABLE_LEAGUES = [
    { id: "Master Multi-League", label: "Master Multi-League", icon: "🏆" },
    { id: "England Virtual", label: "England (Premier League)", icon: "🏴󠁧󠁢󠁥󠁮󠁧󠁿" },
    { id: "Spain Virtual", label: "Spain (La Liga)", icon: "🇪🇸" },
    { id: "Italy Virtual", label: "Italy (Serie A)", icon: "🇮🇹" },
    { id: "Germany Virtual", label: "Germany (Bundesliga)", icon: "🇩🇪" },
    { id: "France Virtual", label: "France (Ligue 1)", icon: "🇫🇷" },
  ];

  const loadStatus = async () => {
    const res = await fetchFrontTestStatus();
    if (res) {
      setData(res);
      if (res.config) {
        setTargetOdds(res.config.target_odds || 2.0);
        setPreferredMarket(res.config.preferred_market || "ALL");
        setEnablePerLeague(res.config.enable_per_league ?? true);
        setEnableMasterSlip(res.config.enable_master_slip ?? true);
        if (res.config.active_leagues && Array.isArray(res.config.active_leagues)) {
          setActiveLeagues(res.config.active_leagues);
        }
      }
    }
    setLoading(false);
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(""), 4000);
  };

  const toggleLeague = (leagueId) => {
    setActiveLeagues((prev) => {
      if (prev.includes(leagueId)) {
        if (prev.length === 1) {
          showToast("At least one league must remain active.");
          return prev;
        }
        return prev.filter((l) => l !== leagueId);
      } else {
        return [...prev, leagueId];
      }
    });
  };

  const handleToggle = async () => {
    if (!data) return;
    setActionLoading(true);
    const newState = !data.is_enabled;
    const res = await toggleFrontTestAutomation(newState);
    if (res && res.status === "SUCCESS") {
      showToast(res.message);
      await loadStatus();
    }
    setActionLoading(false);
  };

  const handleSaveConfig = async () => {
    setActionLoading(true);
    const res = await updateFrontTestConfig({
      target_odds: parseFloat(targetOdds),
      preferred_market: preferredMarket,
      enable_per_league: enablePerLeague,
      enable_master_slip: enableMasterSlip,
      active_leagues: activeLeagues
    });
    if (res && res.status === "SUCCESS") {
      showToast("Strategy presets and active leagues saved!");
      await loadStatus();
    }
    setActionLoading(false);
  };


  const handleTriggerNow = async () => {
    setActionLoading(true);
    const res = await triggerImmediateFrontTestScan();
    if (res && res.status === "SUCCESS") {
      showToast("Scanned current round and generated verified SportyBet slips!");
      await loadStatus();
    }
    setActionLoading(false);
  };

  const handleTestTelegram = async () => {
    setActionLoading(true);
    const res = await sendTelegramTestPing();
    if (res) {
      showToast(res.message);
    }
    setActionLoading(false);
  };

  const copyToClipboard = (code) => {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(""), 2500);
    showToast(`SportyBet Code '${code}' copied!`);
  };

  const formatKickoffTime = (isoString) => {
    if (!isoString) return "Upcoming";
    let str = String(isoString);
    if (!str.endsWith("Z") && !str.includes("+")) {
      str += "Z";
    }
    const d = new Date(str);
    return isNaN(d.getTime()) 
      ? "Upcoming" 
      : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  };

  const handleResetLedger = async () => {
    if (!window.confirm("Are you sure you want to clear all test history and start afresh on a clean slate?")) {
      return;
    }
    setActionLoading(true);
    try {
      const res = await resetFrontTestLedger();
      if (res && res.status === "SUCCESS") {
        showToast("Ledger reset! Starting fresh on clean slate.");
        await loadStatus();
      } else {
        showToast("Failed to reset ledger.");
      }
    } catch (err) {
      showToast("Error resetting ledger.");
    } finally {
      setActionLoading(false);
    }
  };

  const isEnabled = data?.is_enabled ?? false;
  const winRate = data?.win_rate_pct ?? 0;
  const totalSlips = data?.total_slips ?? 0;
  const wonSlips = data?.won_slips ?? 0;
  const lostSlips = data?.lost_slips ?? 0;
  const pendingSlips = data?.pending_slips ?? 0;
  const netProfit = data?.net_profit_units ?? 0;

  const pendingList = data?.recent_slips?.filter(s => s.status === "PENDING") || [];
  const settledList = data?.recent_slips?.filter(s => s.status !== "PENDING") || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      {/* Toast Alert */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-5 py-3 rounded-xl shadow-2xl border border-slate-700 text-xs font-bold flex items-center space-x-2 animate-bounce">
          <Sparkles className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* ── STEP 1: Command Header & Quick State ── */}
      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6">
        <div className="flex items-center space-x-4">
          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center transition-all ${
            isEnabled ? "bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 animate-pulse" : "bg-slate-100 text-slate-400"
          }`}>
            <Bot className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-black text-slate-900">vFootball 24/7 Front-Tester</h1>
              <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${
                isEnabled ? "bg-emerald-100 text-emerald-800 border border-emerald-300" : "bg-slate-100 text-slate-500 border border-slate-300"
              }`}>
                {isEnabled ? "● LIVE ACTIVE" : "○ PAUSED"}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Auto-generates ~2.0x SportyBet tickets before every 30-min round & logs real win rates to Telegram.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto">
          <button
            onClick={handleTriggerNow}
            disabled={actionLoading}
            className="flex-1 lg:flex-none px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-1.5 border border-slate-200"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${actionLoading ? "animate-spin" : ""}`} />
            <span>Scan & Book Next Round</span>
          </button>

          <button
            onClick={handleTestTelegram}
            disabled={actionLoading}
            className="flex-1 lg:flex-none px-4 py-2.5 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-1.5 border border-blue-200"
          >
            <Bell className="w-3.5 h-3.5" />
            <span>Telegram Alert Test</span>
          </button>

          <button
            onClick={handleResetLedger}
            disabled={actionLoading}
            className="flex-1 lg:flex-none px-4 py-2.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-xl text-xs font-bold transition-all flex items-center justify-center space-x-1.5 border border-rose-200"
            title="Clear all test history and start afresh"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Reset Ledger</span>
          </button>

          <button
            onClick={handleToggle}
            disabled={actionLoading}
            className={`w-full lg:w-auto px-6 py-2.5 rounded-xl text-xs font-black tracking-wide transition-all shadow-md flex items-center justify-center space-x-2 ${
              isEnabled 
                ? "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/20" 
                : "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20"
            }`}
          >
            <Power className="w-4 h-4" />
            <span>{isEnabled ? "PAUSE AUTOMATION" : "TURN AUTOMATION ON"}</span>
          </button>
        </div>
      </div>


      {/* ── STEP 2: Live Front-Testing Performance KPIs ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Win Rate</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-3xl font-black text-slate-900">{winRate}%</span>
            <span className="text-xs font-bold text-emerald-600">({wonSlips}W - {lostSlips}L)</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">From {wonSlips + lostSlips} settled slips</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Net Yield / Profit</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className={`text-3xl font-black ${netProfit >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
              {netProfit >= 0 ? `+${netProfit}` : netProfit}
            </span>
            <span className="text-xs font-bold text-slate-500">Units</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Based on 1.0 unit fixed stake</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Active Round Tickets</span>
          <div className="flex items-baseline space-x-2 mt-1">
            <span className="text-3xl font-black text-amber-600">{pendingSlips}</span>
            <span className="text-xs font-bold text-slate-500">Pending</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Auto-settles 3 mins post-kickoff</p>
        </div>

        <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Telegram Channel</span>
          <div className="flex items-center space-x-2 mt-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
            <span className="text-sm font-bold text-emerald-700">@StatIQbot Connected</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Pre-Match + Result Audits Active</p>
        </div>
      </div>

      {/* ── STEP 3: Automated Strategy Presets (Clean Collapsible Card) ── */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-black text-slate-900 flex items-center gap-2 uppercase tracking-wide">
              <Sliders className="w-4 h-4 text-emerald-600" />
              Strategy & Target Odds Presets
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">Customize what type of tickets the engine builds for each round.</p>
          </div>
          <button
            onClick={handleSaveConfig}
            disabled={actionLoading}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition-all shadow-sm self-start sm:self-auto"
          >
            Save Presets
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-5">
          {/* Target Odds */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-700">Target Combined Odds</label>
            <div className="flex gap-2">
              {[1.8, 2.0, 2.2, 2.5].map((val) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setTargetOdds(val)}
                  className={`flex-1 py-2 rounded-xl text-xs font-black border transition-all ${
                    parseFloat(targetOdds) === val
                      ? "bg-emerald-600 border-emerald-600 text-white shadow-sm"
                      : "bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {val.toFixed(1)}x
                </button>
              ))}
            </div>
          </div>

          {/* Market Focus */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-700">Winnable Market Focus</label>
            <select
              value={preferredMarket}
              onChange={(e) => setPreferredMarket(e.target.value)}
              className="w-full px-3.5 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-800 bg-slate-50 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-emerald-500"
            >
              <option value="ALL">⭐ Multi-Market Safe Combo (Over 1.5 + 1X)</option>
              <option value="OVER_1.5">⚽ Over 1.5 Goals Pure Strategy (~78% Hit Rate)</option>
              <option value="DOUBLE_CHANCE">🛡️ Double Chance 1X / X2 (Draw Immunity)</option>
            </select>
          </div>

          {/* Scope Checkboxes */}
          <div className="space-y-2">
            <label className="text-xs font-bold text-slate-700">Dispatch Options</label>
            <div className="space-y-2">
              <label className="flex items-center space-x-2 text-xs font-semibold text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enablePerLeague}
                  onChange={(e) => setEnablePerLeague(e.target.checked)}
                  className="rounded-sm text-emerald-600 focus:ring-emerald-500 w-4 h-4"
                />
                <span>Individual League 2.0x Slips (England, Spain, Italy, etc.)</span>
              </label>

              <label className="flex items-center space-x-2 text-xs font-semibold text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableMasterSlip}
                  onChange={(e) => setEnableMasterSlip(e.target.checked)}
                  className="rounded-sm text-emerald-600 focus:ring-emerald-500 w-4 h-4"
                />
                <span>Master Cross-League 2.0x Slip (#1 Pick per League)</span>
              </label>
            </div>
          </div>
        </div>

        {/* ── Active League Selector Pills ── */}
        <div className="pt-5 mt-5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-2.5">
            <label className="text-xs font-bold text-slate-700 flex items-center gap-1.5">
              <span>🎯 Focus Leagues & Tournaments</span>
              <span className="text-[11px] font-normal text-slate-400">(Click to toggle on/off)</span>
            </label>
            <span className="text-[11px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">
              {activeLeagues.length} of {AVAILABLE_LEAGUES.length} Active
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            {AVAILABLE_LEAGUES.map((league) => {
              const isSelected = activeLeagues.includes(league.id);
              return (
                <button
                  key={league.id}
                  type="button"
                  onClick={() => toggleLeague(league.id)}
                  className={`flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    isSelected
                      ? "bg-emerald-500/10 border-emerald-500 text-emerald-900 shadow-xs"
                      : "bg-slate-50 border-slate-200 text-slate-400 hover:border-slate-300 hover:text-slate-600"
                  }`}
                >
                  <span className="text-sm">{league.icon}</span>
                  <span className="truncate">{league.label}</span>
                  {isSelected && <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 ml-0.5" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>


      {/* ── STEP 4: Visual Ticket Cards & Settlement Ledger ── */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Ticket className="w-5 h-5 text-emerald-600" />
            <h2 className="text-base font-black text-slate-900">Live Dispatched Tickets & Results</h2>
          </div>

          {/* View Filter Switch */}
          <div className="flex p-1 bg-slate-100 rounded-xl">
            <button
              onClick={() => setActiveViewTab("active")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeViewTab === "active" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Upcoming / Active ({pendingList.length})
            </button>
            <button
              onClick={() => setActiveViewTab("history")}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeViewTab === "history" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Settled History ({settledList.length})
            </button>
          </div>
        </div>

        {/* ACTIVE ROUND SLIPS: Render as Clean Betting Slip Cards */}
        {activeViewTab === "active" && (
          <div>
            {pendingList.length === 0 ? (
              <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center">
                <Clock className="w-8 h-8 text-slate-300 mx-auto mb-3 animate-spin" />
                <p className="text-sm font-bold text-slate-700">Awaiting Next vFootball Round</p>
                <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
                  The agent will automatically generate 2.0x slips ~10 minutes before the next round kickoffs. Click 'Scan & Book Next Round' to manually force a scan now.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {pendingList.map((slip) => (
                  <div key={slip.id} className="bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all overflow-hidden flex flex-col justify-between">
                    {/* Header */}
                    <div className="p-4 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                      <div>
                        <span className="text-[10px] font-extrabold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                          {slip.league_name}
                        </span>
                        <p className="text-xs text-slate-400 font-bold mt-1">
                          Kickoff: {formatKickoffTime(slip.round_time)}
                        </p>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-black text-slate-900">{slip.actual_odds}x</span>
                        <p className="text-[10px] font-bold text-amber-600">IN PLAY / PENDING</p>
                      </div>

                    </div>

                    {/* Picks Body */}
                    <div className="p-4 space-y-2 flex-1">
                      {slip.selections?.map((sel, idx) => (
                        <div key={idx} className="p-2.5 bg-slate-50/80 rounded-xl border border-slate-100 flex items-center justify-between">
                          <div>
                            <p className="text-xs font-bold text-slate-800">{sel.match}</p>
                            <p className="text-[11px] font-semibold text-emerald-700">{sel.pick}</p>
                          </div>
                          <span className="text-xs font-bold text-slate-500">{sel.odds}x</span>
                        </div>
                      ))}
                    </div>

                    {/* Booking Code Footer */}
                    <div className="p-3 bg-slate-900 text-white flex items-center justify-between">
                      <div>
                        <p className="text-[9px] text-slate-400 uppercase tracking-wider font-bold">SportyBet Booking Code</p>
                        <p className="text-sm font-mono font-black text-amber-400">{slip.booking_code}</p>
                      </div>
                      <button
                        onClick={() => copyToClipboard(slip.booking_code)}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all"
                      >
                        {copiedCode === slip.booking_code ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span className="text-emerald-400">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5" />
                            <span>Copy Code</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* SETTLED HISTORY: Clean Audited Table */}
        {activeViewTab === "history" && (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            {settledList.length === 0 ? (
              <div className="p-12 text-center text-slate-400 text-xs">
                <p className="font-bold text-slate-700">No Settled Slips Yet</p>
                <p className="text-slate-400 mt-1">Slips will settle and appear here ~3 minutes after match conclusion.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-bold border-b border-slate-200">
                    <tr>
                      <th className="py-3 px-4">League</th>
                      <th className="py-3 px-4">Booking Code</th>
                      <th className="py-3 px-4">Picks</th>
                      <th className="py-3 px-4">Odds</th>
                      <th className="py-3 px-4">Result</th>
                      <th className="py-3 px-4 text-right">P&L</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-medium">
                    {settledList.map((s) => (
                      <tr key={s.id} className="hover:bg-slate-50/80">
                        <td className="py-3 px-4 font-bold text-slate-900">{s.league_name}</td>
                        <td className="py-3 px-4 font-mono font-bold text-slate-700">{s.booking_code}</td>
                        <td className="py-3 px-4">
                          {s.selections?.map((sel, i) => (
                            <span key={i} className="mr-2 inline-block text-[11px] text-slate-600">
                              <b>{sel.match}:</b> {sel.pick} ({sel.odds}x)
                            </span>
                          ))}
                        </td>
                        <td className="py-3 px-4 font-black text-slate-900">{s.actual_odds}x</td>
                        <td className="py-3 px-4">
                          {s.status === "WON" ? (
                            <span className="px-2.5 py-0.5 rounded-full font-bold text-[10px] bg-emerald-100 text-emerald-800 border border-emerald-300">
                              WON
                            </span>
                          ) : (
                            <span className="px-2.5 py-0.5 rounded-full font-bold text-[10px] bg-rose-100 text-rose-800 border border-rose-300">
                              LOST
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right font-black">
                          <span className={s.profit_loss >= 0 ? "text-emerald-600" : "text-rose-600"}>
                            {s.profit_loss >= 0 ? `+${s.profit_loss}` : s.profit_loss} u
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

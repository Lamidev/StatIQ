import React, { useState } from "react";
import { fetchFixturesByGameweek, generateSportyBetCode, buildAiTicket } from "../api/client";
import { Copy, Info, Calendar, Send, ShieldCheck, RefreshCw, CheckCircle2, ExternalLink, X, ChevronDown, ChevronUp, AlertCircle, Award, Trash2, Lock } from "lucide-react";
import { generateSafePick, buildSafeTicket, scoreFixtures } from "../utils/pickEngine";

export default function TicketBuilderTab() {
  const [builderMode, setBuilderMode] = useState("ACCUMULATOR"); // "ACCUMULATOR" or "ROLLOVER"

  // Standard Accumulator State
  const [leagueScope, setLeagueScope] = useState("MULTI");
  const [singleLeague, setSingleLeague] = useState("PL");
  const [gameweek, setGameweek] = useState(1);
  const [targetOdds, setTargetOdds] = useState(2.0);
  const [customOdds, setCustomOdds] = useState("500");
  const [useCustom, setUseCustom] = useState(false);
  const [useLiveOdds, setUseLiveOdds] = useState(false);

  // Rollover State
  const [rolloverRange, setRolloverRange] = useState("FRI_SUN"); // "FRI_SUN" (3 Days) or "FRI_WED" (5 Days)
  const [dailyTargetOdds, setDailyTargetOdds] = useState(1.50);
  const [startingStake, setStartingStake] = useState(5000);
  const [telegramAlerts, setTelegramAlerts] = useState(true);

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [result, setResult] = useState(null);
  const [rolloverResult, setRolloverResult] = useState(null);
  const [generatedCodes, setGeneratedCodes] = useState({});

  // Audit Logs & Rejected Picks UI State
  const [expandedAuditLogs, setExpandedAuditLogs] = useState({});
  const [showRejectedDrawer, setShowRejectedDrawer] = useState(false);

  // Code Generation Modal Popup State
  const [codeModalData, setCodeModalData] = useState(null);
  const [showCodeModal, setShowCodeModal] = useState(false);

  // Lock & Track Ticket Modal State
  const [showLockModal, setShowLockModal] = useState(false);
  const [lockTargetData, setLockTargetData] = useState(null);
  const [stakeInput, setStakeInput] = useState("1000");
  const [lockingTicket, setLockingTicket] = useState(false);
  const [lockedNotice, setLockedNotice] = useState(null);

  const handleLockTicketSubmit = async () => {
    if (!lockTargetData) return;
    setLockingTicket(true);
    try {
      const payload = {
        code: lockTargetData.code || "AI-BUILDER-TICKET",
        mode: builderMode,
        target_odds: lockTargetData.targetOdds || targetOdds,
        total_odds: lockTargetData.totalOdds || 2.0,
        stake: parseFloat(stakeInput) || 1000,
        selections: lockTargetData.selections || []
      };
      const res = await fetch("http://127.0.0.1:8000/api/v1/ticket-tracker/lock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        setShowLockModal(false);
        setLockedNotice("Ticket successfully locked into StatIQ Ticket Tracker! Track live settlements in the BetSlip Auditor tab.");
        setTimeout(() => setLockedNotice(null), 6000);
      }
    } catch (e) {}
    setLockingTicket(false);
  };

  const oddsPresetButtons = [2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 500.0, 1000.0];

  // Helper to dynamically calculate ideal leg bounds for a target total odds
  const getLegBoundsForOdds = (targetTotalOdds) => {
    const o = Math.max(1.1, parseFloat(targetTotalOdds) || 2.0);
    if (o <= 1.5) return { min: 1, max: 2, defaultAvgOdds: o };
    if (o <= 3.0) return { min: 2, max: 3, defaultAvgOdds: 1.35 };
    if (o <= 7.0) return { min: 4, max: 6, defaultAvgOdds: 1.38 };
    if (o <= 15.0) return { min: 6, max: 8, defaultAvgOdds: 1.38 };
    if (o <= 35.0) return { min: 8, max: 11, defaultAvgOdds: 1.36 };
    if (o <= 75.0) return { min: 11, max: 14, defaultAvgOdds: 1.35 };
    if (o <= 200.0) return { min: 13, max: 17, defaultAvgOdds: 1.34 };
    if (o <= 600.0) return { min: 17, max: 23, defaultAvgOdds: 1.33 };
    return { min: 20, max: 26, defaultAvgOdds: 1.32 };
  };

  /**
   * extractSafestSelection — delegates to the shared MatchIQ Pick Engine.
   * Uses Elo-based tier detection + diverse safe pick pools (Gate 1-4).
   * Falls back to Over 1.5 Goals when AI probabilities aren't available.
   *
   * Accepts an optional usedTypeCounts object to enforce Gate 4 diversity
   * across the current ticket being built.
   */
  const extractSafestSelection = (f, usedTypeCounts = {}) => {
    const pd = generateSafePick(f, usedTypeCounts);
    return {
      fixture_id: f.fixture_id || f.external_id,
      home_team: f.home_team || f.home || "Home",
      away_team: f.away_team || f.away || "Away",
      competition_code: f.competition_code || "PL",
      kickoff_datetime: f.kickoff_datetime,
      selection: pd.pick,
      selection_name: pd.pick,
      model_probability: pd.prob / 100,
      estimated_odds: pd.odds,
      tier: pd.tier,
      marketType: pd.marketType,
    };
  };

  const roundOdds = (val) => {
    return Math.max(1.10, Math.min(9.50, Math.round(val * 100) / 100));
  };

  // Build Accumulator Ticket dynamically using 5-Gate Pick Engine Backend API
  const handleBuildSafestTicket = async () => {
    setLoading(true);
    setErrorMsg(null);
    setResult(null);

    const finalOddsGoal = useCustom ? parseFloat(customOdds) || 50.0 : targetOdds;

    const payload = {
      target_odds: finalOddsGoal,
      mode: "ACCUMULATOR",
      league_scope: leagueScope,
      single_league: singleLeague,
      gameweek: gameweek,
      use_live_odds: useLiveOdds
    };

    const res = await buildAiTicket(payload);
    setLoading(false);

    if (!res || res.status === "TIMEOUT" || res.status === "HTTP_ERROR" || res.status === "ERROR") {
      setErrorMsg(
        res?.status === "TIMEOUT"
          ? "Request timed out (>15s). The engine is busy — please try again."
          : res?.status === "HTTP_ERROR"
          ? `Backend error (HTTP ${res.http_status}). Ensure backend is running.`
          : "MatchIQ 5-Gate Pick Engine failed to build ticket. Check backend logs."
      );
      return;
    }

    if (res.ticket) {
      const scopeLabel = leagueScope === "MULTI" ? "Multi-League (All Top Leagues)" : `${singleLeague} Only`;
      setResult({
        ticket: res.ticket,
        scenarios: [
          {
            scenario_id: `MATCHIQ-GW${gameweek}-${finalOddsGoal.toFixed(0)}X`,
            scope_label: scopeLabel,
            gameweek_label: `Gameweek ${gameweek}`,
            target_odds: finalOddsGoal,
            accumulated_odds: res.ticket.accumulated_odds,
            independence_assumption_probability: res.ticket.combined_probability,
            correlation_adjusted_probability: res.ticket.correlation_adjusted_probability,
            confidence_tier: res.ticket.confidence_tier,
            recommended_stake_pct: res.ticket.recommended_stake_pct,
            selections: res.ticket.approved_legs,
            rejected_picks: res.ticket.rejected_picks,
            total_evaluated: res.ticket.total_evaluated,
            decision_audit_summary: res.ticket.decision_audit_summary
          }
        ]
      });
    }
  };

  // Build Multi-Day Rollover Plan dynamically using 5-Gate Pick Engine Backend API
  const handleBuildRollover = async () => {
    setLoading(true);
    setErrorMsg(null);
    setRolloverResult(null);

    const isWeekend = rolloverRange === "FRI_SUN";
    const nDays = isWeekend ? 3 : 5;
    const targetTotalOdds = Math.pow(dailyTargetOdds, nDays);

    const payload = {
      target_odds: targetTotalOdds,
      mode: "ROLLOVER",
      league_scope: "MULTI",
      single_league: "PL",
      gameweek: gameweek,
      use_live_odds: useLiveOdds
    };

    const res = await buildAiTicket(payload);
    setLoading(false);

    if (!res || !res.ticket || !res.ticket.approved_legs) {
      setErrorMsg("Failed to build Rollover plan. Try adjusting target daily odds.");
      return;
    }

    const dayLabels = isWeekend
      ? ["Day 1 (Friday)", "Day 2 (Saturday)", "Day 3 (Sunday)"]
      : ["Day 1 (Friday)", "Day 2 (Saturday)", "Day 3 (Sunday)", "Day 4 (Tuesday UCL)", "Day 5 (Wednesday UCL)"];

    let daysList = [];
    let currentStake = startingStake;
    const legs = res.ticket.approved_legs;

    dayLabels.forEach((label, idx) => {
      const match = legs[idx % legs.length] || {
        home_team: "Arsenal", away_team: "Wolves", selection_name: "Arsenal or Draw", model_probability: 0.92, estimated_odds: dailyTargetOdds
      };
      const odds = match.estimated_odds || dailyTargetOdds;
      const nextPayout = currentStake * odds;

      daysList.push({
        day: label,
        fixture: `${match.home_team} vs ${match.away_team}`,
        pick: match.selection_name || match.selection,
        prob: match.model_probability,
        odds: odds,
        payout: roundOddsVal(nextPayout),
        confidence_tier: match.confidence_tier || "HIGH",
        decision_audit_log: match.decision_audit_log
      });

      currentStake = nextPayout;
    });

    const totalMultiplier = res.ticket.accumulated_odds || daysList.reduce((acc, curr) => acc * curr.odds, 1.0);
    const finalEstimatedPayout = startingStake * totalMultiplier;

    const codeRes = await generateSportyBetCode(daysList);
    const code = codeRes.booking_code || "BC-ROLLOVER-LIVE";

    setRolloverResult({
      days: daysList,
      totalMultiplier: roundOddsVal(totalMultiplier),
      finalEstimatedPayout: roundOddsVal(finalEstimatedPayout),
      bookingCode: code,
      confidence_tier: res.ticket.confidence_tier,
      recommended_stake_pct: res.ticket.recommended_stake_pct,
      decision_audit_summary: res.ticket.decision_audit_summary,
      rejected_picks: res.ticket.rejected_picks
    });
  };

  const roundOddsVal = (val) => Math.round(val * 100) / 100;

  // Generate Booking Code & Trigger UI/UX Modal Popup
  const handleGenerateCode = async (id, selections, scenarioLabel) => {
    const res = await generateSportyBetCode(selections);

    // Handle failure cases — don't fabricate random codes
    if (!res || res.status === "ERROR" || !res.booking_code) {
      const msg = res?.status === "MATCH_NOT_FOUND"
        ? (res.message || "No SportyBet matches found for the selected fixtures. Try again closer to kickoff when the events appear on SportyBet.")
        : "Failed to generate booking code. Ensure the backend is running and try again.";
      setErrorMsg(msg);
      return;
    }

    const code = res.booking_code;
    setGeneratedCodes(prev => ({ ...prev, [id]: code }));

    // Trigger Popup Modal
    setCodeModalData({
      code,
      label: scenarioLabel || `Gameweek ${gameweek} AI Ticket`,
      selections,
      loadUrl: res.load_url || `https://www.sportybet.com/ng/?shareCode=${code}`
    });
    setShowCodeModal(true);
  };

  const copySelectionsAsText = (selections) => {
    const text = selections.map(s => `• ${s.home_team || s.fixture} -> ${s.selection_name || s.selection || s.pick}`).join("\n");
    navigator.clipboard.writeText(text);
    alert("Copied Selections List to clipboard:\n\n" + text);
  };

  const handleRemoveAccumulatorSelection = (scenarioId, selIdx) => {
    if (!result || !result.scenarios) return;
    const updatedScenarios = result.scenarios.map((scn) => {
      if (scn.scenario_id !== scenarioId) return scn;
      const newSelections = scn.selections.filter((_, idx) => idx !== selIdx);
      if (newSelections.length === 0) return null;
      const newAccOdds = newSelections.reduce((acc, p) => acc * (p.estimated_odds || p.odds || 1.2), 1.0);
      const newWinProb = newSelections.reduce((acc, p) => acc * (p.model_probability || p.prob || 0.8), 1.0);
      return {
        ...scn,
        accumulated_odds: Math.round(newAccOdds * 100) / 100,
        independence_assumption_probability: Math.round(newWinProb * 100) / 100,
        selections: newSelections
      };
    }).filter(Boolean);

    if (updatedScenarios.length === 0) {
      setResult(null);
    } else {
      setResult({ ...result, scenarios: updatedScenarios });
    }
  };

  const handleRemoveAccumulatorTicket = (scenarioId) => {
    if (!result || !result.scenarios) return;
    const updated = result.scenarios.filter(s => s.scenario_id !== scenarioId);
    if (updated.length === 0) {
      setResult(null);
    } else {
      setResult({ ...result, scenarios: updated });
    }
  };

  const handleRemoveRolloverDay = (dayIdx) => {
    if (!rolloverResult || !rolloverResult.days) return;
    const newDays = rolloverResult.days.filter((_, idx) => idx !== dayIdx);
    if (newDays.length === 0) {
      setRolloverResult(null);
      return;
    }
    let currentStake = startingStake;
    const updatedDays = newDays.map((item) => {
      const nextPayout = currentStake * item.odds;
      const updatedItem = { ...item, payout: Math.round(nextPayout * 100) / 100 };
      currentStake = nextPayout;
      return updatedItem;
    });
    const newTotalMultiplier = updatedDays.reduce((acc, curr) => acc * curr.odds, 1.0);
    const newFinalPayout = startingStake * newTotalMultiplier;
    setRolloverResult({
      ...rolloverResult,
      days: updatedDays,
      totalMultiplier: Math.round(newTotalMultiplier * 100) / 100,
      finalEstimatedPayout: Math.round(newFinalPayout * 100) / 100
    });
  };

  const handleClearRollover = () => {
    setRolloverResult(null);
  };

  return (
    <div className="space-y-6 relative">
      {/* Sleek Booking Code Confirmation Modal Popup */}
      {showCodeModal && codeModalData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl p-6 max-w-lg w-full border border-slate-200 shadow-2xl space-y-5 relative">
            <button
              onClick={() => setShowCodeModal(false)}
              className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 transition-all"
            >
              <X className="w-4 h-4" />
            </button>

            {/* Header Badge */}
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 flex-shrink-0">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <span className="text-[10px] font-extrabold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200 uppercase">
                  SportyBet Code Ready
                </span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5">
                  Booking Code Generated!
                </h3>
              </div>
            </div>

            {/* Code Display Box */}
            <div className="bg-slate-900 text-white p-5 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider block">
                  SportyBet Booking Code
                </span>
                <span className="text-2xl font-extrabold text-emerald-400 tracking-wider">
                  {codeModalData.code}
                </span>
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(codeModalData.code);
                  alert(`Copied SportyBet Booking Code: ${codeModalData.code}`);
                }}
                className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-extrabold text-xs flex items-center space-x-1.5 transition-all shadow-sm"
              >
                <Copy className="w-4 h-4" />
                <span>Copy Code</span>
              </button>
            </div>

            {/* Action Buttons */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <a
                href={codeModalData.loadUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="py-2.5 px-4 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1.5 transition-all"
              >
                <ExternalLink className="w-4 h-4" />
                <span>Open on SportyBet</span>
              </a>

              <button
                onClick={() => copySelectionsAsText(codeModalData.selections)}
                className="py-2.5 px-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 hover:bg-slate-200 text-xs font-extrabold flex items-center justify-center space-x-1.5 transition-all"
              >
                <Copy className="w-4 h-4" />
                <span>Copy Selections Text</span>
              </button>
            </div>

            {/* Included Selections Breakdown */}
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
                Included Ticket Selections ({codeModalData.selections.length} Picks)
              </span>
              {codeModalData.selections.map((s, idx) => (
                <div key={idx} className="bg-slate-50 p-2.5 rounded-xl border border-slate-200 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-slate-900 block">
                      {s.home_team || s.fixture} {s.away_team ? `vs ${s.away_team}` : ""}
                    </span>
                    <span className="text-slate-600 font-semibold text-[11px]">
                      Pick: {s.selection || s.pick}
                    </span>
                  </div>
                  <span className="font-extrabold text-emerald-700 text-xs">
                    {Math.round((s.model_probability || s.prob || 0.75) * 100)}% Win Chance
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Lock Ticket Confirmation Modal */}
      {showLockModal && lockTargetData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full border border-slate-200 shadow-2xl space-y-5 relative">
            <button
              onClick={() => setShowLockModal(false)}
              className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 transition-all"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 flex-shrink-0">
                <Lock className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200 uppercase">
                  MatchIQ Ticket Tracker
                </span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5">
                  Lock & Track Built Ticket
                </h3>
              </div>
            </div>

            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Ticket Code:</span>
                <span className="font-extrabold text-slate-900">{lockTargetData.code}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Total Odds:</span>
                <span className="font-extrabold text-emerald-700">~{lockTargetData.totalOdds}x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Included Legs:</span>
                <span className="font-bold text-slate-800">{lockTargetData.selections?.length || 0} Picks</span>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Enter Stake Amount (NGN)
              </label>
              <input
                type="number"
                value={stakeInput}
                onChange={(e) => setStakeInput(e.target.value)}
                placeholder="1000"
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <button
                onClick={() => setShowLockModal(false)}
                className="py-2.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-extrabold hover:bg-slate-200 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleLockTicketSubmit}
                disabled={lockingTicket}
                className="py-2.5 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1 transition-all"
              >
                {lockingTicket ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
                <span>{lockingTicket ? "Locking..." : "Confirm Lock"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notice Banner */}
      {lockedNotice && (
        <div className="bg-emerald-50 border border-emerald-200 p-4 rounded-2xl flex items-center space-x-3 text-xs text-emerald-900 animate-in fade-in duration-200 shadow-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
          <span className="font-bold">{lockedNotice}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200">
        <h2 className="text-xl font-extrabold text-slate-900">
          AI Ticket & Rollover Builder
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Build target odds accumulators or generate <strong>Multi-Day Daily Rollover Strategies (Fri-Sun / Fri-Wed)</strong> with real live 2026/27 fixture data and StatIQ probabilities.
        </p>
      </div>

      {/* Mode Selector Tabs */}
      <div className="bg-white p-2 rounded-2xl border border-slate-200 flex space-x-2">
        <button
          onClick={() => setBuilderMode("ACCUMULATOR")}
          className={`flex-1 py-2.5 rounded-xl text-xs font-extrabold transition-all ${
            builderMode === "ACCUMULATOR"
              ? "bg-slate-900 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          Target Odds Accumulator Builder (2x to 1000x)
        </button>

        <button
          onClick={() => setBuilderMode("ROLLOVER")}
          className={`flex-1 py-2.5 rounded-xl text-xs font-extrabold transition-all ${
            builderMode === "ROLLOVER"
              ? "bg-slate-900 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          Safest Multi-Day Rollover Engine (Fri-Sun / Fri-Wed)
        </button>
      </div>

      {/* MODE 1: STANDARD ACCUMULATOR BUILDER */}
      {builderMode === "ACCUMULATOR" ? (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">1. League Scope</label>
              <select
                value={leagueScope}
                onChange={(e) => setLeagueScope(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="MULTI">Multi-League (All Top Leagues Combined)</option>
                <option value="SINGLE">Single League Only</option>
              </select>
            </div>

            {leagueScope === "SINGLE" && (
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Select Target League</label>
                <select
                  value={singleLeague}
                  onChange={(e) => setSingleLeague(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
                >
                  <option value="PL">Premier League (England)</option>
                  <option value="ELC">Championship (England)</option>
                  <option value="PD">La Liga (Spain)</option>
                  <option value="SA">Serie A (Italy)</option>
                  <option value="BL1">Bundesliga (Germany)</option>
                  <option value="FL1">Ligue 1 (France)</option>
                  <option value="DED">Eredivisie (Netherlands)</option>
                  <option value="PPL">Primeira Liga (Portugal)</option>
                </select>
              </div>
            )}

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">2. Target Gameweek</label>
              <select
                value={gameweek}
                onChange={(e) => setGameweek(parseInt(e.target.value))}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                {Array.from({ length: 38 }, (_, i) => i + 1).map((gw) => (
                  <option key={gw} value={gw}>Gameweek {gw}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            <label className="text-xs font-semibold text-slate-700 block mb-2">
              3. Select Target Odds Goal (2.0x to 1,000.0x+)
            </label>

            <div className="flex flex-wrap items-center gap-2">
              {oddsPresetButtons.map((val) => (
                <button
                  key={val}
                  onClick={() => {
                    setTargetOdds(val);
                    setCustomOdds("");
                    setUseCustom(false);
                  }}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-extrabold transition-all ${
                    !useCustom && targetOdds === val
                      ? "bg-slate-900 text-white shadow-sm"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  ~{val.toFixed(0)} Odds
                </button>
              ))}

              <div className="flex items-center gap-1.5 ml-2">
                <input
                  type="number"
                  placeholder="Custom"
                  value={customOdds}
                  onChange={(e) => {
                    const valStr = e.target.value;
                    setCustomOdds(valStr);
                    setUseCustom(true);
                    const parsed = parseFloat(valStr);
                    if (!isNaN(parsed) && parsed > 1.0) {
                      setTargetOdds(parsed);
                    }
                  }}
                  className="w-20 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                />
                <span className="text-xs text-slate-400 font-extrabold">Odds</span>
              </div>
            </div>
          </div>

            <div className="flex items-center justify-between pt-2">
              <label className="flex items-center space-x-2 cursor-pointer text-xs font-bold text-slate-700">
                <input
                  type="checkbox"
                  checked={useLiveOdds}
                  onChange={(e) => setUseLiveOdds(e.target.checked)}
                  className="rounded text-slate-900 focus:ring-slate-900"
                />
                <span>Use Live SportyBet Odds (Enables Gate 3 Value Edge Calculation)</span>
              </label>
            </div>

          {errorMsg && (
            <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start space-x-3 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-extrabold block">Builder Execution Notice</span>
                <p className="mt-0.5">{errorMsg}</p>
              </div>
            </div>
          )}

          <div className="pt-2">
            <button
              onClick={handleBuildSafestTicket}
              disabled={loading}
              className="w-full py-3 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
              <span>{loading ? `Running StatIQ 5-Gate Engine (GW${gameweek})...` : `Build Safest 5-Gate AI Ticket (GW${gameweek})`}</span>
            </button>
          </div>
        </div>
      ) : (
        /* MODE 2: MULTI-DAY ROLLOVER ENGINE */
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">1. Rollover Schedule Range</label>
              <select
                value={rolloverRange}
                onChange={(e) => setRolloverRange(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="FRI_SUN">Weekend Rollover (Friday to Sunday — 3 Days)</option>
                <option value="FRI_WED">UCL Full Week (Friday to Wednesday — 5 Days)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">2. Target Daily Odds</label>
              <select
                value={dailyTargetOdds}
                onChange={(e) => setDailyTargetOdds(parseFloat(e.target.value))}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value={1.30}>~1.30 Daily Odds (Safest Ultra High P)</option>
                <option value={1.50}>~1.50 Daily Odds (Balanced Safe)</option>
                <option value={1.80}>~1.80 Daily Odds</option>
                <option value={2.00}>~2.00 Daily Odds</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">3. Starting Stake (NGN)</label>
              <input
                type="number"
                value={startingStake}
                onChange={(e) => setStartingStake(parseInt(e.target.value) || 1000)}
                placeholder="5000"
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              />
            </div>
          </div>

          {/* Telegram Alert Toggle */}
          <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Send className="w-4 h-4 text-sky-600" />
              <span className="text-xs font-bold text-slate-800">
                Automated 1:00 AM Telegram Notification Alerts
              </span>
            </div>

            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={telegramAlerts}
                onChange={(e) => setTelegramAlerts(e.target.checked)}
                className="w-4 h-4 rounded text-slate-900 focus:ring-slate-900"
              />
              <span className="text-xs text-slate-600 font-medium">Enabled (Sends Daily Pick at 1 AM)</span>
            </label>
          </div>

          <div className="pt-2">
            <button
              onClick={handleBuildRollover}
              disabled={loading}
              className="w-full py-3 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
              <span>{loading ? "Calculating Daily Safest Picks..." : "Generate Safest Live Rollover Plan"}</span>
            </button>
          </div>
        </div>
      )}


      {/* MODE 1 RESULTS */}
      {builderMode === "ACCUMULATOR" && result && (
        <div className="space-y-6">
          {result.scenarios?.map((scn) => {
            const code = generatedCodes[scn.scenario_id];

            if (scn.error) {
              return (
                <div key={scn.scenario_id} className="bg-amber-50 border border-amber-200 p-6 rounded-2xl text-xs text-amber-800">
                  <p className="font-extrabold text-sm">{scn.error}</p>
                  <p className="mt-1">Try selecting a different gameweek or league scope.</p>
                </div>
              );
            }

            return (
              <div key={scn.scenario_id} className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm relative">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-slate-900 text-sm">
                        5-Gate Approved Accumulator ({scn.selections.length} Legs)
                      </span>
                      {scn.confidence_tier && (
                        <span className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                          scn.confidence_tier === "ELITE" ? "bg-purple-100 text-purple-900 border border-purple-200" :
                          scn.confidence_tier === "HIGH" ? "bg-emerald-100 text-emerald-900 border border-emerald-200" :
                          scn.confidence_tier === "SOLID" ? "bg-blue-100 text-blue-900 border border-blue-200" :
                          "bg-amber-100 text-amber-900 border border-amber-200"
                        }`}>
                          {scn.confidence_tier} Tier
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500 font-medium mt-0.5 block">
                      Scope: <strong>{scn.scope_label}</strong> • Combined Odds: <strong>~{scn.accumulated_odds}x</strong> (Target: ~{scn.target_odds}x)
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    {scn.recommended_stake_pct > 0 && (
                      <span className="text-xs font-extrabold text-indigo-700 bg-indigo-50 px-3 py-1 rounded-full border border-indigo-200 flex items-center gap-1">
                        <Award className="w-3.5 h-3.5 text-indigo-600" />
                        <span>Rec. Stake: {scn.recommended_stake_pct}% Bankroll</span>
                      </span>
                    )}

                    <span className="text-xs font-extrabold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
                      {((scn.correlation_adjusted_probability || scn.independence_assumption_probability) * 100).toFixed(1)}% Win Chance
                    </span>

                    <button
                      onClick={() => handleRemoveAccumulatorTicket(scn.scenario_id)}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
                      title="Delete / Remove Ticket"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="space-y-3">
                  {scn.selections.map((sel, idx) => {
                    const logKey = `${scn.scenario_id}_${idx}`;
                    const isExpanded = expandedAuditLogs[logKey];
                    const tier = sel.confidence_tier || "SOLID";

                    return (
                      <div key={idx} className="bg-slate-50 p-3.5 rounded-xl border border-slate-200 space-y-2">
                        <div className="flex items-center justify-between text-xs">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-extrabold text-slate-900">
                                [{sel.competition || sel.competition_code}] {sel.home_team} vs {sel.away_team}
                              </span>
                              <span className={`text-[9px] font-extrabold px-2 py-0.2 rounded uppercase ${
                                tier === "ELITE" ? "bg-purple-100 text-purple-800" :
                                tier === "HIGH" ? "bg-emerald-100 text-emerald-800" :
                                tier === "SOLID" ? "bg-blue-100 text-blue-800" :
                                "bg-amber-100 text-amber-800"
                              }`}>
                                {tier}
                              </span>
                            </div>
                            <span className="text-slate-700 font-semibold text-xs mt-0.5 block">
                              Pick: <strong>{sel.selection_name || sel.selection}</strong>
                            </span>
                          </div>

                          <div className="flex items-center space-x-3">
                            <div className="text-right">
                              <span className="font-extrabold text-emerald-700 block">
                                {(sel.model_probability * 100).toFixed(0)}% Win Chance
                              </span>
                              <span className="text-[10px] text-slate-500 font-medium">
                                Odds: {sel.estimated_odds}
                              </span>
                            </div>

                            <button
                              onClick={() => setExpandedAuditLogs(prev => ({ ...prev, [logKey]: !prev[logKey] }))}
                              className="p-1 text-slate-500 hover:text-slate-800 rounded flex items-center gap-0.5 text-[10px] font-bold border border-slate-200 hover:bg-slate-200 transition-all"
                              title="Toggle 5-Gate Decision Audit Trail"
                            >
                              <span>Audit</span>
                              {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            </button>

                            <button
                              onClick={() => handleRemoveAccumulatorSelection(scn.scenario_id, idx)}
                              className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-100 rounded transition-all"
                              title="Remove selection from ticket"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>

                        {/* Expandable 5-Gate Audit Decision Log */}
                        {isExpanded && sel.decision_audit_log && (
                          <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-[11px] font-mono space-y-1 mt-2 border border-slate-800">
                            <span className="text-[10px] text-emerald-400 font-extrabold uppercase block tracking-wider mb-1">
                              MatchIQ 5-Gate Decision Pipeline Audit Log:
                            </span>
                            {sel.decision_audit_log.map((logLine, lIdx) => (
                              <div key={lIdx} className="flex items-start gap-1.5">
                                <span className="text-emerald-500">✓</span>
                                <span>{logLine}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Collapsible Rejected Picks Section */}
                {scn.rejected_picks && scn.rejected_picks.length > 0 && (
                  <div className="pt-2 border-t border-slate-100">
                    <button
                      onClick={() => setShowRejectedDrawer(!showRejectedDrawer)}
                      className="text-xs text-slate-500 hover:text-slate-800 font-bold flex items-center gap-1.5 transition-all"
                    >
                      <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                      <span>{showRejectedDrawer ? "Hide" : "View"} {scn.rejected_picks.length} Evaluated Fixtures Rejected by 5-Gate Pipeline</span>
                      {showRejectedDrawer ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>

                    {showRejectedDrawer && (
                      <div className="mt-3 space-y-2 bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs">
                        {scn.rejected_picks.map((rej, rIdx) => (
                          <div key={rIdx} className="flex items-center justify-between border-b border-slate-200 pb-1.5 last:border-0 last:pb-0">
                            <span className="font-bold text-slate-800">[{rej.competition}] {rej.fixture}</span>
                            <span className="text-rose-600 font-medium text-[11px]">{rej.rejection_reason}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                  <button
                    onClick={() => handleGenerateCode(scn.scenario_id, scn.selections, `Gameweek ${gameweek} Ticket`)}
                    className="flex-1 py-3 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center shadow-sm w-full sm:w-auto"
                  >
                    <span>Get SportyBet Booking Code</span>
                  </button>

                  <button
                    onClick={() => {
                      setLockTargetData({
                        code: generatedCodes[scn.scenario_id] || `GW${gameweek}-ACC`,
                        targetOdds: scn.target_odds,
                        totalOdds: scn.accumulated_odds,
                        selections: scn.selections
                      });
                      setShowLockModal(true);
                    }}
                    className="px-4 py-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 w-full sm:w-auto"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    <span>Lock & Track Ticket</span>
                  </button>

                  <button
                    onClick={() => handleRemoveAccumulatorTicket(scn.scenario_id)}
                    className="px-4 py-3 rounded-xl bg-slate-100 border border-slate-200 text-slate-700 hover:text-rose-600 text-xs font-extrabold hover:bg-rose-50 transition-all flex items-center justify-center space-x-1 w-full sm:w-auto"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Clear Ticket</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* MODE 2 ROLLOVER RESULTS */}
      {builderMode === "ROLLOVER" && rolloverResult && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6 shadow-sm relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block">
                  {rolloverRange === "FRI_SUN" ? "3-Day Weekend Rollover Plan" : "5-Day Champions League Rollover Plan"}
                </span>
                {rolloverResult.recommended_stake_pct > 0 && (
                  <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200 flex items-center gap-1">
                    <Award className="w-3 h-3 text-indigo-600" />
                    <span>Quarter-Kelly Rec. Stake: {rolloverResult.recommended_stake_pct}% Bankroll</span>
                  </span>
                )}
              </div>
              <h3 className="text-lg font-extrabold text-slate-900 mt-0.5">
                Starting Stake: ₦{startingStake.toLocaleString()} → Est. Payout: ₦{Math.round(rolloverResult.finalEstimatedPayout).toLocaleString()} ({rolloverResult.totalMultiplier.toFixed(2)}x Total Return)
              </h3>
            </div>

            <div className="flex items-center space-x-3">
              <div className="bg-slate-900 text-white px-4 py-2 rounded-xl text-right">
                <span className="text-[10px] text-slate-400 block font-medium">SportyBet Booking Code</span>
                <span className="text-base font-extrabold text-emerald-400">{rolloverResult.bookingCode}</span>
              </div>

              <button
                onClick={handleClearRollover}
                className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all"
                title="Clear Rollover Plan"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Day-by-Day Schedule */}
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <h4 className="text-xs font-extrabold text-slate-700 uppercase">
                Daily Safest Picks Schedule ({rolloverResult.days.length} Days Active)
              </h4>
              <button
                onClick={handleClearRollover}
                className="text-xs font-bold text-rose-600 hover:underline flex items-center space-x-1"
              >
                <Trash2 className="w-3 h-3" />
                <span>Remove All Rollover Days</span>
              </button>
            </div>

            {rolloverResult.days.map((d, idx) => {
              const rLogKey = `roll_${idx}`;
              const isExpanded = expandedAuditLogs[rLogKey];
              const tier = d.confidence_tier || "HIGH";

              return (
                <div key={idx} className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                          {d.day}
                        </span>
                        <span className={`text-[9px] font-extrabold px-2 py-0.2 rounded uppercase ${
                          tier === "ELITE" ? "bg-purple-100 text-purple-800" :
                          tier === "HIGH" ? "bg-emerald-100 text-emerald-800" :
                          tier === "SOLID" ? "bg-blue-100 text-blue-800" :
                          "bg-amber-100 text-amber-800"
                        }`}>
                          {tier}
                        </span>
                      </div>
                      <span className="text-sm font-extrabold text-slate-900 block">
                        {d.fixture}
                      </span>
                      <span className="text-slate-600 font-medium">
                        Safest Selection: <strong>{d.pick}</strong> (Odds: {d.odds.toFixed(2)})
                      </span>
                    </div>

                    <div className="flex items-center space-x-4">
                      <div className="text-right">
                        <span className="text-[10px] text-slate-400 block font-medium">Model Win Probability</span>
                        <span className="text-sm font-extrabold text-emerald-700">{(d.prob * 100).toFixed(0)}% Win Chance</span>
                        <span className="text-[10px] text-slate-500 block">Rolling Payout: ₦{Math.round(d.payout).toLocaleString()}</span>
                      </div>

                      {d.decision_audit_log && (
                        <button
                          onClick={() => setExpandedAuditLogs(prev => ({ ...prev, [rLogKey]: !prev[rLogKey] }))}
                          className="p-1 text-slate-500 hover:text-slate-800 rounded flex items-center gap-0.5 text-[10px] font-bold border border-slate-200 hover:bg-slate-200 transition-all"
                          title="Toggle 5-Gate Decision Audit Trail"
                        >
                          <span>Audit</span>
                          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                      )}

                      <button
                        onClick={() => handleRemoveRolloverDay(idx)}
                        className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-100 rounded-lg transition-all"
                        title="Remove day from Rollover plan"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Expandable Audit Log */}
                  {isExpanded && d.decision_audit_log && (
                    <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-[11px] font-mono space-y-1 mt-2 border border-slate-800">
                      <span className="text-[10px] text-emerald-400 font-extrabold uppercase block tracking-wider mb-1">
                        MatchIQ 5-Gate Decision Audit Log ({d.day}):
                      </span>
                      {d.decision_audit_log.map((logLine, lIdx) => (
                        <div key={lIdx} className="flex items-start gap-1.5">
                          <span className="text-emerald-500">✓</span>
                          <span>{logLine}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
            <button
              onClick={() => handleGenerateCode("ROLLOVER", rolloverResult.days, "Rollover Plan")}
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>Get & Preview Rollover Booking Code</span>
            </button>

            <button
              onClick={() => {
                setLockTargetData({
                  code: rolloverResult.bookingCode || "ROLLOVER-PLAN",
                  targetOdds: dailyTargetOdds,
                  totalOdds: rolloverResult.totalMultiplier,
                  selections: rolloverResult.days
                });
                setShowLockModal(true);
              }}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-extrabold hover:bg-indigo-100 flex items-center justify-center space-x-1.5"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Lock & Track Plan</span>
            </button>

            <button
              onClick={() => copySelectionsAsText(rolloverResult.days)}
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 text-xs font-extrabold hover:bg-slate-200"
            >
              Copy Rollover Daily List
            </button>

            <button
              onClick={handleClearRollover}
              className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-extrabold hover:bg-rose-100 flex items-center justify-center space-x-1"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Dismiss Rollover</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

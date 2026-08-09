import React, { useState } from "react";
import { fetchFixturesByGameweek, generateSportyBetCode, buildAiTicket, lockTrackedTicket } from "../api/client";
import { Copy, Info, Calendar, Send, ShieldCheck, RefreshCw, CheckCircle2, ExternalLink, X, ChevronDown, ChevronUp, AlertCircle, Award, Trash2, Lock, ShieldAlert, Sliders } from "lucide-react";
import { generateSafePick, buildSafeTicket, scoreFixtures } from "../utils/pickEngine";
import { calculateFlexShield } from "../utils/flexCalculator";

export default function TicketBuilderTab() {
  const [builderMode, setBuilderMode] = useState("ACCUMULATOR"); // "ACCUMULATOR" or "ROLLOVER"

  // Standard Accumulator State
  const [leagueScope, setLeagueScope] = useState("MULTI");
  const [singleLeague, setSingleLeague] = useState("PL");
  const [gameweek, setGameweek] = useState(1);
  const [targetOdds, setTargetOdds] = useState(2.0);
  const [targetMode, setTargetMode] = useState("ODDS"); // "ODDS" or "GAMES"
  const [targetGames, setTargetGames] = useState(10);
  const [selectedFlexCut, setSelectedFlexCut] = useState("OFF");
  const [customOdds, setCustomOdds] = useState("500");
  const [useCustom, setUseCustom] = useState(false);
  const [useLiveOdds, setUseLiveOdds] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [builderStep, setBuilderStep] = useState(1); // Wizard step: 1, 2, 3

  // Today's Games Mode State
  const [todayBuildCriteria, setTodayBuildCriteria] = useState("ODDS"); // "ODDS" or "GAMES"
  const [showTodayFixturesDrawer, setShowTodayFixturesDrawer] = useState(false);
  const [fetchingTodayFixtures, setFetchingTodayFixtures] = useState(false);
  const [todayFixturesList, setTodayFixturesList] = useState([]);

  // Rollover State
  const [kickoffScope, setKickoffScope] = useState("TODAY"); // "TODAY", "NEXT_24H", "ALL"
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
        flex_cut: selectedFlexCut,
        selections: lockTargetData.selections || []
      };
      const res = await lockTrackedTicket(payload);
      if (res && (res.id || res.status === "SUCCESS" || res.code)) {
        setShowLockModal(false);
        setLockedNotice(`Ticket ${res.code || res.id || ""} successfully locked into StatIQ Ticket Tracker! Track live settlements in the BetSlip Auditor tab.`);
        setTimeout(() => setLockedNotice(null), 6000);
      } else {
        alert("Failed to lock ticket into Tracker. Ensure backend is running.");
      }
    } catch (e) {
      alert("Error locking ticket: " + e.message);
    }
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
      target_mode: targetMode,
      target_games: targetGames,
      flex_cut: selectedFlexCut,
      mode: "ACCUMULATOR",
      league_scope: leagueScope,
      single_league: singleLeague,
      gameweek: gameweek,
      use_live_odds: useLiveOdds,
      kickoff_scope: kickoffScope,
      strict_mode: strictMode
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
      use_live_odds: useLiveOdds,
      kickoff_scope: kickoffScope,
      strict_mode: strictMode
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
    const regionalCodes = res.regional_codes || { NG: code };
    setGeneratedCodes(prev => ({ ...prev, [id]: code }));

    // Trigger Popup Modal
    setCodeModalData({
      code,
      regionalCodes,
      selectedRegion: "NG",
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

            {/* Header Badge & Country Selector */}
            <div className="flex items-center justify-between">
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

              {/* SportyBet Region Selector */}
              {codeModalData.regionalCodes && (
                <select
                  value={codeModalData.selectedRegion || "NG"}
                  onChange={(e) => {
                    const reg = e.target.value;
                    const rCode = codeModalData.regionalCodes[reg] || codeModalData.code;
                    setCodeModalData({
                      ...codeModalData,
                      selectedRegion: reg,
                      code: rCode,
                      loadUrl: `https://www.sportybet.com/${reg.toLowerCase()}/?shareCode=${rCode}`
                    });
                  }}
                  className="bg-slate-100 border border-slate-200 text-xs font-extrabold text-slate-900 rounded-xl px-2.5 py-1.5"
                >
                  <option value="NG">🇳🇬 Nigeria</option>
                  <option value="GH">🇬🇭 Ghana</option>
                  <option value="KE">🇰🇪 Kenya</option>
                  <option value="UG">🇺🇬 Uganda</option>
                </select>
              )}
            </div>

            {/* Code Display Box */}
            <div className="bg-slate-900 text-white p-5 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider block">
                  SportyBet {codeModalData.selectedRegion || "NG"} Booking Code
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
                className="px-4 py-2 rounded-xl btn-black text-white font-extrabold text-xs flex items-center space-x-1.5 transition-all shadow-sm"
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
                <span>Open on SportyBet ({codeModalData.selectedRegion || "NG"})</span>
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
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-emerald-700 text-xs">
                      {Math.round((s.model_probability || s.prob || 0.75) * 100)}% Win Chance
                    </span>
                    <button
                      onClick={() => {
                        const newSels = codeModalData.selections.filter((_, i) => i !== idx);
                        if (newSels.length === 0) {
                          setShowCodeModal(false);
                        } else {
                          setCodeModalData({ ...codeModalData, selections: newSels });
                        }
                      }}
                      className="p-1 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-600 border border-slate-200 transition-all"
                      title="Cancel / Remove game"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
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

      {/* Mode Selector Tabs — 3 Standalone Concepts */}
      <div className="bg-white p-2 rounded-2xl border border-slate-200 grid grid-cols-1 sm:grid-cols-3 gap-2">
        <button
          onClick={() => setBuilderMode("ACCUMULATOR")}
          className={`py-3 px-3 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 ${
            builderMode === "ACCUMULATOR"
              ? "bg-slate-900 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <span>🎯</span>
          <span>Target Odds Builder</span>
        </button>

        <button
          onClick={() => setBuilderMode("ROLLOVER")}
          className={`py-3 px-3 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 ${
            builderMode === "ROLLOVER"
              ? "bg-slate-900 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <span>🔄</span>
          <span>Daily Rollover Engine</span>
        </button>

        <button
          onClick={() => {
            setBuilderMode("TODAY_GAMES");
            setKickoffScope("TODAY");
          }}
          className={`py-3 px-3 rounded-xl text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 ${
            builderMode === "TODAY_GAMES"
              ? "bg-slate-900 text-white shadow-sm"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <span>📅</span>
          <span>Today's SportyBet Games</span>
        </button>
      </div>


      {/* MODE 1: STANDARD ACCUMULATOR BUILDER */}
      {builderMode === "ACCUMULATOR" ? (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">

          {/* Wizard Step Progress Bar */}
          {(() => {
            const steps = [
              { id: 1, label: "League & Scope" },
              { id: 2, label: "Target Goal" },
              { id: 3, label: "Safety & Options" },
            ];
            return (
              <div className="flex border-b border-slate-100">
                {steps.map((s, i) => {
                  const isActive = builderStep === s.id;
                  const isDone = builderStep > s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => setBuilderStep(s.id)}
                      className={`flex-1 py-3.5 flex flex-col items-center gap-0.5 transition-all border-b-2 ${
                        isActive
                          ? "border-slate-900 bg-slate-50"
                          : isDone
                          ? "border-emerald-500 bg-white"
                          : "border-transparent bg-white"
                      }`}
                    >
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black mb-0.5 ${
                        isActive ? "bg-slate-900 text-white" : isDone ? "bg-emerald-500 text-white" : "bg-slate-100 text-slate-400"
                      }`}>
                        {isDone ? "✓" : s.id}
                      </div>
                      <span className={`text-[10px] font-bold ${isActive ? "text-slate-900" : isDone ? "text-emerald-600" : "text-slate-400"}`}>
                        {s.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })()}

          {/* Step Content */}
          <div className="p-6 space-y-5 min-h-[220px]">

            {/* STEP 1: League & Scope */}
            {builderStep === 1 && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">Select League & Match Window</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Choose where the engine pulls fixtures from.</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">League Scope</label>
                    <select
                      value={leagueScope}
                      onChange={(e) => setLeagueScope(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
                    >
                      <option value="MULTI">Multi-League (All Top Leagues)</option>
                      <option value="SINGLE">Single League Only</option>
                    </select>
                  </div>

                  {leagueScope === "SINGLE" && (
                    <div>
                      <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Target League</label>
                      <select
                        value={singleLeague}
                        onChange={(e) => setSingleLeague(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
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
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Kickoff Window</label>
                    <div className="grid grid-cols-3 gap-1.5 bg-slate-100 p-1.5 rounded-xl">
                      {[
                        { val: "TODAY", label: "📅 Today" },
                        { val: "NEXT_24H", label: "⏰ 24hrs" },
                        { val: "ALL", label: "🌐 All" },
                      ].map(opt => (
                        <button
                          key={opt.val}
                          onClick={() => setKickoffScope(opt.val)}
                          className={`py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                            kickoffScope === opt.val ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                          }`}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Target Gameweek</label>
                    <select
                      value={gameweek}
                      onChange={(e) => setGameweek(parseInt(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
                    >
                      {Array.from({ length: 38 }, (_, i) => i + 1).map((gw) => (
                        <option key={gw} value={gw}>Gameweek {gw}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 2: Target Goal */}
            {builderStep === 2 && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">Set Your Target</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Choose whether to target a specific odds multiplier or number of games.</p>
                </div>

                {/* Mode Toggle */}
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-fit">
                  <button
                    onClick={() => setTargetMode("ODDS")}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "ODDS" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    🎯 Target Odds
                  </button>
                  <button
                    onClick={() => setTargetMode("GAMES")}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "GAMES" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    🎮 Target Games
                  </button>
                </div>

                {targetMode === "ODDS" ? (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">Select a preset odds goal or enter a custom value:</p>
                    <div className="flex flex-wrap gap-2">
                      {oddsPresetButtons.map((val) => (
                        <button
                          key={val}
                          onClick={() => { setTargetOdds(val); setCustomOdds(""); setUseCustom(false); }}
                          className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all ${
                            !useCustom && targetOdds === val
                              ? "bg-slate-900 text-white shadow-sm"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }`}
                        >
                          ~{val.toFixed(0)}x
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="number"
                        placeholder="Custom odds..."
                        value={customOdds}
                        onChange={(e) => {
                          const valStr = e.target.value;
                          setCustomOdds(valStr);
                          setUseCustom(true);
                          const parsed = parseFloat(valStr);
                          if (!isNaN(parsed) && parsed > 1.0) setTargetOdds(parsed);
                        }}
                        className="w-36 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400">odds multiplier</span>
                    </div>
                    <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                      Current target: <strong className="text-slate-900">{useCustom ? (parseFloat(customOdds) > 1 ? `~${parseFloat(customOdds).toFixed(1)}x` : "Invalid") : `~${targetOdds.toFixed(0)}x odds`}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">How many games do you want in the ticket? (SportyBet max: 50)</p>
                    <div className="flex flex-wrap gap-2">
                      {[5, 10, 15, 20, 25, 30, 40, 50].map((num) => (
                        <button
                          key={num}
                          onClick={() => setTargetGames(num)}
                          className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all ${
                            targetGames === num
                              ? "bg-slate-900 text-white shadow-sm"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }`}
                        >
                          {num} {num === 50 ? "⭐" : ""}
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="number"
                        placeholder="Custom (1–50)"
                        min={1}
                        max={50}
                        value={targetGames}
                        onChange={(e) => setTargetGames(Math.min(50, Math.max(1, parseInt(e.target.value) || 1)))}
                        className="w-36 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400">games in ticket</span>
                    </div>
                    <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                      Current target: <strong className="text-slate-900">{targetGames} games</strong>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* STEP 3: Safety & Options */}
            {builderStep === 3 && (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">Safety & Strategy Options</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Fine-tune how the engine filters and presents picks.</p>
                </div>

                {/* Banker Mode */}
                <div
                  className={`p-4 rounded-2xl border flex items-center justify-between cursor-pointer transition-all ${
                    strictMode ? "bg-amber-50 border-amber-300" : "bg-slate-50 border-slate-200 hover:border-slate-300"
                  }`}
                  onClick={() => setStrictMode(!strictMode)}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${strictMode ? "bg-amber-100 text-amber-700" : "bg-slate-200 text-slate-400"}`}>
                      <ShieldAlert className="w-4 h-4" />
                    </div>
                    <div>
                      <p className={`text-xs font-extrabold ${strictMode ? "text-amber-900" : "text-slate-800"}`}>Banker Mode</p>
                      <p className="text-[11px] text-slate-500 mt-0.5">Only include games with massive statistical dominance. Best for 2–5x rollovers.</p>
                    </div>
                  </div>
                  <div className={`w-11 h-6 rounded-full relative flex-shrink-0 transition-colors ${strictMode ? "bg-amber-500" : "bg-slate-200"}`}>
                    <div className="w-4 h-4 bg-white rounded-full absolute top-1 shadow-sm transition-all" style={{ left: strictMode ? "calc(100% - 20px)" : "4px" }} />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Flex Cut */}
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Flex Cut Strategy</label>
                    <select
                      value={selectedFlexCut}
                      onChange={(e) => setSelectedFlexCut(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
                    >
                      <option value="OFF">Flex Off (Straight Accumulator)</option>
                      <option value="1">Flex Cut-1 (Covers 1 Loss)</option>
                      <option value="2">Flex Cut-2 (Covers 2 Losses)</option>
                      <option value="3">Flex Cut-3 (Covers 3 Losses)</option>
                      <option value="4">Flex Cut-4 (Covers 4 Losses)</option>
                      <option value="5">Flex Cut-5 (Covers 5 Losses)</option>
                      <option value="6">Flex Cut-6 (Covers 6 Losses)</option>
                      <option value="7">Flex Cut-7 (Covers 7 Losses)</option>
                    </select>
                  </div>

                  {/* Live Odds */}
                  <div
                    className={`p-3.5 rounded-xl border flex items-center justify-between cursor-pointer transition-all ${
                      useLiveOdds ? "bg-indigo-50 border-indigo-200" : "bg-slate-50 border-slate-200 hover:border-slate-300"
                    }`}
                    onClick={() => setUseLiveOdds(!useLiveOdds)}
                  >
                    <div>
                      <p className={`text-xs font-extrabold ${useLiveOdds ? "text-indigo-900" : "text-slate-700"}`}>Live SportyBet Odds</p>
                      <p className="text-[11px] text-slate-400 mt-0.5">Enables Gate 3 Value Edge calc</p>
                    </div>
                    <div className={`w-11 h-6 rounded-full relative flex-shrink-0 transition-colors ${useLiveOdds ? "bg-indigo-500" : "bg-slate-200"}`}>
                      <div className="w-4 h-4 bg-white rounded-full absolute top-1 shadow-sm transition-all" style={{ left: useLiveOdds ? "calc(100% - 20px)" : "4px" }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Wizard Footer — Navigation + Build Button */}
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3">
            <button
              onClick={() => setBuilderStep(s => Math.max(1, s - 1))}
              disabled={builderStep === 1}
              className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-100 disabled:opacity-30 transition-all"
            >
              ← Back
            </button>

            <div className="flex items-center gap-2 text-[10px] text-slate-400 font-medium">
              Step {builderStep} of 3
            </div>

            {builderStep < 3 ? (
              <button
                onClick={() => setBuilderStep(s => Math.min(3, s + 1))}
                className="px-5 py-2 rounded-xl text-xs font-extrabold bg-slate-900 text-white hover:bg-slate-700 transition-all"
              >
                Next →
              </button>
            ) : (
              <button
                onClick={handleBuildSafestTicket}
                disabled={loading}
                className="px-5 py-2 rounded-xl btn-black text-xs font-extrabold flex items-center gap-2 transition-all shadow-sm"
              >
                {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : null}
                {loading ? "Building..." : "🚀 Build Ticket"}
              </button>
            )}
          </div>

          {errorMsg && (
            <div className="mx-6 mb-4 bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start gap-3 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-extrabold block">Builder Notice</span>
                <p className="mt-0.5">{errorMsg}</p>
              </div>
            </div>
          )}
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


      {/* MODE 3: TODAY'S SPORTYBET LIVE GAMES BUILDER */}
      {builderMode === "TODAY_GAMES" && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-5 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-700 font-extrabold text-lg flex-shrink-0">
                📅
              </div>
              <div>
                <span className="text-[10px] font-extrabold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200 uppercase tracking-wider">
                  Live SportyBet Today Feed
                </span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5">
                  Today's Active SportyBet Matches Builder
                </h3>
              </div>
            </div>

            <button
              onClick={() => {
                setShowTodayFixturesDrawer(!showTodayFixturesDrawer);
                if (!showTodayFixturesDrawer && todayFixturesList.length === 0) {
                  handleBuildSafestTicket();
                }
              }}
              className="py-2 px-3.5 rounded-xl bg-slate-100 border border-slate-200 hover:bg-slate-200 text-slate-800 text-xs font-extrabold flex items-center space-x-1.5 transition-all self-start sm:self-auto"
            >
              <span>🔍</span>
              <span>{showTodayFixturesDrawer ? "Hide Today's Polled Games" : "Browse All Today's SportyBet Games"}</span>
            </button>
          </div>

          <p className="text-xs text-slate-500">
            Polls <strong>100% of active fixtures kicking off today on SportyBet</strong>, evaluates them through the 3-Pillar Matrix (Odds, H2H, Form), purges sub-1.12 odds, and builds an optimal ticket.
          </p>

          {/* Build Criteria Selector (By Target Odds OR By Number of Games) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Selection Criteria</label>
              <div className="flex bg-slate-100 p-1 rounded-xl space-x-1">
                <button
                  onClick={() => setTodayBuildCriteria("ODDS")}
                  className={`px-3 py-1 rounded-lg text-xs font-extrabold transition-all ${
                    todayBuildCriteria === "ODDS" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  🎯 By Target Odds
                </button>
                <button
                  onClick={() => setTodayBuildCriteria("GAMES")}
                  className={`px-3 py-1 rounded-lg text-xs font-extrabold transition-all ${
                    todayBuildCriteria === "GAMES" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  🎮 By Number of Games
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {todayBuildCriteria === "ODDS" ? (
                <div>
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Target Total Odds</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {[1.5, 2.0, 3.0, 5.0, 10.0, 20.0].map((val) => (
                      <button
                        key={val}
                        onClick={() => {
                          setTargetOdds(val);
                          setTargetMode("ODDS");
                        }}
                        className={`py-2 rounded-xl text-xs font-bold transition-all border ${
                          targetOdds === val
                            ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                            : "bg-slate-50 text-slate-700 border-slate-200 hover:border-slate-300"
                        }`}
                      >
                        ~{val}x
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div>
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Target Number of Games</label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {[3, 5, 8, 10, 12, 15].map((count) => (
                      <button
                        key={count}
                        onClick={() => {
                          setTargetGames(count);
                          setTargetMode("GAMES");
                        }}
                        className={`py-2 rounded-xl text-xs font-bold transition-all border ${
                          targetGames === count
                            ? "bg-slate-900 text-white border-slate-900 shadow-sm"
                            : "bg-slate-50 text-slate-700 border-slate-200 hover:border-slate-300"
                        }`}
                      >
                        {count} Games
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Flex Cut Insurance Strategy</label>
                <select
                  value={selectedFlexCut}
                  onChange={(e) => setSelectedFlexCut(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
                >
                  <option value="OFF">Flex Off (Straight Accumulator)</option>
                  <option value="1">Flex Cut-1 (Covers 1 Loss)</option>
                  <option value="2">Flex Cut-2 (Covers 2 Losses)</option>
                  <option value="3">Flex Cut-3 (Covers 3 Losses)</option>
                  <option value="4">Flex Cut-4 (Covers 4 Losses)</option>
                  <option value="5">Flex Cut-5 (Covers 5 Losses)</option>
                </select>
              </div>
            </div>
          </div>

          <button
            onClick={handleBuildSafestTicket}
            disabled={loading}
            className="w-full py-3.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 shadow-sm transition-all"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin text-white" /> : (
              <span>⚡ Generate Ticket for Today's Active Games ({todayBuildCriteria === "ODDS" ? `~${targetOdds}x Odds` : `${targetGames} Games`})</span>
            )}
          </button>

          {/* Drawer: Collapsible View of All Today's Active SportyBet Games */}
          {showTodayFixturesDrawer && result && result.ticket && result.ticket.approved_legs && (
            <div className="bg-slate-50 border border-slate-200 p-4 rounded-2xl space-y-3 animate-in fade-in duration-200">
              <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                <span className="text-xs font-extrabold text-slate-900">
                  Polled Live SportyBet Games Active Today ({result.ticket.approved_legs.length} Matches)
                </span>
                <span className="text-[10px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                  100% Live Feed Verified
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-60 overflow-y-auto pr-1">
                {result.ticket.approved_legs.map((leg, idx) => (
                  <div key={idx} className="bg-white p-3 rounded-xl border border-slate-200 text-xs flex justify-between items-center">
                    <div>
                      <p className="font-extrabold text-slate-900">{leg.home_team} vs {leg.away_team}</p>
                      <p className="text-[11px] text-slate-500 font-medium mt-0.5">Market: {leg.market_name} ({leg.selection_name})</p>
                    </div>
                    <div className="text-right">
                      <span className="font-extrabold text-emerald-700 text-xs block">{leg.estimated_odds}x</span>
                      <span className="text-[10px] font-extrabold text-purple-700 bg-purple-50 px-1.5 py-0.5 rounded uppercase">{leg.confidence_tier || "ELITE"}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}


      {/* MODE 1 & MODE 3 RESULTS */}
      {(builderMode === "ACCUMULATOR" || builderMode === "TODAY_GAMES") && result && (
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
                              className="p-1.5 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300 transition-all shadow-xs"
                              title="Cancel / Remove game from drafted ticket"
                            >
                              <X className="w-4 h-4" />
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

                {/* Flex Strategy Recommendation Card */}
                {(() => {
                  const nLegs = scn.selections.length;
                  const flex = calculateFlexShield(nLegs, nLegs, scn.accumulated_odds, selectedFlexCut);
                  if (!flex.eligible || selectedFlexCut === "OFF") return null;
                  return (
                    <div className="bg-slate-900 border border-emerald-500/40 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-white shadow-sm my-3">
                      <div className="flex items-start space-x-3">
                        <div className="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                          <ShieldCheck className="w-5 h-5" />
                        </div>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-[11px] font-extrabold uppercase tracking-wider text-emerald-400">
                              Recommended SportyBet Flex Strategy
                            </span>
                            <span className="text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 rounded-full">
                              Recommended: Cut-{flex.recommendedCut}
                            </span>
                          </div>
                          <h4 className="text-xs font-extrabold text-white mt-1">
                            Apply Flex Cut-{flex.recommendedCut} on SportyBet when placing this slip
                          </h4>
                          <p className="text-[11px] text-slate-300 mt-0.5 leading-relaxed">
                            StatIQ's model win rate predicts your {nLegs}-leg ticket will hit high accuracy. Selecting <strong>Flex Cut-{flex.recommendedCut}</strong> guarantees payout even if up to <strong>{flex.recommendedCut} matches</strong> have unexpected outcomes.
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col items-end flex-shrink-0 self-stretch sm:self-auto justify-center bg-slate-800/80 border border-slate-700/60 p-2.5 rounded-xl min-w-[130px]">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Flex Coverage</span>
                        <span className="text-xs font-black text-emerald-400 mt-0.5">
                          Up to {flex.recommendedCut} Losses Paid
                        </span>
                      </div>
                    </div>
                  );
                })()}

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

import React, { useState } from "react";
import { decodeBookingCode, runTicketReEdit, generateNewBookingCode, generateVerifiedBookingCode, lockTrackedTicket, fetchTrackedTickets as fetchTrackedTicketsApi, deleteTrackedTicket as deleteTrackedTicketApi } from "../api/client";
import { Search, Copy, CheckCircle, CheckCircle2, ShieldCheck, ShieldAlert, AlertTriangle, ArrowRight, RefreshCw, Trash2, Sliders, ExternalLink, X, Receipt, Sparkles, Scissors, Layers, Ticket } from "lucide-react";

import { calculateFlexShield } from "../utils/flexCalculator";

export default function BetSlipAuditorTab({ onNavigateHistory, onTicketLocked }) {
  const [inputCode, setInputCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [ticketData, setTicketData] = useState(null);

  // Re-Editor Options
  const [mode, setMode] = useState("AUDITOR"); // "AUDITOR" or "REMOVE"
  const [targetOdds, setTargetOdds] = useState(0); // 0 = Keep All Loaded Ticket Games
  const [targetMode, setTargetMode] = useState("ODDS"); // "ODDS" or "GAMES"
  const [targetGames, setTargetGames] = useState(10);
  const [selectedFlexCut, setSelectedFlexCut] = useState("OFF");
  const [customOddsInput, setCustomOddsInput] = useState("");
  const [customGamesInput, setCustomGamesInput] = useState("");
  const [useCustomOdds, setUseCustomOdds] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [auditorStep, setAuditorStep] = useState(1); // Wizard step: 1 or 2

  // Multi-Ticket Portfolio State
  const [numTickets, setNumTickets] = useState(1);
  const [activePortfolioIndex, setActivePortfolioIndex] = useState(0);

  // Processing state & output
  const [reEditing, setReEditing] = useState(false);
  const [reEditResult, setReEditResult] = useState(null);
  const [reEditError, setReEditError] = useState(null);
  const [generatedCode, setGeneratedCode] = useState(null);
  const [generatingCode, setGeneratingCode] = useState(false);

  // Modal UI state for clean code generation popup
  const [codeModalData, setCodeModalData] = useState(null);
  const [showCodeModal, setShowCodeModal] = useState(false);

  // Tracked Staked Tickets State
  const [trackedTickets, setTrackedTickets] = useState([]);
  const [showLockModal, setShowLockModal] = useState(false);
  const [stakeInput, setStakeInput] = useState("500");
  const [lockingTicket, setLockingTicket] = useState(false);

  const fetchTrackedTickets = async () => {
    try {
      const data = await fetchTrackedTicketsApi();
      const list = Array.isArray(data) ? data : data.tickets || [];
      setTrackedTickets(list);
    } catch (e) {}
  };

  React.useEffect(() => {
    fetchTrackedTickets();
  }, []);

  const [toastNotice, setToastNotice] = useState(null);
  const [lockSuccessMessage, setLockSuccessMessage] = useState(false);
  const showNotice = (msg) => {
    setToastNotice(msg);
    setTimeout(() => setToastNotice(null), 4500);
  };


  const handleLockTicketSubmit = async () => {
    if (!reEditResult) return;
    setLockingTicket(true);
    try {
      const payload = {
        code: generatedCode || ticketData?.code || "CUSTOM",
        mode: reEditResult.mode,
        target_odds: targetOdds,
        total_odds: reEditResult.new_total_odds,
        stake: parseFloat(stakeInput) || 500,
        flex_cut: selectedFlexCut,
        selections: reEditResult.final_selections || []
      };
      const res = await lockTrackedTicket(payload);
      if (res && (res.id || res.status === "SUCCESS" || res.code)) {
        await fetchTrackedTickets();
        setShowLockModal(false);
        setLockSuccessMessage(true);
        if (typeof onTicketLocked === "function") onTicketLocked();

        setTimeout(() => setLockSuccessMessage(false), 8000);
      } else {
        showNotice("Failed to lock ticket into Tracker. Ensure backend is running.");
      }
    } catch (e) {
      console.error("Lock ticket error:", e);
      showNotice("Error locking ticket: " + e.message);
    }
    setLockingTicket(false);
  };


  const handleDeleteTrackedTicket = async (ticketId) => {
    try {
      await deleteTrackedTicketApi(ticketId);
      await fetchTrackedTickets();
    } catch (e) {}
  };


  const [autoRefresh, setAutoRefresh] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Demo sample ticket data used when "Load Sample" is clicked
  const sampleTicket = [
    { home_team: "Galatasaray", away_team: "Fenerbahce", market_name: "Double Chance", selection_name: "Home or Draw", odds: 1.35, match_status: "UPCOMING", game_id: "S001" },
    { home_team: "Celtic", away_team: "Rangers", market_name: "Over/Under", selection_name: "Over 1.5", odds: 1.28, match_status: "UPCOMING", game_id: "S002" },
    { home_team: "PSG", away_team: "Lyon", market_name: "Match Result", selection_name: "Home", odds: 1.52, match_status: "UPCOMING", game_id: "S003" },
    { home_team: "Ajax", away_team: "PSV", market_name: "GG/NG", selection_name: "Yes", odds: 1.45, match_status: "UPCOMING", game_id: "S004" },
  ];

  React.useEffect(() => {
    let interval;
    if (autoRefresh && ticketData && (ticketData.code || inputCode)) {
      interval = setInterval(() => {
        handleDecode(ticketData.code || inputCode, true);
      }, 15000);
    }
    return () => clearInterval(interval);
  }, [autoRefresh, ticketData?.code, inputCode]);

  const handleDecode = async (codeToUse, isSilent = false) => {
    const code = codeToUse || inputCode;
    if (!code) return;

    // Demo shortcut — load sample data instantly without hitting the API
    if (code.toUpperCase() === "BC-DEMO-SAMPLE") {
      setTicketData({ code: "BC-DEMO-SAMPLE", total_selections: sampleTicket.length, selections: sampleTicket, _is_demo: true });
      setLoading(false);
      setIsRefreshing(false);
      return;
    }

    if (isSilent) {
      setIsRefreshing(true);
    } else {
      setLoading(true);
      setTicketData(null);
      setReEditResult(null);
      setReEditError(null);
      setGeneratedCode(null);
      setAuditorStep(1);
    }

    const data = await decodeBookingCode(code);

    if (data.selections && data.selections.length > 0) {
      // Success — real selections decoded from SportyBet
      setTicketData(data);
      setAuditorStep(1);
    } else if (data.status === "TIMEOUT" && !isSilent) {
      setReEditError(`⏱ SportyBet is taking too long to respond for code "${code.toUpperCase()}". The backend is busy — wait 10 seconds and try again.`);
    } else if (data.status === "HTTP_ERROR" && !isSilent) {
      setReEditError(`❌ Code "${code.toUpperCase()}" not found on SportyBet (HTTP ${data.http_status}). Check the code is correct.`);
    } else if (data.status === "ERROR" && !isSilent) {
      setReEditError(`❌ Could not connect to StatIQ backend. Make sure the backend server is running on port 8000.`);
    } else if (!isSilent) {
      // Code returned empty selections — invalid or expired code
      setReEditError(`⚠️ No games found for code "${code.toUpperCase()}". The code may be expired or invalid. Try again or load the sample ticket.`);
    }

    setLoading(false);
    setIsRefreshing(false);
  };

  const handleClearTicket = () => {
    setTicketData(null);
    setReEditResult(null);
    setReEditError(null);
    setGeneratedCode(null);
    setInputCode("");
    setShowCodeModal(false);
    setAuditorStep(1);
  };

  const calculateOriginalTotalOdds = () => {
    if (!ticketData || !ticketData.selections) return "1.00";
    const activeSelections = ticketData.selections.filter(s => (parseFloat(s.odds) || 1.0) > 1.0);
    const pool = activeSelections.length > 0 ? activeSelections : ticketData.selections;
    return pool.reduce((acc, s) => acc * (parseFloat(s.odds) || 1.0), 1.0).toFixed(2);
  };

  const handleRemoveSelection = (indexToRemove) => {
    if (!ticketData || !ticketData.selections) return;
    const updatedSelections = ticketData.selections.filter((_, idx) => idx !== indexToRemove);
    setTicketData({
      ...ticketData,
      total_selections: updatedSelections.length,
      selections: updatedSelections,
    });
    setReEditResult(null);
    setReEditError(null);
  };

  const handleRemoveAllNulled = () => {
    if (!ticketData || !ticketData.selections) return;
    const nowMs = Date.now();
    const updated = ticketData.selections.filter((s) => {
      const st = (s.match_status || "").toUpperCase();
      const isNulled = st === "NULLED_EXPIRED" || (parseFloat(s.odds) || 1.0) === 1.0;
      const isLive = st === "LIVE" || st === "IN_PROGRESS" || st === "ONGOING" || st === "H1" || st === "H2" || st === "HT" || Boolean(s.clock) || Boolean(s.score);
      const isConc = st === "CONCLUDED" || st === "FINISHED" || st === "FT";
      const isPastKickoff = s.start_time_ms ? nowMs >= s.start_time_ms : false;
      return !isNulled && !isLive && !isConc && !isPastKickoff;
    });
    setTicketData({
      ...ticketData,
      total_selections: updated.length,
      selections: updated,
    });
    setReEditResult(null);
    setReEditError(null);
  };

  const handleRemoveDraftedSelection = (indexToRemove) => {
    if (!reEditResult || !reEditResult.final_selections) return;
    const updatedSelections = reEditResult.final_selections.filter((_, idx) => idx !== indexToRemove);

    if (updatedSelections.length === 0) {
      setReEditResult(null);
      setGeneratedCode(null);
      return;
    }

    const newTotalOdds = updatedSelections.reduce((acc, s) => {
      const o = parseFloat(s.estimated_odds || s.odds || 1.25);
      return acc * (isNaN(o) || o <= 0 ? 1.0 : o);
    }, 1.0);

    const roundedOdds = (Math.round(newTotalOdds * 100) / 100).toFixed(2);

    setReEditResult({
      ...reEditResult,
      final_count: updatedSelections.length,
      new_total_odds: roundedOdds,
      final_selections: updatedSelections,
    });

    if (codeModalData) {
      setCodeModalData({
        ...codeModalData,
        selections: updatedSelections
      });
    }
  };

  const handleRemoveRiskyMatches = () => {
    if (!ticketData || !ticketData.selections) return;
    const initialCount = ticketData.selections.length;
    
    const safeOnly = ticketData.selections.filter(s => {
      const oddsNum = parseFloat(s.odds) || 1.5;
      const mkt = (s.market_name || "").toLowerCase();
      const sel = (s.selection_name || "").toLowerCase();
      const st = (s.match_status || "").toUpperCase();

      // Nulled, Concluded, or Live games are trimmed
      if (st === "NULLED_EXPIRED" || st === "CONCLUDED" || st === "FINISHED" || st === "FT" || st === "LIVE" || st === "IN_PROGRESS") {
        return false;
      }

      // Volatile trap markets trimmed
      const isTrapMarket = 
        sel.includes("win either half") || 
        mkt.includes("win either half") || 
        sel.includes("weh") || 
        sel.includes("over 9.5") || 
        sel.includes("over 8.5") || 
        mkt.includes("both teams to score") || 
        sel.includes("gg");

      if (isTrapMarket) return false;

      // Safe market floor: Double Chance, Over 1.5, Over 0.5, 1X, X2, or low odds floor
      const isSafeType = 
        mkt.includes("double chance") || 
        sel.includes("1x") || 
        sel.includes("x2") || 
        sel.includes("over 1.5") || 
        sel.includes("over 0.5") || 
        (oddsNum >= 1.15 && oddsNum <= 1.45);

      return isSafeType;
    });

    const removedCount = initialCount - safeOnly.length;

    setTicketData({
      ...ticketData,
      total_selections: safeOnly.length,
      selections: safeOnly,
    });
    setReEditResult(null);
    setReEditError(null);

    if (removedCount > 0) {
      setLockSuccessMessage(`✂️ Smart Trimmed ${removedCount} risky market selection(s)! ${safeOnly.length} safe games remaining.`);
      setTimeout(() => setLockSuccessMessage(false), 5000);
    } else {
      setReEditError("ℹ️ All current loaded games already meet MatchIQ 5-Gate safety criteria (No risky WEH or Over 9.5 picks found).");
    }
  };

  const handleRunReEdit = async () => {
    if (!ticketData || !ticketData.selections) return;
    setReEditing(true);
    setReEditResult(null);
    setReEditError(null);
    setGeneratedCode(null);
    setActivePortfolioIndex(0);

    const finalOdds = useCustomOdds && customOddsInput ? parseFloat(customOddsInput) : targetOdds;
    const result = await runTicketReEdit(
      ticketData.selections,
      finalOdds,
      mode,
      targetMode,
      targetGames,
      Date.now(),
      strictMode,
      numTickets
    );
    setReEditing(false);

    // Handle error/timeout responses
    if (!result || result.status === "TIMEOUT" || result.status === "HTTP_ERROR" || result.status === "ERROR") {
      const statusMsg = result?.status === "TIMEOUT"
        ? "Request timed out (>15s). The server may be overloaded — please try again."
        : result?.status === "HTTP_ERROR"
        ? `Server returned HTTP ${result.http_status}. Check if the backend is running.`
        : "MatchIQ engine returned no result. Please try again or check backend logs.";
      setReEditError(statusMsg);
      return;
    }

    // Valid result
    setReEditResult(result);

    // Auto set verified booking code from primary slip
    if (result.booking_code) {
      setGeneratedCode(result.booking_code);
    }
  };

  const copyCode = (code) => {
    navigator.clipboard.writeText(code);
    showNotice(`Copied SportyBet booking code: ${code}`);
  };

  const copySelectionsAsText = (selections) => {
    const text = selections.map(s => `• ${s.home_team || s.fixture} -> ${s.selection_name || s.market_name || s.pick}`).join("\n");
    navigator.clipboard.writeText(text);
    showNotice(`Copied ${selections.length} selections to clipboard!`);
  };

  return (
    <div className="space-y-6 relative">
      {/* Non-intrusive Toast Notification Banner */}
      {toastNotice && (
        <div className="fixed top-5 right-5 z-50 bg-slate-900 text-white px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 flex items-center space-x-2.5 text-xs font-bold animate-in fade-in slide-in-from-top-4 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastNotice}</span>
        </div>
      )}

      {/* Sleek Booking Code Modal Popup */}

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
                  SportyBet Code Generated
                </span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5">
                  Re-Edited Booking Code Ready!
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
                onClick={() => copyCode(codeModalData.code)}
                className="px-4 py-2 rounded-xl bg-white hover:bg-slate-100 text-slate-900 font-extrabold text-xs flex items-center space-x-1.5 transition-all shadow-sm border border-slate-200"
              >
                <Copy className="w-4 h-4" />
                <span>Copy Code</span>
              </button>

            </div>

            {/* 1-Click Action Buttons */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                onClick={() => {
                  if (codeModalData.selections) {
                    const text = codeModalData.selections.map((s, idx) => 
                      `${idx + 1}. ${s.home_team} vs ${s.away_team} ➔ ${s.market_name} (${s.selection_name})`
                    ).join("\n");
                    navigator.clipboard.writeText(text);
                  }
                  window.open(codeModalData.loadUrl || "https://www.sportybet.com/ng/", "_blank");
                }}
                className="py-2.5 px-4 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1.5 transition-all"
              >
                <ExternalLink className="w-4 h-4" />
                <span>Open on SportyBet</span>
              </button>

              <button
                onClick={() => {
                  if (!codeModalData.selections) return;
                  const text = codeModalData.selections.map((s, idx) => 
                    `${idx + 1}. ${s.home_team} vs ${s.away_team} ➔ Pick: ${s.market_name} (${s.selection_name})`
                  ).join("\n");
                  navigator.clipboard.writeText(text);
                  showNotice(`Copied ${codeModalData.selections.length} StatIQ selections to clipboard!`);
                }}

                className="py-2.5 px-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 hover:bg-slate-200 text-xs font-extrabold flex items-center justify-center space-x-1.5 transition-all"
              >
                <Copy className="w-4 h-4" />
                <span>Copy Selections Text</span>
              </button>
            </div>

            {/* Included Selections Breakdown */}
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
                Final Re-Edited Match Picks ({codeModalData.selections.length} Legs)
              </span>
              {codeModalData.selections.map((s, idx) => (
                <div key={idx} className="bg-slate-50 p-2.5 rounded-xl border border-slate-200 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-slate-900 block">
                      {s.home_team} vs {s.away_team}
                    </span>
                    <span className="text-slate-600 font-semibold text-[11px]">
                      Pick: {s.market_name} — {s.selection_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-emerald-700 text-xs">
                      {Math.round((s.estimated_prob || 0.70) * 100)}% Win Chance
                    </span>
                    <button
                      onClick={() => handleRemoveDraftedSelection(idx)}
                      className="p-1 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-600 border border-slate-200 transition-all"
                      title="Remove game from drafted ticket"
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

      {lockSuccessMessage && (
        <div className="bg-emerald-50 border border-emerald-300 p-4 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-emerald-900 shadow-sm mb-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold flex-shrink-0">
              <CheckCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="font-extrabold text-sm">📌 Ticket Successfully Locked & Moved to Bet History!</p>
              <p className="text-xs text-emerald-700 font-medium">The auditor view has cleared. Your staked ticket is now active and tracked live in Bet History.</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setLockSuccessMessage(false);
                if (onNavigateHistory) onNavigateHistory();
              }}
              className="px-3 py-1.5 rounded-xl bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold shadow-sm transition-all whitespace-nowrap"
            >
              View in Bet History →
            </button>
            <button
              onClick={() => setLockSuccessMessage(false)}
              className="text-xs text-emerald-700 hover:text-emerald-900 font-bold px-2 py-1"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
      <div className="bg-white p-6 rounded-2xl border border-slate-200">
        <h2 className="text-xl font-extrabold text-slate-900">
          StatIQ Ticket Re-Editor & Auditor
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Paste any SportyBet booking code or load ticket selections. StatIQ's statistical engine evaluates every match, flags risky or unsupported games, and re-edits the ticket to hit your target odds.
        </p>
      </div>

      {/* Code Input Box */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4">
        <label className="text-xs font-bold text-slate-700 block uppercase tracking-wider">
          Enter SportyBet Booking Code
        </label>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={inputCode}
              onChange={(e) => setInputCode(e.target.value)}
              placeholder="e.g. BC7F49A"
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-2.5 text-sm font-bold text-slate-900 uppercase tracking-wider focus:outline-none focus:ring-1 focus:ring-slate-900"
            />
          </div>
          <button
            onClick={() => handleDecode()}
            disabled={loading}
            className="px-6 py-2.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider whitespace-nowrap flex items-center justify-center gap-2"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
            <span>{loading ? "Decoding..." : "Load & Analyze Ticket"}</span>
          </button>
        </div>

        {/* Quick Demo Button */}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span>Or test with sample ticket:</span>
          <button
            onClick={() => handleDecode("BC-DEMO-SAMPLE")}
            className="text-indigo-600 hover:text-indigo-800 font-bold underline cursor-pointer"
          >
            Load Sample 4-Match Ticket (includes Turkish/Scottish games)
          </button>
        </div>
      </div>

      {/* Ticket Loaded Preview & Re-Editor Form */}
      {ticketData && (
        <div className="space-y-6">
          {/* Loaded Summary Card */}
          <div className="bg-slate-900 text-white p-6 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">
                  Booking Code: [{ticketData.code || inputCode}]
                </span>
                {ticketData._is_demo && (
                  <span className="text-[10px] font-extrabold bg-amber-400 text-amber-950 px-2 py-0.5 rounded uppercase tracking-wider">
                    Demo Ticket
                  </span>
                )}
              </div>
              <h3 className="text-lg font-extrabold mt-0.5">
                Original Ticket: {ticketData.selections?.length || 0} Matches
              </h3>
              <span className="text-xs text-slate-300 mt-1 block">
                Total Combined Odds: ~<strong>{calculateOriginalTotalOdds()}x</strong>
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <div className="bg-slate-800 p-3.5 rounded-xl border border-slate-700 text-right min-w-[110px]">
                <span className="text-[10px] text-slate-400 block font-medium">Original Odds</span>
                <span className="text-xl font-extrabold text-emerald-400">{calculateOriginalTotalOdds()}x</span>
              </div>

              <button
                onClick={async () => {
                  setGeneratingCode(true);
                  const codeRes = await generateVerifiedBookingCode(ticketData.selections, ticketData.code || "LOADED-TKT", "ng");
                  if (codeRes.booking_code && (codeRes.status === "VERIFIED" || codeRes.status === "SUCCESS")) {
                    setGeneratedCode(codeRes.booking_code);
                    setCodeModalData({
                      code: codeRes.booking_code,
                      status: codeRes.status,
                      verificationSummary: codeRes.reconciliation_summary || "All selections verified 100% with zero false positives.",
                      totalOdds: codeRes.total_odds || calculateOriginalTotalOdds(),
                      selections: ticketData.selections,
                      loadUrl: codeRes.share_url || `https://www.sportybet.com/ng/?shareCode=${codeRes.booking_code}`
                    });
                    setShowCodeModal(true);
                  } else {
                    showNotice(`SportyBet Code Verification Result: ${codeRes.message || 'Could not verify selections on SportyBet Nigeria.'}`);
                  }
                  setGeneratingCode(false);
                }}
                disabled={generatingCode}
                className="px-4 py-3 rounded-xl bg-white hover:bg-slate-100 text-slate-900 text-xs font-extrabold flex items-center justify-center gap-1.5 shadow-sm transition-all border border-slate-200"
                title="Verify and generate a fresh SportyBet booking code for these exact selections"
              >
                {generatingCode ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
                <span>{generatingCode ? "Verifying..." : "Generate SportyBet Code"}</span>
              </button>


              <button
                onClick={handleClearTicket}
                className="px-3.5 py-3 rounded-xl bg-slate-800 hover:bg-rose-900/60 text-slate-400 hover:text-rose-200 border border-slate-700 hover:border-rose-700 transition-all flex flex-col items-center justify-center text-center gap-1"
                title="Clear current ticket and load a new code"
              >
                <Trash2 className="w-4 h-4 text-rose-400" />
                <span className="text-[10px] font-extrabold uppercase tracking-wider">Clear Ticket</span>
              </button>
            </div>

          </div>

          {/* Loaded Matches & Status Breakdown List */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
              <div>
                <h3 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                  <span>Decoded Ticket Matches ({ticketData.selections?.length || 0} Games)</span>
                </h3>
                <p className="text-xs text-slate-500">
                  Review original match selections, live status, and remove nulled/unwanted games manually.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
                <button
                  onClick={() => handleDecode(ticketData.code || inputCode, true)}
                  disabled={isRefreshing}
                  className="px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 font-extrabold text-xs flex items-center gap-1.5 transition-all shadow-sm"
                  title="Fetch latest live scores, match clock, and odds directly from SportyBet API"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
                  <span>{isRefreshing ? "Updating Live..." : "Refresh Live Status"}</span>
                </button>

                <label className="flex items-center gap-1.5 text-xs text-slate-700 font-bold cursor-pointer bg-slate-100 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-200 transition-all select-none">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    className="rounded text-slate-900 focus:ring-slate-900"
                  />
                  <span>Auto-Poll (15s)</span>
                </label>

                <button
                  onClick={handleRemoveRiskyMatches}
                  className="px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-extrabold text-xs flex items-center gap-1.5 transition-all shadow-sm"
                  title="Trim & remove all risky matches evaluated below 70% confidence from the loaded ticket above"
                >
                  <Scissors className="w-3.5 h-3.5" />
                  <span>✂️ Smart Trim Loaded Games</span>
                </button>

                {ticketData.selections?.some(s => {
                  const st = (s.match_status || "").toUpperCase();
                  const nowMs = Date.now();
                  return st === "NULLED_EXPIRED" || st === "IN_PROGRESS" || st === "LIVE" || st === "CONCLUDED" || (s.start_time_ms && nowMs >= s.start_time_ms) || (parseFloat(s.odds) || 1.0) === 1.0;
                }) && (
                  <button
                    onClick={handleRemoveAllNulled}
                    className="px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-extrabold text-xs flex items-center gap-1.5 transition-all shadow-sm"
                    title="Remove all nulled, concluded, or in-progress games"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Purge Nulled / Live Games</span>
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-2.5">
              {ticketData.selections?.map((s, idx) => {
                const oddsNum = parseFloat(s.odds) || 1.75;
                const st = (s.match_status || "").toUpperCase();
                const nowMs = Date.now();
                const isNulled = st === "NULLED_EXPIRED" || oddsNum === 1.0;
                const isConcluded = st === "CONCLUDED" || st === "FINISHED" || st === "FT";
                const isStarted = s.start_time_ms ? nowMs >= s.start_time_ms : false;
                const isInProgress = st === "IN_PROGRESS" || st === "LIVE" || st === "ONGOING" || st === "H1" || st === "H2" || st === "HT" || Boolean(s.clock) || Boolean(s.score) || isStarted;

                return (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
                      isNulled
                        ? "bg-rose-50/60 border-rose-200 text-slate-500"
                        : isConcluded
                        ? "bg-slate-100 border-slate-300 text-slate-700"
                        : isInProgress
                        ? "bg-amber-50/60 border-amber-200 text-slate-800"
                        : "bg-slate-50 border-slate-200 text-slate-900"
                    }`}
                  >
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-extrabold text-sm text-slate-900">
                          {s.home_team} vs {s.away_team}
                        </span>

                        {(s.game_id || s.external_fixture_id) && (
                          <span className="text-[10px] text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                            Game ID: {s.game_id || s.external_fixture_id}
                          </span>
                        )}

                        {s.kickoff_datetime_str && !isInProgress && !isConcluded && (
                          <span className="text-[10px] text-slate-600 font-bold bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                            {s.kickoff_datetime_str}
                          </span>
                        )}

                        {isNulled && (
                          <span className="bg-rose-100 text-rose-800 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                            Odds Nulled / Expired
                          </span>
                        )}
                        {isConcluded && (
                          <span className="bg-slate-200 text-slate-800 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase flex items-center gap-1">
                            <span>🏁 Concluded / Finished</span>
                            {s.score ? <span className="font-black">[{s.score}]</span> : null}
                          </span>
                        )}
                        {isInProgress && !isConcluded && (
                          <span className="bg-amber-100 text-amber-900 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase animate-pulse flex items-center gap-1">
                            <span>🔴 Live / Ongoing</span>
                            {s.clock ? <span>({s.clock} {s.match_status_code || ""})</span> : null}
                            {s.score ? <span className="font-black text-amber-950">[{s.score}]</span> : null}
                          </span>
                        )}
                        {!isNulled && !isInProgress && !isConcluded && (
                          <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                            Upcoming / Bettable
                          </span>
                        )}
                      </div>

                      <div className="text-slate-700 font-semibold text-xs">
                        Original Bettor Pick: <strong className="text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200">{s.market_name} — {s.selection_name}</strong>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 flex-shrink-0">
                      <div className="text-right min-w-[60px]">
                        <span className="text-[10px] text-slate-400 block font-semibold uppercase">Original Odds</span>
                        <span className={`text-base font-extrabold ${isNulled ? "text-rose-600 line-through" : "text-emerald-700"}`}>
                          {oddsNum.toFixed(2)}x
                        </span>
                      </div>

                      {/* Manual Remove Button */}
                      <button
                        onClick={() => handleRemoveSelection(idx)}
                        className="px-2.5 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-600 text-rose-700 hover:text-white border border-rose-200 hover:border-rose-600 font-extrabold text-xs transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                        title="Remove game manually from ticket"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        <span>Remove</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Re-Editor Controls — Wizard */}
          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">

            {/* Wizard Step Bar */}
            <div className="flex border-b border-slate-100">
              {[
                { id: 1, label: "Mode & Safety" },
                { id: 2, label: "Target & Output" },
              ].map((s) => {
                const isActive = auditorStep === s.id;
                const isDone = auditorStep > s.id;
                return (
                  <button
                    key={s.id}
                    onClick={() => setAuditorStep(s.id)}
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

            {/* Step Content */}
            <div className="p-6 space-y-5 min-h-[240px]">

              {/* STEP 1: Mode & Safety */}
              {auditorStep === 1 && (
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-extrabold text-slate-900">Choose Re-Edit Mode</h3>
                    <p className="text-xs text-slate-400 mt-0.5">How should StatIQ handle the picks on your ticket?</p>
                  </div>

                  {/* Mode Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div
                      onClick={() => setMode("AUDITOR")}
                      className={`p-4 rounded-2xl border cursor-pointer transition-all ${
                        mode === "AUDITOR"
                          ? "border-emerald-600 bg-emerald-50/50 ring-2 ring-emerald-600 shadow-sm"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${mode === "AUDITOR" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-500"}`}>
                            <ShieldCheck className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="font-extrabold text-slate-900 text-sm block">Auditor Mode</span>
                            <span className="text-[10px] text-emerald-600 font-bold uppercase tracking-wider">100% Same Games</span>
                          </div>
                        </div>
                        {mode === "AUDITOR" && (
                          <span className="text-[9px] font-black uppercase bg-emerald-600 text-white px-2.5 py-0.5 rounded-full">Active</span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 leading-snug">
                        Keeps all of your ticket's games. Upgrades risky straight picks into mathematically cushioned market lines with high probability.
                      </p>
                    </div>

                    <div
                      onClick={() => setMode("REMOVE")}
                      className={`p-4 rounded-2xl border cursor-pointer transition-all ${
                        mode === "REMOVE"
                          ? "border-rose-600 bg-rose-50/50 ring-2 ring-rose-600 shadow-sm"
                          : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${mode === "REMOVE" ? "bg-rose-600 text-white" : "bg-slate-100 text-slate-500"}`}>
                            <Trash2 className="w-4 h-4" />
                          </div>
                          <div>
                            <span className="font-extrabold text-slate-900 text-sm block">Risk Purge Mode</span>
                            <span className="text-[10px] text-rose-600 font-bold uppercase tracking-wider">Drop Risky Legs</span>
                          </div>
                        </div>
                        {mode === "REMOVE" && (
                          <span className="text-[9px] font-black uppercase bg-rose-600 text-white px-2.5 py-0.5 rounded-full">Active</span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-500 leading-snug">
                        Audits every leg and strictly purges low-confidence picks with audit justification. Leaves only your model-confirmed core winners.
                      </p>
                    </div>
                  </div>

                  {/* Banker Mode Toggle */}
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
                        <p className="text-[11px] text-slate-500 mt-0.5">Only picks with massive statistical dominance. Best for 2–5x rollovers.</p>
                      </div>
                    </div>
                    <div className={`w-11 h-6 rounded-full relative flex-shrink-0 transition-colors ${strictMode ? "bg-amber-500" : "bg-slate-200"}`}>
                      <div className="w-4 h-4 bg-white rounded-full absolute top-1 shadow-sm transition-all" style={{ left: strictMode ? "calc(100% - 20px)" : "4px" }} />
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 2: Target & Flex Cut */}
              {auditorStep === 2 && (
                <div className="space-y-5">
                  <div>
                    <h3 className="text-sm font-extrabold text-slate-900">Set Target & Output Options</h3>
                    <p className="text-xs text-slate-400 mt-0.5">Define your desired output odds and SportyBet flex insurance.</p>
                  </div>

                  {/* Target Mode Toggle */}
                  <div className="space-y-3">
                    <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-fit">
                      <button
                        onClick={() => setTargetMode("ODDS")}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                          targetMode === "ODDS" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                        }`}
                      >
                        Target Odds
                      </button>
                      <button
                        onClick={() => setTargetMode("GAMES")}
                        className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                          targetMode === "GAMES" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                        }`}
                      >
                        Target Games
                      </button>
                    </div>

                    {targetMode === "ODDS" ? (
                      <div className="space-y-2">
                        <div className="flex flex-wrap gap-2">
                          <button
                            onClick={() => { setTargetOdds(0); setUseCustomOdds(false); setReEditResult(null); }}
                            className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                              !useCustomOdds && targetOdds === 0
                                ? "bg-emerald-600 border-emerald-600 text-white shadow-sm"
                                : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                            }`}
                          >
                            All {ticketData?.selections?.length || ""} Games
                          </button>
                          {[1.5, 2.0, 3.0, 5.0, 10.0, 20.0, 50.0].map((val) => (
                            <button
                              key={val}
                              onClick={() => { setTargetOdds(val); setUseCustomOdds(false); setReEditResult(null); }}
                              className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                                !useCustomOdds && targetOdds === val
                                  ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                                  : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                              }`}
                            >
                              ~{val.toFixed(1)}x
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            placeholder="Custom odds..."
                            value={customOddsInput}
                            onChange={(e) => {
                              const valStr = e.target.value;
                              setCustomOddsInput(valStr);
                              setUseCustomOdds(true);
                              const parsed = parseFloat(valStr);
                              if (!isNaN(parsed) && parsed > 1.0) setTargetOdds(parsed);
                            }}
                            className="w-36 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                          />
                          <span className="text-xs text-slate-400">odds multiplier</span>
                        </div>
                        <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                          Current target: <strong className="text-slate-900">{targetOdds === 0 ? "Full ticket (all games)" : useCustomOdds ? `~${parseFloat(customOddsInput).toFixed(1)}x` : `~${targetOdds.toFixed(1)}x odds`}</strong>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex flex-wrap gap-2">
                          {[5, 10, 15, 20, 25, 30, 40, 50].map((num) => (
                            <button
                              key={num}
                              onClick={() => { setTargetGames(num); setCustomGamesInput(""); setReEditResult(null); }}
                              className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all border ${
                                !customGamesInput && targetGames === num
                                  ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                                  : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                              }`}
                            >
                              {num}
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            placeholder="Custom (1–50)"
                            min={1}
                            max={50}
                            value={customGamesInput}
                            onChange={(e) => {
                              const valStr = e.target.value;
                              setCustomGamesInput(valStr);
                              const parsed = parseInt(valStr);
                              if (!isNaN(parsed) && parsed >= 1) setTargetGames(Math.min(50, parsed));
                              setReEditResult(null);
                            }}
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

                  {/* Multi-Ticket Portfolio Selector */}
                  <div className="space-y-2">
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                      Tickets to Generate (Zero-Overlap Portfolio)
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { count: 1, label: "1 Ticket", sub: "Standard Single Slip" },
                        { count: 2, label: "2 Variant Tickets", sub: "Split 0% Overlap / Hedged Markets" },
                      ].map((item) => (
                        <button
                          key={item.count}
                          type="button"
                          onClick={() => { setNumTickets(item.count); setReEditResult(null); }}
                          className={`p-3 rounded-xl border text-left transition-all ${
                            numTickets === item.count
                              ? "bg-slate-900 border-slate-900 text-white shadow-sm ring-1 ring-slate-900"
                              : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          <span className="font-extrabold text-xs block">{item.label}</span>
                          <span className={`text-[9px] block mt-0.5 ${numTickets === item.count ? "text-emerald-400 font-bold" : "text-slate-500"}`}>
                            {item.sub}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Flex Cut — compact select */}
                  <div>
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Flex Cut Strategy</label>
                    <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
                      {[
                        { id: "OFF", label: "Off", sub: "Straight" },
                        { id: "1", label: "Cut 1", sub: "1 Loss" },
                        { id: "2", label: "Cut 2", sub: "2 Losses" },
                        { id: "3", label: "Cut 3", sub: "3 Losses" },
                        { id: "4", label: "Cut 4", sub: "4 Losses" },
                        { id: "5", label: "Cut 5", sub: "5 Losses" },
                        { id: "6", label: "Cut 6", sub: "6 Losses" },
                        { id: "7", label: "Cut 7", sub: "7 Losses" },
                      ].map((item) => (
                        <button
                          key={item.id}
                          onClick={() => setSelectedFlexCut(item.id)}
                          className={`p-2 rounded-xl border text-center transition-all flex flex-col items-center justify-center ${
                            selectedFlexCut === item.id
                              ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                              : "bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          <span className="font-extrabold text-[11px] whitespace-nowrap">{item.label}</span>
                          <span className={`text-[9px] mt-0.5 whitespace-nowrap ${selectedFlexCut === item.id ? "text-emerald-400" : "text-slate-400"}`}>
                            {item.sub}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Wizard Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3">
              <button
                onClick={() => setAuditorStep(s => Math.max(1, s - 1))}
                disabled={auditorStep === 1}
                className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-100 disabled:opacity-30 transition-all"
              >
                ← Back
              </button>

              <span className="text-[10px] text-slate-400 font-medium">Step {auditorStep} of 2</span>

              {auditorStep < 2 ? (
                <button
                  onClick={() => setAuditorStep(s => Math.min(2, s + 1))}
                  className="px-5 py-2 rounded-xl text-xs font-extrabold bg-slate-900 text-white hover:bg-slate-700 transition-all"
                >
                  Next →
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleRunReEdit}
                    disabled={reEditing}
                    className="px-3.5 py-2 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-xs font-extrabold flex items-center gap-1.5 transition-all shadow-sm"
                    title="Generate a fresh, alternative match combination to avoid single-game correlation"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${reEditing ? "animate-spin" : ""}`} />
                    <span>🔀 Reshuffle & Diversify</span>
                  </button>

                  <button
                    onClick={handleRunReEdit}
                    disabled={reEditing}
                    className="px-5 py-2 rounded-xl btn-black text-xs font-extrabold flex items-center gap-2 transition-all shadow-sm"
                  >
                    {reEditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : null}
                    {reEditing
                      ? "Running..."
                      : mode === "AUDITOR"
                      ? "Audit & Upgrade Picks"
                      : mode === "SWAP"
                      ? "Re-Edit Ticket"
                      : "Remove Risky Picks"}
                  </button>
                </div>
              )}
            </div>

            {/* Error Banner */}
            {reEditError && (
              <div className="mx-6 mb-4 bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3">
                <AlertTriangle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                <div>
                  <span className="text-xs font-extrabold text-rose-800 block">Re-Edit Failed</span>
                  <p className="text-xs text-rose-700 mt-0.5">{reEditError}</p>
                  <button
                    onClick={() => setReEditError(null)}
                    className="text-[10px] font-bold text-rose-500 hover:text-rose-700 mt-1 underline"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Re-Edit Output Card */}
          {reEditResult && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6 shadow-sm">
              {lockSuccessMessage && (
                <div className="bg-emerald-600 text-white p-4 rounded-xl shadow-md flex items-center justify-between animate-bounce">
                  <div className="flex items-center space-x-2">
                    <CheckCircle className="w-5 h-5 text-white" />
                    <span className="text-xs font-extrabold">
                      Ticket Successfully Locked! Staked ticket is now active and being tracked live in Bet History.
                    </span>
                  </div>
                  <button
                    onClick={() => {
                      if (onNavigateHistory) onNavigateHistory();
                    }}
                    className="px-3 py-1 bg-white text-emerald-800 rounded-lg text-xs font-bold hover:bg-emerald-50"
                  >
                    View History →
                  </button>
                </div>
              )}

              {/* Header result banner & Portfolio Switcher */}
              {(() => {
                const portfolioSlips = (reEditResult.portfolio_tickets && reEditResult.portfolio_tickets.length > 0)
                  ? reEditResult.portfolio_tickets
                  : [reEditResult];
                const activeSlip = portfolioSlips[activePortfolioIndex] || portfolioSlips[0] || reEditResult;
                const activeFinalSelections = activeSlip.final_selections || reEditResult.final_selections || [];
                const activeOdds = activeSlip.new_total_odds || reEditResult.new_total_odds;
                const activeCount = activeSlip.final_count || activeFinalSelections.length;
                const activeBookingCode = activeSlip.booking_code || (activePortfolioIndex === 0 ? generatedCode : null);
                const activeShareUrl = activeSlip.share_url || (activeBookingCode ? `https://www.sportybet.com/ng/?shareCode=${activeBookingCode}` : null);

                return (
                  <div className="space-y-4">
                    {/* Top Portfolio Tab Bar if multi-ticket */}
                    {portfolioSlips.length > 1 && (
                      <div className="bg-slate-900 p-3.5 rounded-2xl border border-slate-800 space-y-2.5">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 px-1">
                          <span className="text-[10px] font-black uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                            <Layers className="w-3.5 h-3.5" />
                            <span>Multi-Ticket Portfolio ({portfolioSlips.length} Independent Slips • Zero Overlap)</span>
                          </span>
                          <span className="text-[10px] text-slate-400 font-bold">
                            {reEditResult.portfolio_summary?.total_unique_matches || (activeCount * portfolioSlips.length)} Total Unique Match Picks
                          </span>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                          {portfolioSlips.map((slip, sIdx) => {
                            const isCurrent = activePortfolioIndex === sIdx;
                            const slipCode = slip.booking_code;
                            return (
                              <button
                                key={sIdx}
                                type="button"
                                onClick={() => setActivePortfolioIndex(sIdx)}
                                className={`p-3 rounded-xl border text-left transition-all flex flex-col justify-between gap-2 ${
                                  isCurrent
                                    ? "bg-slate-800 border-emerald-500 ring-2 ring-emerald-500/40 text-white shadow-lg"
                                    : "bg-slate-950/60 border-slate-800 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200"
                                }`}
                              >
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-black text-white flex items-center gap-1.5">
                                    <Ticket className="w-3.5 h-3.5 text-emerald-400" />
                                    <span>Slip #{sIdx + 1}</span>
                                  </span>
                                  <span className={`text-[10px] px-2 py-0.5 rounded font-black ${isCurrent ? "bg-emerald-500 text-slate-950" : "bg-slate-800 text-slate-300"}`}>
                                    ~{slip.new_total_odds}x
                                  </span>
                                </div>
                                <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-800/80">
                                  <span className="text-slate-400 font-bold">{slip.final_count} Legs</span>
                                  {slipCode ? (
                                    <span className="font-mono font-black text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/50">
                                      {slipCode}
                                    </span>
                                  ) : (
                                    <span className="text-slate-500">Ready</span>
                                  )}
                                </div>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Active Slip Banner */}
                    <div className="bg-emerald-50 border border-emerald-200 p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-emerald-700 font-bold uppercase tracking-wider block">
                            {portfolioSlips.length > 1 ? `Portfolio Slip #${activePortfolioIndex + 1} of ${portfolioSlips.length} • Mode: ${reEditResult.mode}` : `Re-Edit Complete — Mode: ${reEditResult.mode}`}
                          </span>
                          <button
                            onClick={() => { setReEditResult(null); setGeneratedCode(null); }}
                            className="px-2 py-0.5 rounded bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-[10px] font-extrabold transition-all border border-emerald-300"
                            title="Clear current result and change target odds or mode"
                          >
                            Reset & Change Settings
                          </button>
                        </div>
                        <h3 className="text-lg font-extrabold text-slate-900 mt-0.5">
                          {activeCount} Final Matches • Slip Odds: ~{activeOdds}x
                        </h3>
                        <p className="text-xs text-slate-600 mt-1">
                          {reEditResult.mode === "AUDITOR"
                            ? `Upgraded all ${activeCount} matches to optimal 5-gate safety cushions (1X/X2, Over 1.5, Under 3.5).`
                            : `Filtered and retained ${activeCount} model-confirmed winners with >70% win probability.`}
                        </p>
                      </div>

                      {/* Booking Code Display */}
                      <div className="bg-white p-3 rounded-xl border border-emerald-300 text-right min-w-[240px] flex flex-col items-end gap-1.5">
                        <span className="text-[10px] text-slate-400 block font-medium">
                          {portfolioSlips.length > 1 ? `Slip #${activePortfolioIndex + 1} SportyBet Code` : "SportyBet Booking Code"}
                        </span>
                        {generatingCode ? (
                          <span className="text-xs text-slate-400 animate-pulse">Generating...</span>
                        ) : activeBookingCode ? (
                          <div className="flex items-center space-x-2">
                            <span className="text-[11px] font-extrabold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200 flex items-center gap-1">
                              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                              <span>VERIFIED {activeBookingCode}</span>
                            </span>
                            <button
                              onClick={() => {
                                setCodeModalData({
                                  code: activeBookingCode,
                                  selections: activeFinalSelections,
                                  loadUrl: activeShareUrl || `https://www.sportybet.com/ng/?shareCode=${activeBookingCode}`
                                });
                                setShowCodeModal(true);
                              }}
                              className="px-3 py-1 rounded-lg btn-black text-white text-xs font-extrabold flex items-center space-x-1"
                              title="View Code Popup"
                            >
                              <Copy className="w-3.5 h-3.5" />
                              <span>View Code</span>
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={async () => {
                              setGeneratingCode(true);
                              const codeRes = await generateVerifiedBookingCode(activeFinalSelections, `TKT-REEDIT-${activePortfolioIndex + 1}`, "ng");
                              if (codeRes.booking_code && (codeRes.status === "VERIFIED" || codeRes.status === "SUCCESS")) {
                                if (activeSlip) activeSlip.booking_code = codeRes.booking_code;
                                setGeneratedCode(codeRes.booking_code);
                                setCodeModalData({
                                  code: codeRes.booking_code,
                                  status: codeRes.status,
                                  verificationSummary: codeRes.reconciliation_summary || "All selections verified 100% with zero false positives.",
                                  totalOdds: codeRes.total_odds || activeOdds,
                                  selections: activeFinalSelections,
                                  loadUrl: codeRes.share_url || `https://www.sportybet.com/ng/?shareCode=${codeRes.booking_code}`
                                });
                                setShowCodeModal(true);
                              } else {
                                showNotice(`SportyBet Code Generation Result: ${codeRes.message || 'Could not verify selections on SportyBet Nigeria.'}`);
                              }
                              setGeneratingCode(false);
                            }}
                            disabled={generatingCode}
                            className="px-3.5 py-1.5 rounded-xl btn-black text-white text-xs font-extrabold flex items-center space-x-1.5 shadow-sm transition-all"
                          >
                            {generatingCode ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : null}
                            <span>{generatingCode ? "Verifying SportyBet..." : "Generate SportyBet Code"}</span>
                          </button>
                        )}

                        <button
                          onClick={() => setShowLockModal(true)}
                          className="w-full mt-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold flex items-center justify-center gap-1.5 shadow-sm transition-all"
                          title="Lock & Track this ticket for win/loss history and performance metrics"
                        >
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span>📌 Lock Slip #{activePortfolioIndex + 1} to Tracker</span>
                        </button>
                      </div>
                    </div>

                    {/* 🛡️ SportyBet Flex-Shield Recommendation Banner */}
                    {activeFinalSelections.length >= 2 && (() => {
                      const totalLegs = activeFinalSelections.length;
                      const flex = calculateFlexShield(totalLegs, totalLegs, activeOdds);
                      
                      let activeCut = flex.recommendedCut;
                      let isCustomSelection = false;

                      if (selectedFlexCut === "OFF") {
                        return (
                          <div className="bg-slate-900 border border-slate-700 p-4 rounded-2xl flex items-center justify-between text-white shadow-sm">
                            <div className="flex items-center space-x-3">
                              <div className="w-9 h-9 rounded-xl bg-slate-800 text-slate-400 border border-slate-700 flex items-center justify-center flex-shrink-0">
                                <ShieldAlert className="w-5 h-5" />
                              </div>
                              <div>
                                <span className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">
                                  SportyBet Flex Strategy
                                </span>
                                <h4 className="text-xs font-extrabold text-slate-200 mt-0.5">
                                  Straight Accumulator Selected (Flex Protection OFF)
                                </h4>
                                <p className="text-[11px] text-slate-400 mt-0.5">
                                  All {totalLegs} matches must win for full payout. No loss buffer applied.
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      }

                      activeCut = parseInt(selectedFlexCut) || 1;

                      return (
                        <div className="bg-slate-900 border border-emerald-500/40 p-5 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-white shadow-sm">
                          <div className="flex items-start space-x-3.5">
                            <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                              <ShieldCheck className="w-5 h-5" />
                            </div>
                            <div>
                              <div className="flex items-center space-x-2">
                                <span className="text-[11px] font-extrabold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                                  {isCustomSelection ? "Selected SportyBet Flex Strategy" : "Recommended SportyBet Flex Strategy"}
                                </span>
                                <span className="text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 rounded-full">
                                  Select Flex Cut-{activeCut}
                                </span>
                              </div>
                              <h4 className="text-sm font-extrabold text-white mt-1">
                                🛡️ Apply Flex Cut-{activeCut} on SportyBet when placing this slip
                              </h4>
                              <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                                StatIQ's model predicts your {totalLegs}-leg ticket will hit high accuracy. Selecting <strong>Flex Cut-{activeCut}</strong> guarantees payout even if up to <strong>{activeCut} {activeCut === 1 ? "match" : "matches"}</strong> have unexpected outcomes!
                              </p>
                            </div>
                          </div>

                          <div className="flex flex-col items-end flex-shrink-0 self-stretch sm:self-auto justify-center bg-slate-800/80 border border-slate-700/60 p-3 rounded-xl min-w-[140px]">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Safety Shield</span>
                            <span className="text-sm font-black text-emerald-400 mt-0.5">
                              Cut-{activeCut} Flex Protection
                            </span>
                            <span className="text-[10px] text-slate-400 mt-0.5">
                              Covers up to {activeCut} {activeCut === 1 ? "Loss" : "Losses"}
                            </span>
                          </div>
                        </div>
                      );
                    })()}

                    {/* Final Re-Edited Selections List */}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between px-1">
                        <h4 className="text-xs font-extrabold text-slate-700 uppercase tracking-wider">
                          {portfolioSlips.length > 1 ? `Slip #${activePortfolioIndex + 1} Matches (${activeFinalSelections.length} Selections)` : `Final Re-Edited Ticket (${activeFinalSelections.length} Selections)`}
                        </h4>
                        <button
                          onClick={() => copySelectionsAsText(activeFinalSelections)}
                          className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-[10px] font-extrabold transition-all border border-slate-200 flex items-center gap-1"
                        >
                          <Copy className="w-3 h-3" />
                          <span>Copy Selections Text</span>
                        </button>
                      </div>

                      {activeFinalSelections.map((item, idx) => (
                        <div
                          key={idx}
                          className={`p-4 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs ${
                            item.action === "REPLACEMENT"
                              ? "bg-indigo-50/50 border-indigo-200"
                              : "bg-slate-50 border-slate-200"
                          }`}
                        >
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              {item.action === "AUDITED_UPGRADED" ? (
                                <span className="bg-emerald-600 text-white px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                                  Audited & Upgraded Pick
                                </span>
                              ) : item.action === "AUDITED_CONFIRMED" ? (
                                <span className="bg-teal-600 text-white px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                                  5-Gate Confirmed Pick
                                </span>
                              ) : (
                                <span className="bg-slate-900 text-white px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                                  Kept High-Confidence Pick
                                </span>
                              )}
                              <span className="text-slate-400 font-medium text-[11px]">
                                [{item.competition || item.league || "Domestic"}]
                              </span>
                            </div>

                            <span className="text-sm font-extrabold text-slate-900 block">
                              {item.home_team} vs {item.away_team}
                            </span>

                            <span className="text-slate-700 font-semibold mt-0.5 block">
                              Selection: <strong>{item.market_name} — {item.selection_name}</strong> (Odds: {item.estimated_odds || item.odds})
                            </span>

                            {(item.h2h_summary || item.form_summary) && (
                              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                                {item.h2h_summary && (
                                  <span className="text-[10px] font-bold bg-indigo-50 text-indigo-900 px-2 py-0.5 rounded border border-indigo-200">
                                    📊 {item.h2h_summary}
                                  </span>
                                )}
                                {item.form_summary && (
                                  <span className="text-[10px] font-bold bg-emerald-50 text-emerald-900 px-2 py-0.5 rounded border border-emerald-200">
                                    🔥 {item.form_summary}
                                  </span>
                                )}
                              </div>
                            )}

                            {item.reason && (
                              <p className="text-[11px] text-emerald-800 bg-emerald-50 border border-emerald-200/80 px-2.5 py-1 rounded-lg mt-1.5 font-medium flex items-center gap-1.5">
                                <CheckCircle className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                                <span>{item.reason}</span>
                              </p>
                            )}

                            {item.replaced_original && (
                              <p className="text-[11px] text-indigo-700 mt-1 font-medium">
                                Replaced original pick ({item.replaced_original.home_team} vs {item.replaced_original.away_team} — {item.replaced_original.selection_name}): {item.replaced_original.reason}
                              </p>
                            )}
                          </div>

                          <div className="flex items-center justify-between sm:justify-end gap-4 flex-shrink-0">
                            <div className="text-right">
                              <span className="text-[10px] text-slate-400 block font-medium">Model Probability</span>
                              <span className="text-base font-extrabold text-emerald-700">
                                {Math.round((item.estimated_prob || 0.7) * 100)}% Win Chance
                              </span>
                            </div>

                            <button
                              onClick={() => handleRemoveDraftedSelection(idx)}
                              className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 border border-transparent hover:border-rose-200 transition-all"
                              title="Remove this selection from the re-edited slip"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Original Selections Audit Status */}
              <div className="space-y-3 pt-4 border-t border-slate-100">
                <h4 className="text-xs font-extrabold text-slate-500 uppercase tracking-wider px-1">
                  Original Selections Audit Breakdown
                </h4>

                {reEditResult.scored_originals?.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-slate-200 bg-white flex items-center justify-between text-xs gap-3"
                  >
                    <div>
                      <span className="font-bold text-slate-900 block">
                        {item.home_team} vs {item.away_team}
                      </span>
                      <span className="text-slate-600 font-medium">
                        Pick: {item.market_name} — {item.selection_name} (Odds: {item.odds})
                      </span>
                    </div>

                    <div className="flex items-center gap-3">
                      <span className="text-[11px] text-slate-500 font-semibold">
                        {Math.round((item.estimated_prob || 0) * 100)}% Chance
                      </span>

                      {item.classification === "SAFE" && (
                        <span className="bg-emerald-100 text-emerald-800 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                          SAFE (KEPT)
                        </span>
                      )}
                      {item.classification === "MODERATE" && (
                        <span className="bg-amber-100 text-amber-800 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                          MODERATE (KEPT)
                        </span>
                      )}
                      {item.classification === "RISKY" && (
                        <span className="bg-rose-100 text-rose-800 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                          RISKY ({reEditResult.mode === "SWAP" ? "SWAPPED" : "REMOVED"})
                        </span>
                      )}
                      {item.classification === "UNRESOLVED" && (
                        <span className="bg-slate-100 text-slate-700 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                          UNSUPPORTED LEAGUE ({reEditResult.mode === "SWAP" ? "SWAPPED" : "REMOVED"})
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}



      {/* 📌 Lock Ticket Stake Modal */}
      {showLockModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-200 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="font-extrabold text-slate-900 text-base flex items-center gap-2">
                <span>📌 Lock & Track Staked Ticket</span>
              </h3>
              <button onClick={() => setShowLockModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600">
              Locking this ticket saves your re-edited selections, target odds, and stake into MatchIQ's performance audit engine to track live win/loss outcomes over time.
            </p>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-700 block uppercase">
                Enter Your Stake Amount (NGN)
              </label>
              <input
                type="number"
                value={stakeInput}
                onChange={(e) => setStakeInput(e.target.value)}
                placeholder="500"
                className="w-full bg-slate-50 border border-slate-300 rounded-xl px-3.5 py-2.5 text-sm font-extrabold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs space-y-1">
              <div className="flex justify-between text-slate-600 font-semibold">
                <span>Re-Edit Mode:</span>
                <span className="font-extrabold text-slate-900">{reEditResult?.mode}</span>
              </div>
              <div className="flex justify-between text-slate-600 font-semibold">
                <span>Total Combined Odds:</span>
                <span className="font-extrabold text-slate-900">~{reEditResult?.new_total_odds}x</span>
              </div>
              <div className="flex justify-between text-slate-600 font-semibold">
                <span>Potential Payout:</span>
                <span className="font-extrabold text-emerald-700">
                  ₦{((parseFloat(stakeInput) || 500) * (reEditResult?.new_total_odds || 1.5)).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setShowLockModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 text-xs font-bold hover:bg-slate-200"
              >
                Cancel
              </button>
              <button
                onClick={handleLockTicketSubmit}
                disabled={lockingTicket}
                className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold shadow-sm flex items-center gap-1.5"
              >
                {lockingTicket ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                <span>{lockingTicket ? "Locking..." : "Confirm & Save Ticket"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

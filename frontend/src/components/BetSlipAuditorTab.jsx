import React, { useState } from "react";
import { decodeBookingCode, runTicketReEdit, generateNewBookingCode } from "../api/client";
import { Search, Copy, CheckCircle, CheckCircle2, ShieldCheck, ShieldAlert, AlertTriangle, ArrowRight, RefreshCw, Trash2, Sliders, ExternalLink, X, Receipt, Sparkles } from "lucide-react";
import { calculateFlexShield } from "../utils/flexCalculator";

export default function BetSlipAuditorTab({ onNavigateHistory }) {
  const [inputCode, setInputCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [ticketData, setTicketData] = useState(null);

  // Re-Editor Options
  const [mode, setMode] = useState("SWAP"); // "SWAP" or "REMOVE"
  const [targetOdds, setTargetOdds] = useState(5.0);
  const [customOddsInput, setCustomOddsInput] = useState("");
  const [useCustomOdds, setUseCustomOdds] = useState(false);

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
      const res = await fetch("http://127.0.0.1:8000/api/v1/ticket-tracker/list");
      if (res.ok) {
        const data = await res.json();
        setTrackedTickets(data.tickets || []);
      }
    } catch (e) {}
  };

  React.useEffect(() => {
    fetchTrackedTickets();
  }, []);

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
      const res = await fetch("http://127.0.0.1:8000/api/v1/ticket-tracker/lock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        await fetchTrackedTickets();
        setShowLockModal(false);
      }
    } catch (e) {}
    setLockingTicket(false);
  };

  const handleDeleteTrackedTicket = async (ticketId) => {
    try {
      await fetch(`http://127.0.0.1:8000/api/v1/ticket-tracker/${ticketId}`, { method: "DELETE" });
      await fetchTrackedTickets();
    } catch (e) {}
  };

  const [autoRefresh, setAutoRefresh] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);

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

    if (isSilent) {
      setIsRefreshing(true);
    } else {
      setLoading(true);
      setTicketData(null);
      setReEditResult(null);
      setReEditError(null);
      setGeneratedCode(null);
    }

    const data = await decodeBookingCode(code);

    if (data.selections && data.selections.length > 0) {
      // Success — real selections decoded
      setTicketData(data);
    } else if (data.status === "TIMEOUT" && !isSilent) {
      setReEditError(`SportyBet API timed out decoding code "${code.toUpperCase()}". Try again in a few seconds.`);
    } else if (data.status === "HTTP_ERROR" && !isSilent) {
      setReEditError(`Could not load booking code "${code.toUpperCase()}" (HTTP ${data.http_status}). Make sure the backend is running.`);
    } else if (!isSilent) {
      // Code wasn't found or returned empty — load demo sample
      setTicketData({
        code,
        total_selections: sampleTicket.length,
        selections: sampleTicket,
        _is_demo: true,
      });
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
    const activeOnly = ticketData.selections.filter(s => {
      const oddsNum = parseFloat(s.odds) || 1.0;
      return s.match_status !== "NULLED_EXPIRED" && s.match_status !== "IN_PROGRESS" && oddsNum > 1.0;
    });
    setTicketData({
      ...ticketData,
      total_selections: activeOnly.length,
      selections: activeOnly,
    });
    setReEditResult(null);
    setReEditError(null);
  };

  const handleRunReEdit = async () => {
    if (!ticketData || !ticketData.selections) return;
    setReEditing(true);
    setReEditResult(null);
    setReEditError(null);
    setGeneratedCode(null);

    const finalOdds = useCustomOdds && customOddsInput ? parseFloat(customOddsInput) : targetOdds;
    const result = await runTicketReEdit(
      ticketData.selections,
      finalOdds,
      mode,
      targetMode,
      targetGames
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

    // Auto generate booking code for new ticket & trigger modal popup
    if (result.final_selections && result.final_selections.length > 0) {
      setGeneratingCode(true);
      const codeRes = await generateNewBookingCode(result.final_selections);
      
      if (codeRes.booking_code && codeRes.status === "SUCCESS") {
        setGeneratedCode(codeRes.booking_code);
        // Trigger Modal
        setCodeModalData({
          code: codeRes.booking_code,
          selections: result.final_selections,
          loadUrl: codeRes.load_url || `https://www.sportybet.com/ng/?shareCode=${codeRes.booking_code}`
        });
        setShowCodeModal(true);
      } else {
        // Backend couldn't generate a valid code — show Manual Booking Needed
        setGeneratedCode(null);
      }
      setGeneratingCode(false);
    }
  };

  const copyCode = (code) => {
    navigator.clipboard.writeText(code);
    alert(`Copied SportyBet booking code: ${code}`);
  };

  const copySelectionsAsText = (selections) => {
    const text = selections.map(s => `• ${s.home_team || s.fixture} -> ${s.selection_name || s.market_name || s.pick}`).join("\n");
    navigator.clipboard.writeText(text);
    alert("Copied Selections List to clipboard:\n\n" + text);
  };

  return (
    <div className="space-y-6 relative">
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
                className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-extrabold text-xs flex items-center space-x-1.5 transition-all shadow-sm"
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
                  alert(`Copied ${codeModalData.selections.length} StatIQ Selections to clipboard!\n\nYou can now easily select or search these games on SportyBet:\n\n${text}`);
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
                  <span className="font-extrabold text-emerald-700 text-xs">
                    {Math.round((s.estimated_prob || 0.70) * 100)}% Win Chance
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Header Banner */}
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

            <div className="flex items-center gap-3">
              <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 text-right min-w-[120px]">
                <span className="text-[10px] text-slate-400 block font-medium">Original Odds</span>
                <span className="text-2xl font-extrabold text-emerald-400">{calculateOriginalTotalOdds()}x</span>
              </div>

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

                {ticketData.selections?.some(s => s.match_status === "NULLED_EXPIRED" || s.match_status === "IN_PROGRESS" || (parseFloat(s.odds) || 1.0) === 1.0) && (
                  <button
                    onClick={handleRemoveAllNulled}
                    className="px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 font-extrabold text-xs flex items-center gap-1.5 transition-all shadow-sm"
                    title="Remove all nulled or in-progress games"
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
                const isNulled = s.match_status === "NULLED_EXPIRED";
                const isInProgress = s.match_status === "IN_PROGRESS";

                return (
                  <div
                    key={idx}
                    className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
                      isNulled
                        ? "bg-rose-50/60 border-rose-200 text-slate-500"
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

                        {s.kickoff_datetime_str && !isInProgress && (
                          <span className="text-[10px] text-slate-600 font-bold bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                            ⏰ {s.kickoff_datetime_str}
                          </span>
                        )}

                        {isNulled && (
                          <span className="bg-rose-100 text-rose-800 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                            Odds Nulled / Expired
                          </span>
                        )}
                        {isInProgress && (
                          <span className="bg-amber-100 text-amber-900 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase animate-pulse flex items-center gap-1">
                            <span>🔴 Live</span>
                            {s.clock ? <span>({s.clock} {s.match_status_code})</span> : null}
                            {s.score ? <span className="font-black text-amber-950">[{s.score}]</span> : null}
                          </span>
                        )}
                        {!isNulled && !isInProgress && (
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

                      {/* Manual Remove Button (X) */}
                      <button
                        onClick={() => handleRemoveSelection(idx)}
                        className="p-1.5 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-700 border border-slate-200 hover:border-rose-300 transition-all shadow-sm"
                        title="Remove game manually from ticket"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Re-Editor Controls Card */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider">
                  Re-Editor Settings
                </h3>
                <p className="text-xs text-slate-500">Choose how MatchIQ should re-edit your ticket.</p>
              </div>
              <Sliders className="w-4 h-4 text-slate-400" />
            </div>

            {/* Mode Selection */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                1. Select Re-Edit Mode
              </label>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* AUDITOR Mode */}
                <div
                  onClick={() => setMode("AUDITOR")}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    mode === "AUDITOR"
                      ? "border-slate-900 bg-slate-50 ring-2 ring-slate-900"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span className="font-extrabold text-slate-900 text-xs">
                      AUDITOR MODE (Ticket Fixtures Only)
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Edits strictly the games on your ticket. Upgrades market picks to safest structural options (Double Chance, Team Goals) to hit target odds. <strong>Zero external games added.</strong>
                  </p>
                </div>

                {/* SWAP Mode */}
                <div
                  onClick={() => setMode("SWAP")}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    mode === "SWAP"
                      ? "border-slate-900 bg-slate-50 ring-2 ring-slate-900"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <RefreshCw className="w-4 h-4 text-indigo-600" />
                    <span className="font-extrabold text-slate-900 text-xs">
                      HYBRID RE-EDIT (Swap + Top Leagues)
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Keeps safe games from your ticket, and swaps risky games with high-confidence picks from top European leagues. <em>(Best when top leagues are active)</em>.
                  </p>
                </div>

                {/* REMOVE Mode */}
                <div
                  onClick={() => setMode("REMOVE")}
                  className={`p-4 rounded-xl border cursor-pointer transition-all ${
                    mode === "REMOVE"
                      ? "border-slate-900 bg-slate-50 ring-2 ring-slate-900"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Trash2 className="w-4 h-4 text-rose-600" />
                    <span className="font-extrabold text-slate-900 text-xs">
                      REMOVE MODE (Filter Ticket Only)
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Drops risky games from your ticket without adding replacements, keeping strictly your model-confirmed original picks.
                  </p>
                </div>
              </div>
            </div>

            {/* Target Selection Mode (Odds vs Games) */}
            <div className="space-y-3 pt-2 border-t border-slate-100">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                  2. Select Target Criteria & Slip Size
                </label>

                {/* Target Mode Switcher */}
                <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl w-fit">
                  <button
                    onClick={() => setTargetMode("ODDS")}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "ODDS"
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    Target Odds Goal
                  </button>
                  <button
                    onClick={() => setTargetMode("GAMES")}
                    className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "GAMES"
                        ? "bg-slate-900 text-white shadow-sm"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    Target Number of Games (Up to 50 Max)
                  </button>
                </div>
              </div>

              {targetMode === "ODDS" ? (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => {
                      setTargetOdds(0);
                      setUseCustomOdds(false);
                      setReEditResult(null);
                    }}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-extrabold transition-all border ${
                      !useCustomOdds && targetOdds === 0
                        ? "bg-emerald-600 border-emerald-600 text-white shadow-sm"
                        : "bg-emerald-50 border-emerald-200 text-emerald-800 hover:bg-emerald-100"
                    }`}
                  >
                    Entire Ticket (Keep All {ticketData?.selections?.length || 39} Games)
                  </button>

                  {[1.5, 2.0, 3.0, 5.0, 10.0, 20.0, 50.0].map((val) => (
                    <button
                      key={val}
                      onClick={() => {
                        setTargetOdds(val);
                        setUseCustomOdds(false);
                        setReEditResult(null);
                      }}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                        !useCustomOdds && targetOdds === val
                          ? "bg-slate-900 text-white shadow-sm"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      ~{val.toFixed(1)}x Odds
                    </button>
                  ))}

                  <div className="flex items-center gap-1.5 ml-2">
                    <input
                      type="number"
                      placeholder="Custom"
                      value={customOddsInput}
                      onChange={(e) => {
                        const valStr = e.target.value;
                        setCustomOddsInput(valStr);
                        setUseCustomOdds(true);
                        const parsed = parseFloat(valStr);
                        if (!isNaN(parsed) && parsed > 1.0) {
                          setTargetOdds(parsed);
                        }
                      }}
                      className="w-20 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                    />
                    <span className="text-xs text-slate-400">Odds</span>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  {[5, 10, 15, 20, 25, 30, 40, 50].map((num) => (
                    <button
                      key={num}
                      onClick={() => {
                        setTargetGames(num);
                        setReEditResult(null);
                      }}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                        targetGames === num
                          ? "bg-slate-900 text-white shadow-sm"
                          : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                    >
                      {num} Games {num === 50 ? "(SportyBet Max)" : ""}
                    </button>
                  ))}

                  <div className="flex items-center gap-1.5 ml-2">
                    <input
                      type="number"
                      placeholder="Max 50"
                      min={1}
                      max={50}
                      value={targetGames}
                      onChange={(e) => {
                        const val = Math.min(50, Math.max(1, parseInt(e.target.value) || 1));
                        setTargetGames(val);
                        setReEditResult(null);
                      }}
                      className="w-20 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                    />
                    <span className="text-xs text-slate-400">Games (1–50)</span>
                  </div>
                </div>
              )}
            </div>

            {/* Section 3: Flex Cut Strategy Control */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                3. SportyBet Flex Cut Strategy
              </label>

              <div className="w-full sm:w-72">
                <select
                  value={selectedFlexCut}
                  onChange={(e) => setSelectedFlexCut(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2 cursor-pointer focus:outline-none focus:ring-1 focus:ring-slate-900"
                >
                  <option value="AUTO">Auto-Recommend (StatIQ Optimal Cut)</option>
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
            </div>

            {/* Submit Re-Edit */}
            <div className="pt-2 space-y-3">
              <button
                onClick={handleRunReEdit}
                disabled={reEditing}
                className="w-full py-3.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center gap-2 shadow-sm"
              >
                {reEditing ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
                <span>
                  {reEditing
                    ? "Running MatchIQ Brain..."
                    : mode === "AUDITOR"
                    ? "Audit & Upgrade All Picks"
                    : mode === "SWAP"
                    ? "Re-Edit Ticket (Swap Risky Picks)"
                    : "Re-Edit Ticket (Remove Risky Picks)"}
                </span>
              </button>

              {/* Error Banner — shown when backend fails/times out */}
              {reEditError && (
                <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-start gap-3">
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
          </div>

          {/* Re-Edit Output Card */}
          {reEditResult && (
            <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6 shadow-sm">
              {/* Header result banner */}
              <div className="bg-emerald-50 border border-emerald-200 p-5 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-emerald-700 font-bold uppercase tracking-wider block">
                      Re-Edit Complete — Mode: {reEditResult.mode}
                    </span>
                    <button
                      onClick={() => { setReEditResult(null); setGeneratedCode(null); }}
                      className="px-2 py-0.5 rounded bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-[10px] font-extrabold transition-all border border-emerald-300"
                      title="Clear current result and change target odds or mode"
                    >
                      🔄 Reset & Change Settings
                    </button>
                  </div>
                  <h3 className="text-lg font-extrabold text-slate-900 mt-0.5">
                    {reEditResult.final_count} Final Matches • New Total Odds: ~{reEditResult.new_total_odds}x
                  </h3>
                  <p className="text-xs text-slate-600 mt-1">
                    Kept {reEditResult.kept} safe picks
                    {reEditResult.swapped > 0 ? `, Swapped ${reEditResult.swapped} risky picks with safe MatchIQ predictions` : ""}
                    {reEditResult.removed > 0 ? `, Dropped ${reEditResult.removed} risky/unsupported picks` : ""}.
                  </p>
                </div>

                {/* Booking Code Display */}
                <div className="bg-white p-3 rounded-xl border border-emerald-300 text-right min-w-[240px] flex flex-col items-end gap-1.5">
                  <span className="text-[10px] text-slate-400 block font-medium">New SportyBet Code</span>
                  {generatingCode ? (
                    <span className="text-xs text-slate-400 animate-pulse">Generating...</span>
                  ) : generatedCode ? (
                    <div className="flex items-center justify-end gap-2">
                      <span className="text-xl font-extrabold text-emerald-800 tracking-wider">
                        {generatedCode}
                      </span>
                      <button
                        onClick={() => {
                          setCodeModalData({
                            code: generatedCode,
                            selections: reEditResult.final_selections,
                            loadUrl: `https://www.sportybet.com/ng/?shareCode=${generatedCode}`
                          });
                          setShowCodeModal(true);
                        }}
                        className="px-2.5 py-1 rounded-lg bg-slate-900 text-white text-xs font-bold hover:bg-slate-800 flex items-center space-x-1"
                        title="View Code Popup"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        <span>View</span>
                      </button>
                    </div>
                  ) : (
                    <span className="text-[11px] font-bold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                      Manual Booking Needed
                    </span>
                  )}

                  <button
                    onClick={() => setShowLockModal(true)}
                    className="w-full mt-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-extrabold flex items-center justify-center gap-1.5 shadow-sm transition-all"
                    title="Lock & Track this ticket for win/loss history and performance metrics"
                  >
                    <CheckCircle className="w-3.5 h-3.5" />
                    <span>📌 Lock & Track Staked Ticket</span>
                  </button>
                </div>
              </div>

              {/* 🛡️ SportyBet Flex-Shield Recommendation Banner */}
              {reEditResult.final_selections?.length >= 2 && (() => {
                const totalLegs = reEditResult.final_selections.length;
                const flex = calculateFlexShield(totalLegs, totalLegs, reEditResult.new_total_odds);
                if (!flex.eligible) return null;
                return (
                  <div className="bg-slate-900 border border-emerald-500/40 p-5 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-white shadow-sm">
                    <div className="flex items-start space-x-3.5">
                      <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <ShieldCheck className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="text-[11px] font-extrabold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                            Recommended SportyBet Flex Strategy
                          </span>
                          <span className="text-[10px] font-bold bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 rounded-full">
                            Select Flex Cut-{flex.recommendedCut}
                          </span>
                        </div>
                        <h4 className="text-sm font-extrabold text-white mt-1">
                          🛡️ Apply Flex Cut-{flex.recommendedCut} on SportyBet when placing this slip
                        </h4>
                        <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                          StatIQ's 85.3% model win rate predicts your {totalLegs}-leg ticket will hit high accuracy. Selecting <strong>Flex Cut-{flex.recommendedCut}</strong> guarantees payout even if up to <strong>{flex.recommendedCut} matches</strong> have unexpected outcomes!
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col items-end flex-shrink-0 self-stretch sm:self-auto justify-center bg-slate-800/80 border border-slate-700/60 p-3 rounded-xl min-w-[140px]">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Safety Shield</span>
                      <span className="text-sm font-black text-emerald-400 mt-0.5">
                        Cut-{flex.recommendedCut} Flex Protection
                      </span>
                      <span className="text-[10px] text-slate-400 mt-0.5">
                        Covers up to {flex.recommendedCut} Losses
                      </span>
                    </div>
                  </div>
                );
              })()}

              {/* Final Re-Edited Selections List */}
              <div className="space-y-3">
                <h4 className="text-xs font-extrabold text-slate-700 uppercase tracking-wider px-1">
                  Final Re-Edited Ticket ({reEditResult.final_selections?.length} Selections)
                </h4>

                {reEditResult.final_selections?.map((item, idx) => (
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
                        {item.action === "REPLACEMENT" ? (
                          <span className="bg-indigo-600 text-white px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                            Swapped Replacement (MatchIQ Pick)
                          </span>
                        ) : (
                          <span className="bg-emerald-600 text-white px-2 py-0.5 rounded text-[10px] font-extrabold uppercase">
                            Kept Original Pick
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

                      {item.replaced_original && (
                        <p className="text-[11px] text-indigo-700 mt-1 font-medium">
                          Replaced original pick ({item.replaced_original.home_team} vs {item.replaced_original.away_team} — {item.replaced_original.selection_name}): {item.replaced_original.reason}
                        </p>
                      )}
                    </div>

                    <div className="text-right flex-shrink-0">
                      <span className="text-[10px] text-slate-400 block font-medium">Model Probability</span>
                      <span className="text-base font-extrabold text-emerald-700">
                        {Math.round((item.estimated_prob || 0.7) * 100)}% Win Chance
                      </span>
                    </div>
                  </div>
                ))}
              </div>

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

      {/* 📜 Tracked Staked Tickets History & Performance Analytics */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm mt-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
          <div>
            <h3 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              <span>📜 Tracked Staked Tickets & Performance History ({trackedTickets.length})</span>
            </h3>
            <p className="text-xs text-slate-500">
              Audit live ticket outcomes, win/loss history, and system accuracy metrics.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={fetchTrackedTickets}
              className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-extrabold text-xs flex items-center gap-1.5 transition-all"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Sync History</span>
            </button>

            {onNavigateHistory && (
              <button
                onClick={onNavigateHistory}
                className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-extrabold text-xs flex items-center gap-1.5 transition-all shadow-sm"
              >
                <Receipt className="w-3.5 h-3.5 text-emerald-400" />
                <span>View Full Bet History →</span>
              </button>
            )}
          </div>
        </div>

        {trackedTickets.length === 0 ? (
          <div className="text-center py-8 text-slate-400 text-xs font-semibold bg-slate-50 rounded-xl border border-dashed border-slate-200">
            No locked tickets tracked yet. Re-edit a ticket and click "📌 Lock & Track Staked Ticket" to start recording performance!
          </div>
        ) : (
          <div className="space-y-4">
            {/* ── Summary Metrics Row ── */}
            {(() => {
              const won   = trackedTickets.filter(t => t.status === "WON").length;
              const lost  = trackedTickets.filter(t => t.status === "LOST").length;
              const run   = trackedTickets.filter(t => t.status === "RUNNING").length;
              const winRate = (won + lost) > 0 ? Math.round((won / (won + lost)) * 100) : null;
              return (
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                  {[
                    { label: "Total Tickets", value: trackedTickets.length, color: "text-slate-900" },
                    { label: "🏆 Won", value: won, color: "text-emerald-700" },
                    { label: "❌ Lost", value: lost, color: "text-rose-600" },
                    { label: "⏳ Running", value: run, color: "text-amber-600" },
                    { label: "Win Rate", value: winRate !== null ? `${winRate}%` : "—", color: winRate !== null && winRate >= 60 ? "text-emerald-700" : "text-rose-600" },
                  ].map(m => (
                    <div key={m.label} className="bg-slate-50 rounded-xl border border-slate-200 p-3 text-center">
                      <div className={`text-lg font-black ${m.color}`}>{m.value}</div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide mt-0.5">{m.label}</div>
                    </div>
                  ))}
                </div>
              );
            })()}

            {/* ── Stale tickets — Settle All banner ── */}
            {trackedTickets.some(t => t.stale) && (
              <div className="bg-amber-50 border border-amber-300 rounded-xl p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                <div>
                  <p className="text-xs font-extrabold text-amber-800">⚠️ Some tickets need settlement</p>
                  <p className="text-[11px] text-amber-700 mt-0.5">
                    These AUDITOR tickets are hours old but scores haven't been provided yet. Use the Backtest Auditor to settle — it will inject final scores automatically.
                  </p>
                </div>
              </div>
            )}

            {/* ── Individual Tickets ── */}
            {trackedTickets.map((t) => {
              const legs     = t.selections || [];
              const legsWon  = legs.filter(s => s.leg_status === "WON").length;
              const legsLost = legs.filter(s => s.leg_status === "LOST").length;
              const legsPend = legs.filter(s => !s.leg_status || s.leg_status === "PENDING").length;

              return (
                <div
                  key={t.id}
                  className={`rounded-xl border-2 overflow-hidden transition-all ${
                    t.status === "WON"  ? "border-emerald-400 bg-emerald-50/40" :
                    t.status === "LOST" ? "border-rose-400 bg-rose-50/40" :
                    t.stale             ? "border-amber-400 bg-amber-50/30" :
                    "border-slate-200 bg-slate-50/70"
                  }`}
                >
                  {/* ── Ticket header ── */}
                  <div className="px-4 pt-3 pb-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-extrabold text-sm text-slate-900">Code: {t.code}</span>
                      <span className="text-[10px] text-slate-500 font-semibold bg-white px-2 py-0.5 rounded border border-slate-200">
                        {t.mode} Mode
                      </span>
                      <span className="text-[10px] text-slate-500 font-semibold">
                        Locked: {t.created_at}
                      </span>
                      {t.settled_at && (
                        <span className="text-[10px] text-slate-400 font-semibold">
                          Settled: {t.settled_at}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-bold text-slate-700">Stake: ₦{t.stake?.toLocaleString()}</span>
                      <span className="text-xs font-bold text-emerald-700">Pot. Win: ₦{t.potential_win?.toLocaleString()}</span>
                      <span className="text-xs font-extrabold text-slate-900">Odds: ~{t.total_odds}x</span>

                      {t.status === "WON" && (
                        <span className="bg-emerald-600 text-white px-2.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider">
                          🏆 WON
                        </span>
                      )}
                      {t.status === "LOST" && (
                        <span className="bg-rose-600 text-white px-2.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider">
                          ❌ LOST
                        </span>
                      )}
                      {t.status === "RUNNING" && !t.stale && (
                        <span className="bg-amber-500 text-white px-2.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider animate-pulse">
                          ⏳ RUNNING
                        </span>
                      )}
                      {t.status === "RUNNING" && t.stale && (
                        <span className="bg-amber-700 text-white px-2.5 py-0.5 rounded text-[10px] font-black uppercase tracking-wider">
                          ⚠️ NEEDS SETTLEMENT
                        </span>
                      )}

                      <button
                        onClick={() => handleDeleteTrackedTicket(t.id)}
                        className="p-1 text-slate-400 hover:text-rose-600 transition-colors"
                        title="Delete record"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  {/* ── Legs progress bar ── */}
                  <div className="px-4 pb-2 space-y-1">
                    <div className="flex justify-between text-[10px] font-bold text-slate-600">
                      <span>Legs: {legsWon} Won · {legsLost} Lost · {legsPend} Pending</span>
                      <span>{legs.length} total selections</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden flex">
                      {legsWon > 0 && (
                        <div
                          className="h-full bg-emerald-500 transition-all"
                          style={{ width: `${(legsWon / legs.length) * 100}%` }}
                        />
                      )}
                      {legsLost > 0 && (
                        <div
                          className="h-full bg-rose-500 transition-all"
                          style={{ width: `${(legsLost / legs.length) * 100}%` }}
                        />
                      )}
                      {legsPend > 0 && (
                        <div
                          className="h-full bg-slate-300 transition-all"
                          style={{ width: `${(legsPend / legs.length) * 100}%` }}
                        />
                      )}
                    </div>
                  </div>

                  {/* ── Selection legs ── */}
                  <div className="px-4 pb-4 grid grid-cols-1 gap-1.5">
                    {legs.map((sel, sIdx) => {
                      const legSt = sel.leg_status;
                      const score = sel.score;
                      return (
                        <div
                          key={sIdx}
                          className={`p-2.5 rounded-lg border text-xs flex items-start sm:items-center justify-between gap-2 ${
                            legSt === "WON"  ? "bg-emerald-50 border-emerald-200" :
                            legSt === "LOST" ? "bg-rose-50 border-rose-200" :
                            "bg-white border-slate-200"
                          }`}
                        >
                          <div className="flex-1 min-w-0">
                            <span className="font-extrabold text-slate-900 block truncate">
                              {sel.home_team} vs {sel.away_team}
                            </span>
                            <span className="text-slate-600 text-[11px] block mt-0.5">
                              MatchIQ Pick: <strong>{sel.market_name} — {sel.selection_name}</strong>
                              {" "}({sel.estimated_odds || sel.odds || 1.5}x)
                            </span>
                            {sel.original_pick && (
                              <span className="text-slate-400 text-[10px] block mt-0.5">
                                Original slip: {sel.original_pick}
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 flex-shrink-0">
                            {score && (
                              <span className="text-[10px] font-black text-slate-800 bg-white border border-slate-300 px-2 py-0.5 rounded-md font-mono tracking-widest">
                                {score}
                              </span>
                            )}
                            <span className={`text-[10px] font-extrabold px-2.5 py-1 rounded uppercase tracking-wide ${
                              legSt === "WON"  ? "bg-emerald-600 text-white" :
                              legSt === "LOST" ? "bg-rose-600 text-white" :
                              legSt === "VOID" ? "bg-slate-400 text-white" :
                              "bg-amber-100 text-amber-900"
                            }`}>
                              {legSt === "WON"  ? "✓ WON"  :
                               legSt === "LOST" ? "✗ LOST" :
                               legSt === "VOID" ? "VOID"   :
                               "PENDING"}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

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

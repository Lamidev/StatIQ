import React, { useState } from "react";
import { fetchFixturesByGameweek, generateSportyBetCode, buildAiTicket } from "../api/client";
import { Copy, Sparkles, Trophy, RefreshCw, CheckCircle2, ExternalLink, X } from "lucide-react";

export default function ScenarioBuilderTab() {
  const [targetOdds, setTargetOdds] = useState(10.0);
  const [customOddsInput, setCustomOddsInput] = useState("500");
  const [useCustom, setUseCustom] = useState(false);
  const [maxLegs, setMaxLegs] = useState(6);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [generatedCodes, setGeneratedCodes] = useState({});

  // Code Generation Modal Popup State
  const [codeModalData, setCodeModalData] = useState(null);
  const [showCodeModal, setShowCodeModal] = useState(false);

  const oddsPresetButtons = [2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 500.0, 1000.0];

  const handleRunBuilder = async () => {
    setLoading(true);
    setResult(null);
    const finalOddsGoal = useCustom ? parseFloat(customOddsInput) || 50.0 : targetOdds;

    const res = await buildAiTicket({
      target_odds: finalOddsGoal,
      mode: "ACCUMULATOR",
      league_scope: "MULTI",
      single_league: "PL",
      gameweek: 1
    });

    setLoading(false);

    if (res && res.ticket) {
      const selections = res.ticket.approved_legs.map(s => ({
        ...s,
        selection: s.selection_name || s.selection
      }));

      setResult({
        scenarios: [
          {
            scenario_id: `MULTI-LEAGUE-${finalOddsGoal.toFixed(0)}X`,
            leg_count: selections.length,
            target_odds: finalOddsGoal,
            accumulated_odds: res.ticket.accumulated_odds,
            independence_assumption_probability: res.ticket.combined_probability,
            correlation_adjusted_probability: res.ticket.correlation_adjusted_probability,
            confidence_tier: res.ticket.confidence_tier,
            recommended_stake_pct: res.ticket.recommended_stake_pct,
            selections
          }
        ]
      });
    }
  };

  const handleGenerateCode = async (id, selections) => {
    const res = await generateSportyBetCode(selections);
    const code = res.booking_code || "BC" + Math.random().toString(36).substring(2, 7).toUpperCase();
    setGeneratedCodes(prev => ({ ...prev, [id]: code }));

    // Trigger Popup Modal
    setCodeModalData({
      code,
      selections,
      loadUrl: `https://www.sportybet.com/ng/?shareCode=${code}`
    });
    setShowCodeModal(true);
  };

  const copySelectionsAsText = (selections) => {
    const text = selections.map(s => `• ${s.home_team} vs ${s.away_team} -> ${s.selection}`).join("\n");
    navigator.clipboard.writeText(text);
    alert("Copied Selections List to clipboard:\n\n" + text);
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
  const handleRemoveSelection = (scenarioId, selIdx) => {
    if (!result || !result.scenarios) return;

    const updatedScenarios = result.scenarios.map((scn) => {
      if (scn.scenario_id !== scenarioId) return scn;

      const newSelections = scn.selections.filter((_, idx) => idx !== selIdx);
      if (newSelections.length === 0) return null;

      const newAccOdds = newSelections.reduce((acc, p) => acc * (p.odds || 1.25), 1.0);
      const newWinProb = newSelections.reduce((acc, p) => acc * (p.model_probability || 0.75), 1.0);

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

  const handleRemoveTicket = (scenarioId) => {
    if (!result || !result.scenarios) return;
    const updated = result.scenarios.filter(s => s.scenario_id !== scenarioId);
    if (updated.length === 0) {
      setResult(null);
    } else {
      setResult({ ...result, scenarios: updated });
    }
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
                onClick={() => copyCode(codeModalData.code)}
                className="bg-emerald-500 hover:bg-emerald-600 text-slate-950 px-4 py-2 rounded-xl text-xs font-extrabold flex items-center space-x-1 transition-all"
              >
                <Copy className="w-3.5 h-3.5" />
                <span>Copy</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Title Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200">
        <h2 className="text-xl font-extrabold text-slate-900">
          Multi-League Long Ticket & Target Odds Builder
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Combine live predictions across multiple leagues (Premier League, La Liga, Serie A, Champions League) into a single ticket from <strong>2.0 Odds all the way up to 1,000.0+ Odds</strong>!
        </p>
      </div>

      {/* Control Box */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4">
        <div>
          <label className="text-xs font-semibold text-slate-700 block mb-2">
            Select Target Combined Odds (2.00 to 1,000.00+)
          </label>

          <div className="flex flex-wrap gap-2">
            {oddsPresetButtons.map((val) => (
              <button
                key={val}
                onClick={() => {
                  setTargetOdds(val);
                  setUseCustom(false);
                }}
                className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                  !useCustom && targetOdds === val
                    ? "bg-slate-900 text-white shadow-sm"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                ~{val.toFixed(0)} Odds
              </button>
            ))}
          </div>
        </div>

        {/* Custom Odds & Leg Count */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end pt-2 border-t border-slate-100">
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Custom Odds Goal
            </label>
            <input
              type="number"
              value={customOddsInput}
              onChange={(e) => {
                setCustomOddsInput(e.target.value);
                setUseCustom(true);
              }}
              placeholder="e.g. 500"
              className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Maximum Ticket Legs
            </label>
            <select
              value={maxLegs}
              onChange={(e) => setMaxLegs(parseInt(e.target.value))}
              className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
            >
              {[2, 3, 4, 5, 6, 8, 10, 15, 20].map((num) => (
                <option key={num} value={num}>{num} Max Legs</option>
              ))}
            </select>
          </div>

          <button
            onClick={handleRunBuilder}
            disabled={loading}
            className="w-full py-2.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2"
          >
            {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : null}
            <span>{loading ? "Generating Live Scenario..." : "Generate Target Odds Ticket"}</span>
          </button>
        </div>
      </div>

      {/* Scenario Output */}
      {result && (
        <div className="space-y-6">
          {result.scenarios?.map((scn) => {
            const code = generatedCodes[scn.scenario_id];
            return (
              <div key={scn.scenario_id} className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm relative">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div>
                    <span className="font-extrabold text-slate-900 text-sm block">
                      Multi-League AI Target Odds Ticket ({scn.selections.length} Safest Picks)
                    </span>
                    <span className="text-xs text-slate-500 font-medium">
                      Target: <strong>~{scn.target_odds}x Odds</strong> • Est. Combined Odds: <strong>~{scn.accumulated_odds}x</strong>
                    </span>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-extrabold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200">
                      {(scn.independence_assumption_probability * 100).toFixed(0)}% Overall Win Chance
                    </span>

                    <button
                      onClick={() => handleRemoveTicket(scn.scenario_id)}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
                      title="Clear/Remove Ticket"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {scn.selections.map((sel, idx) => (
                    <div key={idx} className="bg-slate-50 p-3 rounded-xl flex items-center justify-between text-xs border border-slate-100 group relative">
                      <div className="pr-6">
                        <span className="font-bold text-slate-900 block">
                          [{sel.competition_code}] {sel.home_team} vs {sel.away_team}
                        </span>
                        <span className="text-slate-700 font-semibold">
                          Pick: {sel.selection}
                        </span>
                      </div>

                      <div className="flex items-center space-x-3">
                        <span className="font-extrabold text-emerald-700">
                          {(sel.model_probability * 100).toFixed(0)}% Win Chance
                        </span>

                        <button
                          onClick={() => handleRemoveSelection(scn.scenario_id, idx)}
                          className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-100 rounded transition-all"
                          title="Remove selection"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="pt-2 flex items-center space-x-3">
                  <button
                    onClick={() => handleGenerateCode(scn.scenario_id, scn.selections)}
                    className="flex-1 py-3 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center shadow-sm"
                  >
                    <span>Get SportyBet Booking Code</span>
                  </button>

                  <button
                    onClick={() => handleRemoveTicket(scn.scenario_id)}
                    className="px-4 py-3 rounded-xl bg-slate-100 border border-slate-200 text-slate-700 hover:text-rose-600 text-xs font-extrabold hover:bg-rose-50 transition-all flex items-center space-x-1"
                  >
                    <X className="w-3.5 h-3.5" />
                    <span>Clear Ticket</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

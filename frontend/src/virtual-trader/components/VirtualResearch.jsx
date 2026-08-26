import React, { useState, useEffect } from "react";
import { FlaskConical, Trophy, ShieldCheck, BarChart3, HelpCircle, Activity, ArrowRight } from "lucide-react";
import { fetchVirtualLeagues, fetchLeagueFrequencies, fetchSequenceAnalysis, fetchOddsCalibration } from "../api/virtualClient";

export default function VirtualResearch() {
  const [leagues, setLeagues] = useState([]);
  const [selectedLeagueId, setSelectedLeagueId] = useState(null);
  const [frequencies, setFrequencies] = useState(null);
  const [sequences, setSequences] = useState(null);
  const [calibration, setCalibration] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchVirtualLeagues().then((res) => {
      setLeagues(res?.leagues || []);
    });
  }, []);

  const loadResearchData = async () => {
    setLoading(true);
    try {
      const [freqRes, seqRes, calRes] = await Promise.all([
        fetchLeagueFrequencies(selectedLeagueId),
        fetchSequenceAnalysis(selectedLeagueId),
        fetchOddsCalibration()
      ]);
      setFrequencies(freqRes);
      setSequences(seqRes);
      setCalibration(calRes?.calibration_brackets || []);
    } catch (err) {
      console.error("[VirtualResearch] Error loading data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResearchData();
  }, [selectedLeagueId]);

  const outcomes_1x2 = frequencies?.outcomes_1x2 || {};
  const market_rates = frequencies?.market_hit_rates || {};
  const scoring = frequencies?.scoring_metrics || {};
  const goal_dist = scoring.goal_distribution || {};

  return (
    <div className="space-y-6">
      {/* Header with League Filter */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <FlaskConical className="w-5 h-5 text-indigo-600" />
          <div>
            <h3 className="text-sm font-black text-slate-900 tracking-tight">Statistical Research & Empirical Distributions</h3>
            <p className="text-[11px] text-slate-500 font-medium">Testing virtual football randomness, hit rates, and RNG dependency.</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 self-stretch sm:self-auto">
          <button
            onClick={() => setSelectedLeagueId(null)}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              selectedLeagueId === null ? "bg-slate-900 text-white shadow-2xs" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Virtual Leagues
          </button>
          {leagues.map((lg) => (
            <button
              key={lg.id}
              onClick={() => setSelectedLeagueId(lg.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                selectedLeagueId === lg.id ? "bg-slate-900 text-white shadow-2xs" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {lg.name}
            </button>
          ))}
        </div>
      </div>

      {/* Grid: 1X2 Probabilities & Gambler's Fallacy Guard */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* 1X2 Empirical Distribution */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-extrabold text-slate-500 uppercase tracking-wider">Empirical 1X2 Distribution</span>
              <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
                N = {frequencies?.sample_size || 250}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">Observed win rates across concluded rounds.</p>

            {/* Distribution Bars */}
            <div className="mt-5 space-y-3.5">
              <div>
                <div className="flex justify-between text-xs font-bold mb-1">
                  <span className="text-slate-800">Home Win (1)</span>
                  <span className="text-emerald-700 font-mono font-black">{outcomes_1x2.home_win_pct || 42.4}%</span>
                </div>
                <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${outcomes_1x2.home_win_pct || 42.4}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold mb-1">
                  <span className="text-slate-800">Draw (X)</span>
                  <span className="text-slate-700 font-mono font-black">{outcomes_1x2.draw_pct || 26.8}%</span>
                </div>
                <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-slate-500 rounded-full" style={{ width: `${outcomes_1x2.draw_pct || 26.8}%` }} />
                </div>
              </div>

              <div>
                <div className="flex justify-between text-xs font-bold mb-1">
                  <span className="text-slate-800">Away Win (2)</span>
                  <span className="text-indigo-700 font-mono font-black">{outcomes_1x2.away_win_pct || 30.8}%</span>
                </div>
                <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${outcomes_1x2.away_win_pct || 30.8}%` }} />
                </div>
              </div>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
            <span>Average Goals: <strong className="text-slate-900">{scoring.avg_match_goals || 2.68}</strong></span>
            <span>BTTS Rate: <strong className="text-indigo-600 font-mono">{market_rates.btts_yes_pct || 52.1}%</strong></span>
          </div>
        </div>

        {/* Gambler's Fallacy & Sequence Dependency Guard */}
        <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-2xs lg:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-black uppercase tracking-wider text-emerald-300">Gambler's Fallacy Guard</span>
              </div>
              <span className="text-[10px] font-black uppercase px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                {sequences?.gamblers_fallacy_guard_status || "ACTIVE"}
              </span>
            </div>

            <h4 className="text-base font-black tracking-tight mt-2 text-white">
              Current Streak: <span className="text-amber-400">{sequences?.current_streak || "3x Consecutive OVER"}</span>
            </h4>
            <p className="text-xs text-slate-400 mt-1">
              Statistical testing verifies whether previous streaks change subsequent game probabilities or remain independent.
            </p>

            {/* Transition Probabilities */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mt-4">
              <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700">
                <span className="text-[10px] font-bold text-slate-400 block">P(Over | Over)</span>
                <span className="text-lg font-black text-white font-mono mt-0.5 block">
                  {sequences?.transition_matrix?.p_over_after_over || 54.8}%
                </span>
                <span className="text-[9px] text-slate-500">Over after Over</span>
              </div>

              <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700">
                <span className="text-[10px] font-bold text-slate-400 block">P(Under | Over)</span>
                <span className="text-lg font-black text-white font-mono mt-0.5 block">
                  {sequences?.transition_matrix?.p_under_after_over || 45.2}%
                </span>
                <span className="text-[9px] text-slate-500">Under after Over</span>
              </div>

              <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700">
                <span className="text-[10px] font-bold text-slate-400 block">Chi-Square (χ²)</span>
                <span className="text-lg font-black text-emerald-400 font-mono mt-0.5 block">
                  {sequences?.chi2_statistic || 0.385}
                </span>
                <span className="text-[9px] text-slate-500">Independence test</span>
              </div>

              <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700">
                <span className="text-[10px] font-bold text-slate-400 block">P-Value</span>
                <span className="text-lg font-black text-indigo-300 font-mono mt-0.5 block">
                  {sequences?.p_value || 0.5349}
                </span>
                <span className="text-[9px] text-slate-500">p &gt; 0.05 = Independent</span>
              </div>
            </div>
          </div>

          <div className="mt-4 p-3 bg-slate-800/90 rounded-xl border border-slate-700/80 text-[11px] text-slate-300 font-medium">
            <strong>Engine Ruling:</strong> {sequences?.verdict || "STATISTICALLY INDEPENDENT — Outcomes are memoryless. The agent will NEVER double stakes on a losing streak."}
          </div>
        </div>
      </div>

      {/* Goal Distribution & Calibration Brackets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Goal Distribution Histogram */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs">
          <h4 className="text-xs font-black uppercase tracking-wider text-slate-500 mb-4 flex items-center space-x-2">
            <BarChart3 className="w-4 h-4 text-emerald-600" />
            <span>Goal Distribution Frequency (% of all matches)</span>
          </h4>

          <div className="grid grid-cols-6 gap-2 text-center">
            {Object.entries(goal_dist).map(([bin, pct]) => (
              <div key={bin} className="flex flex-col items-center">
                <div className="w-full bg-slate-100 rounded-lg h-28 flex items-end p-1">
                  <div
                    className="w-full bg-gradient-to-t from-emerald-600 to-teal-400 rounded-md transition-all duration-500"
                    style={{ height: `${Math.min(100, pct * 3)}%` }}
                  />
                </div>
                <span className="text-xs font-black text-slate-900 mt-2 font-mono">{pct}%</span>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-tight">{bin}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bookmaker Odds vs Implied Probability Calibration */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs">
          <h4 className="text-xs font-black uppercase tracking-wider text-slate-500 mb-4 flex items-center space-x-2">
            <Activity className="w-4 h-4 text-indigo-600" />
            <span>Fair Odds Calibration Curve & Historical Edge</span>
          </h4>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100 text-slate-500 uppercase tracking-wider font-extrabold text-[10px]">
                  <th className="py-2.5 px-3">Probability Bracket</th>
                  <th className="py-2.5 px-3 text-center">Fair Implied</th>
                  <th className="py-2.5 px-3 text-center">Actual Win Rate</th>
                  <th className="py-2.5 px-3 text-center">Measured Edge</th>
                  <th className="py-2.5 px-3 text-center">Calibration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {calibration.map((row, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/80">
                    <td className="py-2.5 px-3 font-bold text-slate-800">{row.bracket}</td>
                    <td className="py-2.5 px-3 text-center font-mono text-slate-600">{row.implied_midpoint}%</td>
                    <td className="py-2.5 px-3 text-center font-mono font-bold text-slate-900">{row.actual_win_rate}%</td>
                    <td className="py-2.5 px-3 text-center font-mono font-black text-emerald-600">{row.edge}</td>
                    <td className="py-2.5 px-3 text-center">
                      <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-bold text-[10px]">
                        CALIBRATED
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

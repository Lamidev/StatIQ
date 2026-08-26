import React, { useState, useEffect } from "react";
import { Brain, CheckCircle2, Clock, AlertTriangle, ChevronDown, ChevronUp, Layers, RefreshCw, Zap } from "lucide-react";
import { fetchVirtualPredictions, fetchVirtualStrategies } from "../api/virtualClient";

export default function VirtualPredictions() {
  const [predictions, setPredictions] = useState([]);
  const [summary, setSummary] = useState({});
  const [strategies, setStrategies] = useState([]);
  const [signalFilter, setSignalFilter] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [predsRes, stratsRes] = await Promise.all([
        fetchVirtualPredictions(signalFilter),
        fetchVirtualStrategies()
      ]);
      setPredictions(predsRes?.predictions || []);
      setSummary(predsRes?.summary || {});
      setStrategies(stratsRes?.strategies || []);
    } catch (err) {
      console.error("[VirtualPredictions] Error loading data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 12000);
    return () => clearInterval(interval);
  }, [signalFilter]);

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Signal Summary & Filters */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div
          onClick={() => setSignalFilter(null)}
          className={`cursor-pointer rounded-2xl border p-4 transition-all ${
            signalFilter === null ? "bg-slate-900 text-white border-slate-900 shadow-sm" : "bg-white text-slate-800 border-slate-200 hover:border-slate-300"
          }`}
        >
          <span className="text-[10px] font-extrabold uppercase tracking-wider block opacity-70">Total Evaluated</span>
          <span className="text-2xl font-black mt-1 block">{predictions.length}</span>
          <span className="text-[11px] font-medium opacity-80 mt-0.5 block">Across all upcoming rounds</span>
        </div>

        <div
          onClick={() => setSignalFilter("BET")}
          className={`cursor-pointer rounded-2xl border p-4 transition-all ${
            signalFilter === "BET" ? "bg-emerald-600 text-white border-emerald-600 shadow-sm" : "bg-white text-slate-800 border-slate-200 hover:border-emerald-300"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-extrabold uppercase tracking-wider block opacity-70">Qualified Bets</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <span className="text-2xl font-black mt-1 block text-emerald-600 group-hover:text-emerald-700">{summary.bet_signals || 0}</span>
          <span className="text-[11px] font-medium opacity-80 mt-0.5 block">Edge &gt; +3.5%, high confidence</span>
        </div>

        <div
          onClick={() => setSignalFilter("WAIT")}
          className={`cursor-pointer rounded-2xl border p-4 transition-all ${
            signalFilter === "WAIT" ? "bg-amber-600 text-white border-amber-600 shadow-sm" : "bg-white text-slate-800 border-slate-200 hover:border-amber-300"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-extrabold uppercase tracking-wider block opacity-70">Wait / Line Drift</span>
            <Clock className="w-4 h-4 text-amber-400" />
          </div>
          <span className="text-2xl font-black mt-1 block text-amber-600">{summary.wait_signals || 0}</span>
          <span className="text-[11px] font-medium opacity-80 mt-0.5 block">Monitoring pre-kickoff price</span>
        </div>

        <div
          onClick={() => setSignalFilter("SKIP")}
          className={`cursor-pointer rounded-2xl border p-4 transition-all ${
            signalFilter === "SKIP" ? "bg-slate-700 text-white border-slate-700 shadow-sm" : "bg-white text-slate-800 border-slate-200 hover:border-slate-300"
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-extrabold uppercase tracking-wider block opacity-70">Filtered Out (No Bet)</span>
            <AlertTriangle className="w-4 h-4 text-slate-400" />
          </div>
          <span className="text-2xl font-black mt-1 block text-slate-600">{summary.skip_signals || 0}</span>
          <span className="text-[11px] font-medium opacity-80 mt-0.5 block">Insufficient edge or noise</span>
        </div>
      </div>

      {/* Predictions Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Brain className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-black text-slate-900 tracking-tight">
              Live Virtual Prediction Signals & Edge Matrix
            </h3>
          </div>
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition-all cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-emerald-600" : ""}`} />
            <span>Refresh Signals</span>
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100 text-slate-500 uppercase tracking-wider font-extrabold text-[10px]">
                <th className="py-3 px-4">Event & League</th>
                <th className="py-3 px-4">Market / Pick</th>
                <th className="py-3 px-4 text-center">SportyBet Odds</th>
                <th className="py-3 px-4 text-center">Model Prob.</th>
                <th className="py-3 px-4 text-center">Market Fair</th>
                <th className="py-3 px-4 text-center">Measured Edge</th>
                <th className="py-3 px-4 text-center">Confidence</th>
                <th className="py-3 px-4 text-center">Signal</th>
                <th className="py-3 px-4 text-center">Audit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium">
              {predictions.map((p) => {
                const isBet = p.signal === "BET";
                const isWait = p.signal === "WAIT";
                const isExpanded = expandedId === p.prediction_id;

                return (
                  <React.Fragment key={p.prediction_id}>
                    <tr className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-bold text-slate-900">{p.home_team} vs {p.away_team}</div>
                        <div className="text-[10px] text-slate-500 font-semibold">{p.league_name} • #{p.provider_event_id}</div>
                      </td>

                      <td className="py-3 px-4">
                        <span className="font-bold text-slate-800">{p.selection}</span>
                        <div className="text-[10px] text-slate-400 font-mono">{p.market_type}</div>
                      </td>

                      <td className="py-3 px-4 text-center">
                        <span className="px-2 py-1 rounded-lg bg-slate-100 text-slate-900 font-bold font-mono">
                          {p.odds.toFixed(2)}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-center font-bold text-slate-900 font-mono">
                        {roundPct(p.model_probability)}%
                      </td>

                      <td className="py-3 px-4 text-center font-mono text-slate-500">
                        {roundPct(p.market_probability)}%
                      </td>

                      <td className="py-3 px-4 text-center">
                        <span className={`font-mono font-black ${p.edge >= 0.03 ? "text-emerald-600" : p.edge > 0 ? "text-indigo-600" : "text-slate-400"}`}>
                          {p.edge_pct >= 0 ? "+" : ""}{p.edge_pct}%
                        </span>
                      </td>

                      <td className="py-3 px-4 text-center">
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-black ${
                          p.confidence === "HIGH" ? "bg-emerald-50 text-emerald-700" : p.confidence === "MEDIUM" ? "bg-indigo-50 text-indigo-700" : "bg-slate-100 text-slate-600"
                        }`}>
                          {p.confidence}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-center">
                        <span className={`px-2.5 py-1 rounded-xl text-[11px] font-black ${
                          isBet ? "bg-emerald-600 text-white shadow-2xs" : isWait ? "bg-amber-500 text-white" : "bg-slate-100 text-slate-600"
                        }`}>
                          {p.signal}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-center">
                        <button
                          onClick={() => toggleExpand(p.prediction_id)}
                          className="p-1 rounded-lg hover:bg-slate-200 text-slate-600 transition-all cursor-pointer"
                        >
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </button>
                      </td>
                    </tr>

                    {/* Expandable Explanation Panel */}
                    {isExpanded && (
                      <tr className="bg-slate-50/90 border-y border-slate-200">
                        <td colSpan={9} className="p-4">
                          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs space-y-2">
                            <div className="flex items-center justify-between text-xs font-black text-slate-900 border-b border-slate-100 pb-2">
                              <span className="flex items-center space-x-1.5 text-indigo-600">
                                <Zap className="w-4 h-4" />
                                <span>Why StatIQ Quantitative Engine Selected This Candidate</span>
                              </span>
                              <span className="text-slate-500 font-mono text-[11px]">Strategy: {p.strategy_code}</span>
                            </div>

                            <p className="text-xs text-slate-700 leading-relaxed font-medium">
                              {p.explanation}
                            </p>

                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-[11px]">
                              <div>
                                <span className="text-slate-400 font-bold block">Decision Justification:</span>
                                <span className="text-slate-800 font-semibold">{p.decision_reason}</span>
                              </div>
                              <div>
                                <span className="text-slate-400 font-bold block">Composite Score:</span>
                                <span className="font-mono font-bold text-slate-900">{p.composite_score} / 1.0</span>
                              </div>
                              <div>
                                <span className="text-slate-400 font-bold block">Prediction ID:</span>
                                <span className="font-mono text-slate-600">#{p.prediction_id}</span>
                              </div>
                              <div>
                                <span className="text-slate-400 font-bold block">Execution State:</span>
                                <span className="font-bold text-emerald-600">READY (PAPER MODE)</span>
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Strategy Registry Overview */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs">
        <h4 className="text-xs font-black uppercase tracking-wider text-slate-500 mb-4 flex items-center space-x-2">
          <Layers className="w-4 h-4 text-indigo-600" />
          <span>Active Quantitative Virtual Strategies in Registry</span>
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {strategies.map((st) => (
            <div key={st.code} className="bg-slate-50 rounded-xl p-4 border border-slate-200/80 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between">
                  <span className={`px-2 py-0.5 rounded-md text-[10px] font-black ${
                    st.status === "QUALIFIED" ? "bg-emerald-100 text-emerald-800" : st.status === "PAPER" ? "bg-indigo-100 text-indigo-800" : "bg-slate-200 text-slate-700"
                  }`}>
                    {st.status}
                  </span>
                  <span className="text-[10px] font-bold text-slate-400 font-mono">{st.current_version}</span>
                </div>
                <h5 className="text-xs font-black text-slate-900 mt-2">{st.name}</h5>
                <p className="text-[11px] text-slate-500 mt-1 font-medium leading-normal">{st.description}</p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-200 text-[10px] text-slate-500 flex justify-between font-mono">
                <span>Min Edge: <strong>+{roundPct(st.min_edge_threshold)}%</strong></span>
                <span>Target: <strong>{st.target_market}</strong></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function roundPct(val) {
  if (val === null || val === undefined) return 0;
  return Math.round(val * 1000) / 10;
}

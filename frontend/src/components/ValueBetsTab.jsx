import React, { useState, useEffect } from "react";
import { fetchValueOpportunities } from "../api/client";
import { TrendingUp, Copy } from "lucide-react";

export default function ValueBetsTab() {
  const [opportunities, setOpportunities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadOpportunities();
  }, []);

  const loadOpportunities = async () => {
    setLoading(true);
    const data = await fetchValueOpportunities(0.03, 0.05);
    setOpportunities(data.opportunities || []);
    setLoading(false);
  };

  return (
    <div className="space-y-6">
      {/* Title Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200">
        <h2 className="text-xl font-extrabold text-slate-900">
          Value Bets (+EV Opportunities)
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Matches where MatchIQ model probabilities are significantly higher than bookmaker odds.
        </p>
      </div>

      {/* Cards Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div key={n} className="bg-white p-6 rounded-2xl border border-slate-200 animate-pulse h-48" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {opportunities.map((item, idx) => (
            <div key={idx} className="card-clean-hover p-6 rounded-2xl flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                  <span className="font-bold text-slate-700">
                    {item.home_team} vs {item.away_team}
                  </span>
                  <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-semibold">
                    {item.bookmaker || "SportyBet"}
                  </span>
                </div>

                <div className="my-3">
                  <span className="text-[11px] text-slate-400 block font-medium uppercase">
                    Recommended Market
                  </span>
                  <span className="text-base font-extrabold text-slate-900">
                    {item.selection}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 bg-slate-50 p-3 rounded-xl text-center text-xs my-3">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Bookmaker Odds</span>
                    <span className="font-extrabold text-slate-900">{item.odds?.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">AI Win Chance</span>
                    <span className="font-extrabold text-indigo-600">{(item.model_probability * 100).toFixed(0)}%</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">Model Edge</span>
                    <span className="font-extrabold text-emerald-600">+{(item.model_edge * 100).toFixed(1)}%</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-100 text-xs">
                <span className="font-extrabold text-emerald-600 flex items-center space-x-1">
                  <TrendingUp className="w-4 h-4" />
                  <span>+{(item.expected_value * 100).toFixed(1)}% Expected Value</span>
                </span>

                <button
                  onClick={() => navigator.clipboard.writeText(item.selection)}
                  className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs transition-all cursor-pointer"
                >
                  Copy Pick
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

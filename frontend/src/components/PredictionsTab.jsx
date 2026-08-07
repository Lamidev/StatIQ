import React, { useState, useEffect } from "react";
import { fetchLivePredictions } from "../api/client";
import { Search, Calendar } from "lucide-react";

export default function PredictionsTab() {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedComp, setSelectedComp] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const competitions = [
    { code: "ALL", name: "All Leagues" },
    { code: "PL", name: "Premier League" },
    { code: "PD", name: "La Liga" },
    { code: "SA", name: "Serie A" },
    { code: "BL1", name: "Bundesliga" },
    { code: "FL1", name: "Ligue 1" },
    { code: "CL", name: "Champions League" },
  ];

  useEffect(() => {
    loadPredictions();
  }, []);

  const loadPredictions = async () => {
    setLoading(true);
    const data = await fetchLivePredictions("PENDING", 60);
    setPredictions(data.predictions || []);
    setLoading(false);
  };

  const filteredPredictions = predictions.filter((p) => {
    const homeName = p.home_team || `Team ${p.home_team_id}`;
    const awayName = p.away_team || `Team ${p.away_team_id}`;
    
    const compCode = (p.competition || p.competition_code || "").toString().toUpperCase();
    const compName = (p.competition_name || "").toString().toUpperCase();

    const matchComp =
      selectedComp === "ALL" ||
      compCode === selectedComp.toUpperCase() ||
      compName.includes(selectedComp.toUpperCase());

    const matchSearch =
      searchQuery === "" ||
      homeName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      awayName.toLowerCase().includes(searchQuery.toLowerCase());

    return matchComp && matchSearch;
  });

  return (
    <div className="space-y-6">
      {/* Title Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900">
            Upcoming Match Predictions
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            AI probability distributions calculated before kickoff for upcoming matches.
          </p>
        </div>

        <button
          onClick={loadPredictions}
          className="px-4 py-2 rounded-xl btn-black text-xs self-start sm:self-auto"
        >
          Refresh Games
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex items-center space-x-2 overflow-x-auto w-full sm:w-auto py-1">
          {competitions.map((c) => (
            <button
              key={c.code}
              onClick={() => setSelectedComp(c.code)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                selectedComp === c.code
                  ? "bg-slate-900 text-white"
                  : "bg-white text-slate-600 border border-slate-200 hover:bg-slate-50"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search teams (e.g. Real Madrid)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-white border border-slate-200 rounded-xl pl-9 pr-4 py-1.5 text-xs text-slate-900 focus:outline-none focus:border-slate-400"
          />
        </div>
      </div>

      {/* Match Cards Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((n) => (
            <div key={n} className="bg-white p-6 rounded-2xl border border-slate-200 animate-pulse h-56" />
          ))}
        </div>
      ) : filteredPredictions.length === 0 ? (
        <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center">
          <h3 className="text-base font-bold text-slate-800">No predictions found for this filter</h3>
          <p className="text-xs text-slate-500 mt-1">Try selecting "All Leagues" or clear your search term.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredPredictions.map((pred, idx) => {
            const homeName = pred.home_team || `Team ${pred.home_team_id}`;
            const awayName = pred.away_team || `Team ${pred.away_team_id}`;

            const pHome = Math.round(pred.prob_home * 100);
            const pDraw = Math.round(pred.prob_draw * 100);
            const pAway = Math.round(pred.prob_away * 100);

            const pOver15 = Math.round((pred.prob_over_1_5 || 0.75) * 100);
            const pOver25 = Math.round((pred.prob_over_2_5 || 0.52) * 100);
            const pBtts = Math.round((pred.prob_btts_yes || 0.55) * 100);

            return (
              <div key={idx} className="card-clean-hover p-6 rounded-2xl flex flex-col justify-between">
                <div>
                  {/* Top Bar */}
                  <div className="flex items-center justify-between text-xs text-slate-400 mb-3">
                    <span className="font-bold text-slate-700 bg-slate-100 px-2.5 py-0.5 rounded uppercase">
                      {pred.competition_name || pred.competition || "League"}
                    </span>
                    <div className="flex items-center space-x-1">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" />
                      <span>{new Date(pred.kickoff_datetime).toLocaleDateString()}</span>
                    </div>
                  </div>

                  {/* Teams Matchup */}
                  <div className="my-4">
                    <div className="text-base font-extrabold text-slate-900 flex items-center justify-between">
                      <span>{homeName}</span>
                      <span className="text-xs text-slate-400 font-normal">vs</span>
                      <span>{awayName}</span>
                    </div>
                  </div>

                  {/* 1X2 Probabilities */}
                  <div className="space-y-1.5 my-4">
                    <div className="flex justify-between text-xs font-semibold text-slate-700">
                      <span>Home Win: <strong>{pHome}%</strong></span>
                      <span>Draw: <strong>{pDraw}%</strong></span>
                      <span>Away Win: <strong>{pAway}%</strong></span>
                    </div>

                    <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden flex">
                      <div style={{ width: `${pHome}%` }} className="bg-emerald-500 h-full" />
                      <div style={{ width: `${pDraw}%` }} className="bg-slate-400 h-full" />
                      <div style={{ width: `${pAway}%` }} className="bg-indigo-500 h-full" />
                    </div>
                  </div>
                </div>

                {/* Additional Markets */}
                <div className="grid grid-cols-3 gap-2 pt-3 border-t border-slate-100 text-center text-xs">
                  <div className="bg-slate-50 p-2 rounded-lg">
                    <span className="text-[10px] text-slate-400 block font-medium">Over 1.5</span>
                    <span className="font-bold text-slate-900">{pOver15}%</span>
                  </div>
                  <div className="bg-slate-50 p-2 rounded-lg">
                    <span className="text-[10px] text-slate-400 block font-medium">Over 2.5</span>
                    <span className="font-bold text-slate-900">{pOver25}%</span>
                  </div>
                  <div className="bg-slate-50 p-2 rounded-lg">
                    <span className="text-[10px] text-slate-400 block font-medium">BTTS</span>
                    <span className="font-bold text-slate-900">{pBtts}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

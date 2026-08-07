import React, { useState, useEffect, useCallback } from "react";
import { fetchFixturesByGameweek, fetchAvailableMatchdays, fetchCrossLeagueGameweek } from "../api/client";
import { Search, Calendar, RefreshCw, Wifi, WifiOff, Sparkles, Trophy, CheckCircle2, Shield } from "lucide-react";
import LeagueGameweekSidebar from "./LeagueGameweekSidebar";

function formatKickoff(iso) {
  if (!iso) return "TBC";
  const d = new Date(iso);
  const datePart = d.toLocaleDateString("en-GB", {
    weekday: "short", day: "2-digit", month: "short"
  });
  const timePart = d.toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit"
  });
  return `${datePart} • ${timePart}`;
}

const formatProb = (val, fallback = 33) => {
  if (val === undefined || val === null) return fallback;
  const n = parseFloat(val);
  if (isNaN(n)) return fallback;
  return n <= 1.0 ? Math.round(n * 100) : Math.round(n);
};

export default function GameweekFixturesTab() {
  const [selectedLeague, setSelectedLeague] = useState("ALL_TOP");
  const [selectedGameweek, setSelectedGameweek] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");

  const [fixtures, setFixtures] = useState([]);
  const [leagueInfo, setLeagueInfo] = useState({ current_matchday: 1, total_matchdays: 38 });
  const [dataSource, setDataSource] = useState("loading"); // "live" | "error" | "loading"
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Load league info when selected league changes
  useEffect(() => {
    if (selectedLeague === "ALL_TOP") {
      setLeagueInfo({ current_matchday: 1, total_matchdays: 38, competition_name: "All Top & Safest Fixtures" });
      return;
    }
    fetchAvailableMatchdays(selectedLeague).then(data => {
      setLeagueInfo({
        current_matchday: data.current_matchday || 1,
        total_matchdays: data.total_matchdays || 38,
        competition_name: data.competition_name,
        season: data.season,
      });
      if (data.current_matchday) {
        setSelectedGameweek(data.current_matchday);
      }
    }).catch(() => {});
  }, [selectedLeague]);

  // Load fixtures for selected league and gameweek
  const loadFixtures = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setDataSource("loading");

    try {
      let result;
      if (selectedLeague === "ALL_TOP") {
        result = await fetchCrossLeagueGameweek(selectedGameweek, 25);
      } else {
        result = await fetchFixturesByGameweek(selectedLeague, selectedGameweek);
      }

      if (result.source === "error") {
        setDataSource("error");
        setError(result.detail || "Could not reach the backend server.");
        setFixtures([]);
      } else {
        setFixtures(result.fixtures || []);
        setDataSource("live");
        setLastUpdated(new Date());
      }
    } catch (err) {
      setDataSource("error");
      setError(err.message);
      setFixtures([]);
    } finally {
      setIsLoading(false);
    }
  }, [selectedLeague, selectedGameweek]);

  useEffect(() => {
    loadFixtures();
  }, [loadFixtures]);

  const filteredFixtures = fixtures.filter(f =>
    searchQuery === "" ||
    f.home_team?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    f.away_team?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Banner */}
      <div className="bg-slate-900 text-white p-6 rounded-2xl shadow-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Trophy className="w-5 h-5 text-emerald-400" />
            <h1 className="text-xl font-extrabold tracking-tight">Match Fixtures & Live AI Analytics</h1>
          </div>
          <p className="text-xs text-slate-400">
            Real-time fixtures across top European and International leagues with StatIQ Elo rating probabilities.
          </p>
        </div>

        <button
          onClick={loadFixtures}
          disabled={isLoading}
          className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all border border-slate-700 shadow-sm disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          <span>Sync Fixtures</span>
        </button>
      </div>

      {/* Main Grid: Sidebar Left + Fixture List Right */}
      <div className="flex flex-col lg:flex-row items-start gap-6">
        {/* Vertical Grouped Sidebar */}
        <LeagueGameweekSidebar
          selectedLeague={selectedLeague}
          onSelectLeague={(code) => {
            setSelectedLeague(code);
            setSearchQuery("");
          }}
          selectedGw={selectedGameweek}
          onSelectGw={(gw) => setSelectedGameweek(gw)}
          totalGws={leagueInfo.total_matchdays || 38}
        />

        {/* Fixture Content Panel */}
        <div className="flex-1 w-full space-y-4">
          {/* Search & Filter Header Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">
                {leagueInfo.competition_name || "StatIQ"} — Gameweek {selectedGameweek}
              </span>
              <span className="bg-slate-100 text-slate-700 text-[10px] font-mono font-extrabold px-2 py-0.5 rounded-full">
                {filteredFixtures.length} Matches
              </span>
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search team name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-4 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
              />
            </div>
          </div>

          {/* Loading Indicator */}
          {isLoading && (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
              <RefreshCw className="w-6 h-6 text-slate-400 animate-spin mx-auto" />
              <p className="text-xs font-bold text-slate-500">Fetching live fixtures from football-data.org...</p>
            </div>
          )}

          {/* Error Indicator */}
          {!isLoading && dataSource === "error" && (
            <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 text-rose-900 space-y-2">
              <div className="flex items-center gap-2 font-extrabold text-sm">
                <WifiOff className="w-4 h-4 text-rose-600" />
                <span>Could not load fixtures</span>
              </div>
              <p className="text-xs text-rose-700">{error}</p>
            </div>
          )}

          {/* Empty Search Result */}
          {!isLoading && dataSource !== "error" && filteredFixtures.length === 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center text-slate-400 space-y-2">
              <p className="text-xs font-extrabold text-slate-600">No matches found for GW{selectedGameweek}</p>
              <p className="text-[11px]">Try selecting another Gameweek or clearing your search term.</p>
            </div>
          )}

          {/* Fixture Cards List */}
          {!isLoading && filteredFixtures.length > 0 && (
            <div className="space-y-3">
              {filteredFixtures.map((f) => {
                const homeProb = formatProb(f.ai_prob_home, 45);
                const drawProb = formatProb(f.ai_prob_draw, 25);
                const awayProb = formatProb(f.ai_prob_away, 30);
                const isFinished = f.status === "FINISHED";

                return (
                  <div
                    key={f.fixture_id || f.external_id}
                    className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-all space-y-3"
                  >
                    {/* Fixture Header: Kickoff Date & Status */}
                    <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                      <div className="flex items-center gap-2">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span className="text-xs font-semibold text-slate-600">
                          {formatKickoff(f.kickoff_datetime)}
                        </span>
                      </div>

                      {isFinished ? (
                        <span className="bg-slate-100 text-slate-700 text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full">
                          Finished
                        </span>
                      ) : (
                        <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-extrabold uppercase px-2.5 py-0.5 rounded-full flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                          Upcoming
                        </span>
                      )}
                    </div>

                    {/* Teams & Score / Odds Grid */}
                    <div className="grid grid-cols-12 items-center gap-4 py-1">
                      {/* Home Team */}
                      <div className="col-span-4 flex items-center justify-end gap-3 text-right">
                        <div>
                          <span className="text-sm font-black text-slate-900 block leading-tight">
                            {f.home_team}
                          </span>
                          <span className="text-[10px] text-slate-400 font-semibold">
                            Elo {f.home_elo || 1670}
                          </span>
                        </div>
                        {f.home_crest ? (
                          <img src={f.home_crest} alt={f.home_team} className="w-8 h-8 object-contain flex-shrink-0" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-xs font-extrabold text-slate-600 flex-shrink-0">
                            {f.home_team?.slice(0, 2).toUpperCase()}
                          </div>
                        )}
                      </div>

                      {/* Score or VS Badge */}
                      <div className="col-span-4 text-center">
                        {isFinished ? (
                          <div className="bg-slate-900 text-white px-3 py-1.5 rounded-xl font-mono text-base font-black inline-block">
                            {f.home_score} : {f.away_score}
                          </div>
                        ) : (
                          <span className="text-xs font-black text-slate-400 uppercase bg-slate-100 px-3 py-1 rounded-full">
                            VS
                          </span>
                        )}
                      </div>

                      {/* Away Team */}
                      <div className="col-span-4 flex items-center justify-start gap-3 text-left">
                        {f.away_crest ? (
                          <img src={f.away_crest} alt={f.away_team} className="w-8 h-8 object-contain flex-shrink-0" />
                        ) : (
                          <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-xs font-extrabold text-slate-600 flex-shrink-0">
                            {f.away_team?.slice(0, 2).toUpperCase()}
                          </div>
                        )}
                        <div>
                          <span className="text-sm font-black text-slate-900 block leading-tight">
                            {f.away_team}
                          </span>
                          <span className="text-[10px] text-slate-400 font-semibold">
                            Elo {f.away_elo || 1670}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* StatIQ Probability Meter */}
                    <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between text-[11px] font-extrabold">
                        <span className="text-emerald-700">1 ({homeProb}%)</span>
                        <span className="text-slate-500">X ({drawProb}%)</span>
                        <span className="text-blue-700">2 ({awayProb}%)</span>
                      </div>

                      <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden flex">
                        <div style={{ width: `${homeProb}%` }} className="bg-emerald-500 h-full" />
                        <div style={{ width: `${drawProb}%` }} className="bg-slate-400 h-full" />
                        <div style={{ width: `${awayProb}%` }} className="bg-blue-500 h-full" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

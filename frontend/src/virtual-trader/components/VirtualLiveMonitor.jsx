import React, { useState, useEffect } from "react";
import { Clock, RefreshCw, Trophy, AlertCircle } from "lucide-react";
import { fetchVirtualEvents, fetchVirtualLeagues } from "../api/virtualClient";

export default function VirtualLiveMonitor() {
  const [events, setEvents] = useState([]);
  const [leagues, setLeagues] = useState([]);
  const [selectedLeagueId, setSelectedLeagueId] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [eventsRes, leaguesRes] = await Promise.all([
        fetchVirtualEvents(50, selectedLeagueId),
        fetchVirtualLeagues()
      ]);
      setEvents(eventsRes?.events || []);
      setLeagues(leaguesRes?.leagues || []);
    } catch (err) {
      console.error("Failed to load virtual monitor data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [selectedLeagueId]);

  return (
    <div className="space-y-4">
      {/* League Filter Header */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <Trophy className="w-4 h-4 text-indigo-600" />
          <span className="text-xs font-black uppercase tracking-wider text-slate-700">Filter Virtual League:</span>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setSelectedLeagueId(null)}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              selectedLeagueId === null
                ? "bg-slate-900 text-white shadow-2xs"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All Leagues
          </button>
          {leagues.map((lg) => (
            <button
              key={lg.id}
              onClick={() => setSelectedLeagueId(lg.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
                selectedLeagueId === lg.id
                  ? "bg-slate-900 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {lg.name} ({lg.total_events_collected || 0})
            </button>
          ))}
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition-all self-end sm:self-auto cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-indigo-600" : ""}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Events Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-sm font-black text-slate-900 tracking-tight flex items-center space-x-2">
            <Clock className="w-4 h-4 text-emerald-600" />
            <span>Active Virtual Match Stream & Live Odds Snapshot</span>
          </h3>
          <span className="text-xs font-bold text-slate-500">{events.length} upcoming matches</span>
        </div>

        {events.length === 0 ? (
          <div className="py-16 text-center text-slate-500">
            <AlertCircle className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <p className="text-xs font-bold">No active virtual matches found currently.</p>
            <p className="text-[11px] text-slate-400 mt-1">
              The Virtual Ingestion Worker is polling SportyBet factsCenter for the next upcoming round.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100 text-slate-500 uppercase tracking-wider font-extrabold text-[10px]">
                  <th className="py-3 px-4">Event ID</th>
                  <th className="py-3 px-4">League</th>
                  <th className="py-3 px-4">Scheduled Kickoff</th>
                  <th className="py-3 px-4">Matchup</th>
                  <th className="py-3 px-4 text-center">1 (Home)</th>
                  <th className="py-3 px-4 text-center">X (Draw)</th>
                  <th className="py-3 px-4 text-center">2 (Away)</th>
                  <th className="py-3 px-4 text-center">Over Line</th>
                  <th className="py-3 px-4 text-center">Under Line</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {events.map((ev) => {
                  const odds = ev.latest_odds || {};
                  return (
                    <tr key={ev.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-bold text-slate-600">
                        #{ev.provider_event_id}
                      </td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-bold text-[11px]">
                          {ev.league_name}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-700">
                        {ev.scheduled_time ? new Date(ev.scheduled_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Upcoming"}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center space-x-2 font-bold text-slate-900">
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 text-[11px]">{ev.home_team}</span>
                          <span className="text-slate-400 font-semibold text-[10px]">vs</span>
                          <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-800 text-[11px]">{ev.away_team}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-slate-900">
                        {odds.odds_home ? (
                          <span className="px-2 py-1 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200/60 font-mono">
                            {odds.odds_home.toFixed(2)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-slate-900">
                        {odds.odds_draw ? (
                          <span className="px-2 py-1 rounded-lg bg-slate-100 text-slate-800 font-mono">
                            {odds.odds_draw.toFixed(2)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-slate-900">
                        {odds.odds_away ? (
                          <span className="px-2 py-1 rounded-lg bg-indigo-50 text-indigo-800 border border-indigo-200/60 font-mono">
                            {odds.odds_away.toFixed(2)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-slate-900">
                        {odds.odds_over ? (
                          <span className="px-2 py-1 rounded-lg bg-amber-50 text-amber-800 font-mono">
                            {odds.odds_over.toFixed(2)}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="py-3 px-4 text-center font-bold text-slate-900">
                        {odds.odds_under ? (
                          <span className="px-2 py-1 rounded-lg bg-slate-100 text-slate-800 font-mono">
                            {odds.odds_under.toFixed(2)}
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

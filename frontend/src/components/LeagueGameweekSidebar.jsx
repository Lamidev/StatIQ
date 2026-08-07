import React from "react";
import { Trophy, Calendar, Check, AlertCircle, Sparkles, Globe } from "lucide-react";

export const LEAGUE_GROUPS = [
  {
    region: "England",
    flag: "🇬🇧",
    leagues: [
      { code: "PL", name: "Premier League", tag: "ENG", icon: "⚽" },
      { code: "ELC", name: "Championship", tag: "ENG", icon: "⚽" },
    ]
  },
  {
    region: "Spain",
    flag: "🇪🇸",
    leagues: [
      { code: "PD", name: "La Liga", tag: "ESP", icon: "🇪🇸" },
    ]
  },
  {
    region: "Italy",
    flag: "🇮🇹",
    leagues: [
      { code: "SA", name: "Serie A", tag: "ITA", icon: "🇮🇹" },
    ]
  },
  {
    region: "Germany",
    flag: "🇩🇪",
    leagues: [
      { code: "BL1", name: "Bundesliga", tag: "GER", icon: "🇩🇪" },
    ]
  },
  {
    region: "France",
    flag: "🇫🇷",
    leagues: [
      { code: "FL1", name: "Ligue 1", tag: "FRA", icon: "🇫🇷" },
    ]
  },
  {
    region: "Netherlands",
    flag: "🇳🇱",
    leagues: [
      { code: "DED", name: "Eredivisie", tag: "NED", icon: "🇳🇱" },
    ]
  },
  {
    region: "Portugal",
    flag: "🇵🇹",
    leagues: [
      { code: "PPL", name: "Primeira Liga", tag: "POR", icon: "🇵🇹" },
    ]
  },
  {
    region: "Europe",
    flag: "🇪🇺",
    leagues: [
      { code: "CL", name: "Champions League", tag: "UEFA", icon: "🏆" },
    ]
  },
  {
    region: "South America",
    flag: "🌎",
    leagues: [
      { code: "CLI", name: "Copa Libertadores", tag: "SAM", icon: "🌎" },
      { code: "BSA", name: "Brasileirão Série A", tag: "BRA", icon: "🇧🇷" },
    ]
  },
  {
    region: "International",
    flag: "🌐",
    leagues: [
      { code: "WC", name: "FIFA World Cup 2026", tag: "INT", icon: "🌐" },
    ]
  }
];

export default function LeagueGameweekSidebar({
  selectedLeague,
  onSelectLeague,
  selectedGw,
  onSelectGw,
  totalGws = 38
}) {
  return (
    <div className="w-full lg:w-72 bg-white rounded-2xl border border-slate-200 shadow-sm p-4 space-y-6 flex-shrink-0">
      {/* Sidebar Header */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-emerald-600" />
          <h2 className="text-sm font-extrabold text-slate-900 tracking-tight">
            League Selector
          </h2>
        </div>
        <span className="text-[10px] font-extrabold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
          Live API
        </span>
      </div>

      {/* Top Option: All Games */}
      <button
        onClick={() => onSelectLeague("ALL_TOP")}
        className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-bold transition-all text-left ${
          selectedLeague === "ALL_TOP"
            ? "bg-slate-900 text-white shadow-sm font-extrabold"
            : "text-slate-700 hover:bg-slate-100 hover:text-slate-900 border border-slate-100"
        }`}
      >
        <div className="flex items-center gap-2 truncate">
          <span>⚽</span>
          <span className="truncate">All Games</span>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-extrabold uppercase ${
              selectedLeague === "ALL_TOP" ? "bg-slate-800 text-emerald-400" : "bg-slate-100 text-slate-500"
            }`}
          >
            ALL
          </span>
          {selectedLeague === "ALL_TOP" && <Check className="w-3.5 h-3.5 text-emerald-400" />}
        </div>
      </button>

      {/* Vertical Grouped Leagues */}
      <div className="space-y-4 max-h-[460px] overflow-y-auto pr-1 text-xs">
        {LEAGUE_GROUPS.map((group) => (
          <div key={group.region} className="space-y-1">
            <div className="flex items-center gap-1.5 px-2 py-1 text-[11px] font-extrabold text-slate-400 uppercase tracking-wider">
              <span>{group.flag}</span>
              <span>{group.region}</span>
            </div>

            <div className="space-y-1 pl-1">
              {group.leagues.map((league) => {
                const isSelected = selectedLeague === league.code;
                return (
                  <button
                    key={league.code}
                    onClick={() => onSelectLeague(league.code)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-bold transition-all text-left ${
                      isSelected
                        ? "bg-slate-900 text-white shadow-sm font-extrabold"
                        : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span>{league.icon}</span>
                      <span className="truncate">{league.name}</span>
                    </div>

                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <span
                        className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-extrabold uppercase ${
                          isSelected ? "bg-slate-800 text-emerald-400" : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {league.tag}
                      </span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-emerald-400" />}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Subscription Tier Info Box */}
      <div className="bg-amber-50 border border-amber-200/80 rounded-xl p-3 text-[11px] text-amber-900 space-y-1">
        <div className="flex items-center gap-1.5 font-extrabold text-amber-800">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>API Subscription Tier Note</span>
        </div>
        <p className="text-[10px] text-amber-700 leading-tight">
          Not available: Turkish Süper Lig, Scottish Premiership, Europa League — not on this API subscription tier.
        </p>
      </div>

      {/* Gameweek Selector */}
      <div className="border-t border-slate-100 pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Calendar className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-xs font-extrabold text-slate-900">Select Gameweek</span>
          </div>
          <span className="text-[10px] font-bold text-slate-400">Current: GW{selectedGw}</span>
        </div>

        {/* Dynamic GW Grid Pills */}
        <div className="grid grid-cols-5 gap-1.5 max-h-36 overflow-y-auto p-1 bg-slate-50 rounded-xl border border-slate-100">
          {Array.from({ length: totalGws }, (_, i) => i + 1).map((gw) => {
            const isGwSelected = selectedGw === gw;
            return (
              <button
                key={gw}
                onClick={() => onSelectGw(gw)}
                className={`py-1 text-[11px] font-extrabold rounded-lg transition-all text-center ${
                  isGwSelected
                    ? "bg-emerald-600 text-white shadow-sm scale-105"
                    : "bg-white text-slate-700 hover:bg-slate-200 border border-slate-200/60"
                }`}
              >
                GW{gw}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

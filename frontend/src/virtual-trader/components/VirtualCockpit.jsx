import React, { useState, useEffect, useCallback } from "react";
import {
  Power, RefreshCw, Ticket, Copy, CheckCircle, ExternalLink,
  TrendingUp, ChevronDown, ChevronUp, Settings, Zap, AlertCircle
} from "lucide-react";
import { fetchLiveVFootball, generateLiveTicket, updateAgentConfig, fetchAgentState } from "../api/virtualClient";

const LEAGUE_FLAGS = {
  England: "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
  Spain: "🇪🇸",
  Italy: "🇮🇹",
  Germany: "🇩🇪",
  France: "🇫🇷",
  Turkey: "🇹🇷",
};

function OddBtn({ label, value, isSelected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
        isSelected
          ? "bg-emerald-500 text-white border-emerald-500 shadow-sm"
          : "bg-slate-50 text-slate-700 border-slate-200 hover:border-emerald-400 hover:bg-emerald-50"
      }`}
    >
      <span className="text-[10px] font-medium text-inherit opacity-70 mb-0.5">{label}</span>
      <span>{value ?? "—"}</span>
    </button>
  );
}

function MatchRow({ fixture, onSelectionToggle, selections }) {
  const [showMore, setShowMore] = useState(false);
  const odds = fixture.odds_1x2 || {};
  const ouList = fixture.odds_ou || [];
  const mainOU = ouList.find(o => o.line === "2.5") || ouList[0];

  const isSelected = (pick) => selections.some(s => s.game_id === fixture.game_id && s.pick_code === pick);

  return (
    <div className="border border-slate-100 rounded-xl bg-white hover:border-slate-200 transition-all">
      {/* Match header */}
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-slate-400">ID:{fixture.game_id}</span>
          <span className="text-xs font-bold text-slate-800">{fixture.home_team}</span>
          <span className="text-[10px] text-slate-400 font-medium">vs</span>
          <span className="text-xs font-bold text-slate-800">{fixture.away_team}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
            {fixture.kick_off_display}
          </span>
          <button
            onClick={() => setShowMore(!showMore)}
            className="text-slate-400 hover:text-slate-600 transition-colors"
          >
            {showMore ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {/* Main odds row */}
      <div className="flex items-center gap-1.5 px-3 pb-2.5">
        {/* 1X2 */}
        <div className="flex gap-1">
          <OddBtn label="1" value={odds.home} isSelected={isSelected("1")}
            onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `${fixture.home_team} Win`, pick_code: "1", odds: parseFloat(odds.home) })} />
          <OddBtn label="X" value={odds.draw} isSelected={isSelected("X")}
            onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: "Draw", pick_code: "X", odds: parseFloat(odds.draw) })} />
          <OddBtn label="2" value={odds.away} isSelected={isSelected("2")}
            onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `${fixture.away_team} Win`, pick_code: "2", odds: parseFloat(odds.away) })} />
        </div>

        {/* O/U */}
        {mainOU && (
          <div className="flex gap-1 ml-1">
            <div className="text-[10px] text-slate-400 self-center font-medium">{mainOU.line}</div>
            <OddBtn label="Ov" value={mainOU.over} isSelected={isSelected(`over_${mainOU.line}`)}
              onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `Over ${mainOU.line}`, pick_code: `over_${mainOU.line}`, odds: parseFloat(mainOU.over) })} />
            <OddBtn label="Un" value={mainOU.under} isSelected={isSelected(`under_${mainOU.line}`)}
              onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `Under ${mainOU.line}`, pick_code: `under_${mainOU.line}`, odds: parseFloat(mainOU.under) })} />
          </div>
        )}

        {/* Extra markets count */}
        {fixture.market_count > 3 && (
          <span className="ml-auto text-[10px] text-slate-400 font-medium">+{fixture.market_count - 3}</span>
        )}
      </div>

      {/* More O/U lines */}
      {showMore && ouList.length > 1 && (
        <div className="px-3 pb-2.5 flex flex-wrap gap-1 border-t border-slate-50 pt-2">
          {ouList.map(ou => ou.line !== mainOU?.line && (
            <div key={ou.line} className="flex items-center gap-1">
              <span className="text-[10px] text-slate-400">{ou.line}:</span>
              <OddBtn label="Ov" value={ou.over} isSelected={isSelected(`over_${ou.line}`)}
                onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `Over ${ou.line}`, pick_code: `over_${ou.line}`, odds: parseFloat(ou.over) })} />
              <OddBtn label="Un" value={ou.under} isSelected={isSelected(`under_${ou.line}`)}
                onClick={() => onSelectionToggle({ game_id: fixture.game_id, league: fixture.league, match: `${fixture.home_team} vs ${fixture.away_team}`, pick: `Under ${ou.line}`, pick_code: `under_${ou.line}`, odds: parseFloat(ou.under) })} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LeagueBlock({ leagueName, fixtures, onSelectionToggle, selections }) {
  const [collapsed, setCollapsed] = useState(false);
  const flag = LEAGUE_FLAGS[leagueName] || "⚽";
  const kickoff = fixtures[0]?.kick_off_display || "--:--";

  return (
    <div className="mb-4">
      <button
        className="w-full flex items-center justify-between px-3 py-2 bg-slate-800 text-white rounded-xl mb-2 hover:bg-slate-700 transition-colors"
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-2">
          <span className="text-base">{flag}</span>
          <span className="text-sm font-bold">{leagueName} Virtual</span>
          <span className="text-[10px] text-slate-300 bg-slate-700 px-2 py-0.5 rounded-full">{kickoff}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">{fixtures.length} matches</span>
          {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
        </div>
      </button>

      {!collapsed && (
        <div className="space-y-1.5 pl-1">
          {fixtures.map(f => (
            <MatchRow key={f.game_id} fixture={f} onSelectionToggle={onSelectionToggle} selections={selections} />
          ))}
        </div>
      )}
    </div>
  );
}

function TicketPanel({ selections, onClear, stake, setStake }) {
  const [copied, setCopied] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [ticket, setTicket] = useState(null);

  const totalOdds = selections.reduce((acc, s) => acc * s.odds, 1);
  const potReturn = (stake * totalOdds).toFixed(2);
  const profit = (potReturn - stake).toFixed(2);

  const handleCopy = () => {
    if (ticket?.booking_code) {
      navigator.clipboard.writeText(ticket.booking_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleGenerateFromSelections = async () => {
    setGenerating(true);
    // Here we just use the manual selections as the "ticket"
    const t = {
      selections,
      total_odds: totalOdds.toFixed(2),
      stake_ngn: stake,
      potential_return_ngn: potReturn,
      profit_ngn: profit,
      booking_code: "LOAD-ON-SPORTYBET",
      sportybet_url: "https://www.sportybet.com/ng/sport/vFootball/",
    };
    setTicket(t);
    setGenerating(false);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4 sticky top-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-slate-800 flex items-center gap-2">
          <Ticket size={16} className="text-emerald-500" />
          Bet Slip
        </h3>
        {selections.length > 0 && (
          <button onClick={onClear} className="text-xs text-red-500 hover:text-red-700 font-medium">Clear</button>
        )}
      </div>

      {selections.length === 0 ? (
        <div className="text-center py-6 text-slate-400">
          <Ticket size={24} className="mx-auto mb-2 opacity-30" />
          <p className="text-xs">Click odds to add selections</p>
        </div>
      ) : (
        <>
          <div className="space-y-2 mb-3 max-h-48 overflow-y-auto">
            {selections.map((s, i) => (
              <div key={i} className="bg-slate-50 rounded-lg p-2">
                <div className="text-[10px] text-slate-500 truncate">{s.league}</div>
                <div className="text-xs font-semibold text-slate-700 truncate">{s.match}</div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="text-[11px] text-emerald-600 font-bold">{s.pick}</span>
                  <span className="text-xs font-bold text-slate-800">{s.odds}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Odds summary */}
          <div className="bg-slate-900 text-white rounded-xl p-3 mb-3 text-sm">
            <div className="flex justify-between mb-1">
              <span className="text-slate-400 text-xs">{selections.length} selection{selections.length > 1 ? "s" : ""}</span>
              <span className="font-bold text-emerald-400">{totalOdds.toFixed(2)}x</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-slate-400 text-xs">Stake</span>
              <div className="flex-1 flex items-center">
                <span className="text-slate-400 text-xs mr-1">₦</span>
                <input
                  type="number"
                  value={stake}
                  onChange={e => setStake(Number(e.target.value))}
                  className="flex-1 bg-slate-800 text-white text-xs rounded px-2 py-1 w-full"
                  min={100}
                  step={500}
                />
              </div>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-slate-400">Potential</span>
              <span className="font-bold text-white">₦{parseFloat(potReturn).toLocaleString()}</span>
            </div>
            <div className="flex justify-between text-xs mt-0.5">
              <span className="text-slate-400">Profit</span>
              <span className={`font-bold ${profit > 0 ? "text-emerald-400" : "text-red-400"}`}>
                +₦{parseFloat(profit).toLocaleString()}
              </span>
            </div>
          </div>

          <button
            onClick={handleGenerateFromSelections}
            disabled={generating}
            className="w-full bg-emerald-500 hover:bg-emerald-600 text-white font-bold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
          >
            {generating ? <RefreshCw size={14} className="animate-spin" /> : <Ticket size={14} />}
            {generating ? "Generating..." : "Create Ticket"}
          </button>

          {ticket && (
            <div className="mt-3 bg-emerald-50 border border-emerald-200 rounded-xl p-3">
              <div className="text-xs font-bold text-emerald-800 mb-2">Ready to Book</div>
              <div className="flex items-center justify-between bg-white border border-emerald-200 rounded-lg px-3 py-2 mb-2">
                <span className="font-mono font-bold text-slate-900 text-sm tracking-widest">{ticket.booking_code}</span>
                <button onClick={handleCopy} className="text-emerald-500">
                  {copied ? <CheckCircle size={16} /> : <Copy size={16} />}
                </button>
              </div>
              <a
                href={ticket.sportybet_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-1.5 w-full py-2 bg-slate-900 text-white text-xs font-bold rounded-lg hover:bg-slate-700 transition-colors"
              >
                <ExternalLink size={12} />
                Open SportyBet vFootball
              </a>
              <p className="text-[10px] text-slate-500 mt-1.5 text-center">
                Add your selections manually on the SportyBet vFootball page
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function AgentPanel({ onAgentGenerate }) {
  const [active, setActive] = useState(true);
  const [targetOdds, setTargetOdds] = useState(2.0);
  const [numGames, setNumGames] = useState(2);
  const [stake, setStake] = useState(1000);
  const [market, setMarket] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [lastTicket, setLastTicket] = useState(null);
  const [copied, setCopied] = useState(false);

  const markets = ["ALL", "1X2_HOME", "1X2_AWAY", "OVER_1.5", "OVER_2.5", "DOUBLE_CHANCE"];

  const handleGenerate = async () => {
    setLoading(true);
    const res = await generateLiveTicket({ targetOdds, numGames, stakeAmount: stake, market });
    setLoading(false);
    if (res?.status === "SUCCESS") {
      setLastTicket(res.ticket);
      onAgentGenerate?.(res.ticket);
    } else {
      setLastTicket(null);
    }
  };

  const handleCopy = (code) => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4">
      {/* Agent toggle */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Zap size={16} className="text-amber-500" />
          <span className="font-bold text-slate-800 text-sm">Auto-Pick Agent</span>
        </div>
        <button
          onClick={() => setActive(!active)}
          className={`relative w-11 h-6 rounded-full transition-colors ${active ? "bg-emerald-500" : "bg-slate-300"}`}
        >
          <div className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-transform ${active ? "translate-x-6" : "translate-x-1"}`} />
        </button>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <label className="text-[10px] text-slate-500 font-medium mb-1 block">Target Odds</label>
          <input type="number" value={targetOdds} step="0.5" min="1.5" max="20"
            onChange={e => setTargetOdds(Number(e.target.value))}
            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm font-bold text-slate-800" />
        </div>
        <div>
          <label className="text-[10px] text-slate-500 font-medium mb-1 block">Games</label>
          <select value={numGames} onChange={e => setNumGames(Number(e.target.value))}
            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm font-bold text-slate-800">
            {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[10px] text-slate-500 font-medium mb-1 block">Stake (₦)</label>
          <input type="number" value={stake} step="500" min="100"
            onChange={e => setStake(Number(e.target.value))}
            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm font-bold text-slate-800" />
        </div>
        <div>
          <label className="text-[10px] text-slate-500 font-medium mb-1 block">Market</label>
          <select value={market} onChange={e => setMarket(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm font-bold text-slate-800">
            {markets.map(m => <option key={m} value={m}>{m.replace(/_/g, " ")}</option>)}
          </select>
        </div>
      </div>

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="w-full bg-slate-900 hover:bg-slate-700 text-white font-bold py-2.5 rounded-xl text-sm transition-colors flex items-center justify-center gap-2"
      >
        {loading ? <RefreshCw size={14} className="animate-spin" /> : <Zap size={14} />}
        {loading ? "Finding best picks..." : "Auto-Generate Ticket"}
      </button>

      {/* Generated ticket */}
      {lastTicket && (
        <div className="mt-3 bg-slate-50 rounded-xl p-3 border border-slate-200">
          <div className="text-xs font-bold text-slate-700 mb-2 flex items-center gap-1">
            <CheckCircle size={12} className="text-emerald-500" />
            {lastTicket.num_selections || lastTicket.selections?.length} Selections · {lastTicket.total_odds}x
          </div>
          {lastTicket.selections?.map((s, i) => (
            <div key={i} className="text-[10px] text-slate-600 mb-0.5">
              <span className="font-medium">{s.match}</span> → <span className="text-emerald-600 font-bold">{s.pick}</span> @ {s.odds}
            </div>
          ))}
          <div className="flex items-center justify-between mt-2 bg-white rounded-lg p-2 border border-slate-100">
            <div>
              <div className="text-[10px] text-slate-500">Potential Return</div>
              <div className="text-sm font-bold text-emerald-600">₦{parseFloat(lastTicket.potential_return_ngn).toLocaleString()}</div>
            </div>
            <button
              onClick={() => handleCopy(lastTicket.booking_code || "")}
              className="flex items-center gap-1.5 bg-slate-900 text-white text-xs font-bold px-3 py-1.5 rounded-lg"
            >
              {copied ? <CheckCircle size={12} /> : <Copy size={12} />}
              {lastTicket.booking_code}
            </button>
          </div>
          <a href="https://www.sportybet.com/ng/sport/vFootball/" target="_blank" rel="noopener noreferrer"
            className="mt-2 flex items-center justify-center gap-1 text-[10px] text-slate-500 hover:text-slate-700">
            <ExternalLink size={10} /> Open SportyBet vFootball
          </a>
        </div>
      )}
    </div>
  );
}

export default function VirtualCockpit() {
  const [fixtures, setFixtures] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [selections, setSelections] = useState([]);
  const [stake, setStake] = useState(1000);

  const loadFixtures = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLiveVFootball();
      if (data?.leagues) {
        setFixtures(data.leagues);
        setLastRefresh(new Date());
      } else {
        setError("No fixtures available right now");
      }
    } catch (e) {
      setError("Could not connect to vFootball API");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFixtures();
    // Auto-refresh every 2 minutes to catch new rounds
    const interval = setInterval(loadFixtures, 2 * 60 * 1000);
    return () => clearInterval(interval);
  }, [loadFixtures]);

  const handleSelectionToggle = (sel) => {
    setSelections(prev => {
      const exists = prev.findIndex(s => s.game_id === sel.game_id && s.pick_code === sel.pick_code);
      if (exists >= 0) {
        return prev.filter((_, i) => i !== exists);
      }
      // Remove any other selection from same match
      const filtered = prev.filter(s => s.game_id !== sel.game_id);
      return [...filtered, sel];
    });
  };

  const totalMatches = Object.values(fixtures).reduce((a, arr) => a + arr.length, 0);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">⚽ vFootball Live</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {totalMatches > 0
              ? `${totalMatches} fixtures · ${Object.keys(fixtures).length} leagues · Auto-updates every 2 min`
              : "SportyBet Virtual Football — real odds, real gameIds"}
          </p>
        </div>
        <button
          onClick={loadFixtures}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-xl text-xs font-bold text-slate-700 transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {lastRefresh && (
        <p className="text-[10px] text-slate-400">
          Last fetched: {lastRefresh.toLocaleTimeString()} — data from SportyBet vFootball API
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: Fixtures (2/3 width) */}
        <div className="lg:col-span-2 space-y-2">
          {/* Table header */}
          {totalMatches > 0 && (
            <div className="grid grid-cols-[1fr_auto] gap-2 px-3 pb-1">
              <div className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">Match</div>
              <div className="flex gap-6 text-[10px] text-slate-400 font-medium uppercase tracking-wide pr-1">
                <span>1</span><span>X</span><span>2</span>
                <span className="ml-1">Ov</span><span>Un</span>
              </div>
            </div>
          )}

          {loading && (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="h-14 bg-slate-100 animate-pulse rounded-xl" />
              ))}
            </div>
          )}

          {error && !loading && (
            <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
              <AlertCircle size={16} />
              <div>
                <p className="text-sm font-semibold">{error}</p>
                <p className="text-xs mt-0.5">The agent will retry automatically. Check your connection or SportyBet status.</p>
              </div>
            </div>
          )}

          {!loading && !error && totalMatches === 0 && (
            <div className="text-center py-10 text-slate-400">
              <p className="text-sm font-medium">No upcoming vFootball fixtures found</p>
              <p className="text-xs mt-1">Try refreshing — rounds happen every ~30 minutes</p>
            </div>
          )}

          {!loading && Object.entries(fixtures).map(([leagueName, leagueFixtures]) => (
            <LeagueBlock
              key={leagueName}
              leagueName={leagueName}
              fixtures={leagueFixtures}
              onSelectionToggle={handleSelectionToggle}
              selections={selections}
            />
          ))}
        </div>

        {/* Right: Bet Slip + Agent Panel (1/3 width) */}
        <div className="space-y-4">
          <AgentPanel onAgentGenerate={(t) => console.log("Agent generated:", t)} />
          <TicketPanel
            selections={selections}
            onClear={() => setSelections([])}
            stake={stake}
            setStake={setStake}
          />
        </div>
      </div>
    </div>
  );
}

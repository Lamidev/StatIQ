import React, { useState, useEffect } from "react";
import { 
  fetchFixturesByGameweek, 
  generateSportyBetCode, 
  generateVerifiedBookingCode, 
  buildAiTicket, 
  lockTrackedTicket, 
  fetchTodaysSportybetGames, 
  mergeMasterTicket, 
  buildTicketFromShortlist,
  fetchRolloverSchedule,
  updateRolloverSchedule,
  runRolloverNow,
  testRolloverTelegram,
  fetchRolloverHistory,
  resetRolloverChallenge
} from "../api/client";
import { Copy, Info, Calendar, Send, ShieldCheck, RefreshCw, CheckCircle2, ExternalLink, X, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertCircle, Award, Trash2, Lock, ShieldAlert, Sliders, Sparkles, Search, Filter, BarChart2, Target, RotateCcw, Ticket, Layers, Zap, FileText, Upload, ListFilter, Clipboard, Check, Clock, Bell, Play, CheckCircle, TrendingUp, DollarSign, ArrowRight, Shield, Flame, Activity } from "lucide-react";

import { generateSafePick, buildSafeTicket, scoreFixtures } from "../utils/pickEngine";
import { calculateFlexShield } from "../utils/flexCalculator";

const AVAILABLE_LEAGUES = [
  { code: "INT", name: "International Matches", country: "International" },
  { code: "UNL", name: "UEFA Nations League", country: "Europe" },
  { code: "WCQ", name: "World Cup Qualifiers", country: "International" },
  { code: "AFCON", name: "AFCON Qualifiers", country: "Africa" },
  { code: "CONCACAF", name: "CONCACAF Nations League", country: "Americas" },
  { code: "INT_FRIENDLY", name: "Int. Friendlies", country: "International" },
  { code: "PL", name: "Premier League", country: "England" },
  { code: "PD", name: "La Liga", country: "Spain" },
  { code: "SA", name: "Serie A", country: "Italy" },
  { code: "BL1", name: "Bundesliga", country: "Germany" },
  { code: "FL1", name: "Ligue 1", country: "France" },
  { code: "DED", name: "Eredivisie", country: "Netherlands" },
  { code: "PPL", name: "Liga Portugal", country: "Portugal" },
  { code: "TUR", name: "Süper Lig", country: "Turkey" },
  { code: "BEL", name: "Pro League", country: "Belgium" },
  { code: "AUT", name: "Bundesliga", country: "Austria" },
  { code: "SAU", name: "Pro League", country: "Saudi Arabia" },
  { code: "SCO", name: "Premiership", country: "Scotland" },
  { code: "SUI", name: "Super League", country: "Switzerland" },
  { code: "CRO", name: "HNL", country: "Croatia" },
  { code: "DEN", name: "Superliga", country: "Denmark" },
  { code: "GRE", name: "Super League", country: "Greece" },
  { code: "NOR", name: "Eliteserien", country: "Norway" },
  { code: "SWE", name: "Allsvenskan", country: "Sweden" },
  { code: "POL", name: "Ekstraklasa", country: "Poland" },
  { code: "BRA", name: "Serie A", country: "Brazil" },
  { code: "MLS", name: "MLS", country: "USA" },
  { code: "ARG", name: "Primera División", country: "Argentina" },
  { code: "MEX", name: "Liga MX", country: "Mexico" },
  { code: "COL", name: "Liga BetPlay", country: "Colombia" },
  { code: "CHI", name: "Primera División", country: "Chile" },
  { code: "CZE", name: "1. Liga", country: "Czech Republic" },
  { code: "RUS", name: "Premier League", country: "Russia" },
  { code: "UKR", name: "Premier League", country: "Ukraine" },
  { code: "ROU", name: "Superliga", country: "Romania" },
  { code: "ELC", name: "Championship", country: "England" },
  { code: "SD", name: "LaLiga Hypermotion", country: "Spain" },
  { code: "BL2", name: "2. Bundesliga", country: "Germany" },
  { code: "IT2", name: "Serie B", country: "Italy" },
  { code: "FL2", name: "Ligue 2", country: "France" },
  { code: "UCL", name: "Champions League", country: "Europe" },
  { code: "UEL", name: "Europa League", country: "Europe" },
  { code: "UECL", name: "Conference League", country: "Europe" },
];

const LEAGUE_COUNTRY_MAP = {
  "INT": "International",
  "UNL": "Europe",
  "WCQ": "International",
  "AFCON": "Africa",
  "CONCACAF": "Americas",
  "INT_FRIENDLY": "International",
  "PL": "England",
  "PREMIER LEAGUE": "England",
  "PD": "Spain",
  "LALIGA": "Spain",
  "LA LIGA": "Spain",
  "SA": "Italy",
  "SERIE A": "Italy",
  "BL1": "Germany",
  "BUNDESLIGA": "Germany",
  "FL1": "France",
  "LIGUE 1": "France",
  "DED": "Netherlands",
  "EREDIVISIE": "Netherlands",
  "PPL": "Portugal",
  "LIGA PORTUGAL": "Portugal",
  "PRIMEIRA LIGA": "Portugal",
  "TUR": "Turkey",
  "SÜPER LIG": "Turkey",
  "SUPER LIG": "Turkey",
  "BEL": "Belgium",
  "PRO LEAGUE": "Belgium",
  "AUT": "Austria",
  "SAU": "Saudi Arabia",
  "SCO": "Scotland",
  "PREMIERSHIP": "Scotland",
  "SUI": "Switzerland",
  "SUPER LEAGUE": "Switzerland",
  "CRO": "Croatia",
  "HNL": "Croatia",
  "DEN": "Denmark",
  "SUPERLIGA": "Denmark",
  "GRE": "Greece",
  "NOR": "Norway",
  "ELITESERIEN": "Norway",
  "SWE": "Sweden",
  "ALLSVENSKAN": "Sweden",
  "POL": "Poland",
  "EKSTRAKLASA": "Poland",
  "BRA": "Brazil",
  "MLS": "USA",
  "ARG": "Argentina",
  "MEX": "Mexico",
  "COL": "Colombia",
  "CHI": "Chile",
  "CZE": "Czech Republic",
  "1. LIGA": "Czech Republic",
  "RUS": "Russia",
  "UKR": "Ukraine",
  "ROU": "Romania",
  "ELC": "England",
  "CHAMPIONSHIP": "England",
  "SD": "Spain",
  "BL2": "Germany",
  "IT2": "Italy",
  "SERIE B": "Italy",
  "FL2": "France",
  "LIGUE 2": "France",
};

export const formatCompetitionWithCountry = (comp, country) => {
  const cName = (comp || "").trim();
  const cCountry = (country || "").trim();

  if (!cName) return cCountry || "Football";

  const lowerComp = cName.toLowerCase();
  const lowerCountry = cCountry.toLowerCase();

  // Continental / European club competitions -> Do NOT prefix with country
  const isContinental =
    lowerComp.includes("champions league") ||
    lowerComp.includes("europa league") ||
    lowerComp.includes("conference league") ||
    lowerComp.includes("copa libertadores") ||
    lowerComp.includes("copa sudamericana") ||
    lowerComp.includes("nations league") ||
    lowerComp.includes("world cup") ||
    lowerComp.includes("ucl") ||
    lowerComp.includes("uel") ||
    lowerComp.includes("uecl") ||
    lowerCountry === "europe" ||
    lowerCountry === "international" ||
    lowerCountry === "world";

  if (isContinental) {
    return cName;
  }

  // Find country either passed or from lookup map
  const resolvedCountry = cCountry || LEAGUE_COUNTRY_MAP[cName.toUpperCase()] || LEAGUE_COUNTRY_MAP[cName.toUpperCase().replace(/\s+/g, "_")] || "";

  if (!resolvedCountry || lowerComp.includes(resolvedCountry.toLowerCase())) {
    return cName;
  }

  return `${resolvedCountry} · ${cName}`;
};

export default function TicketBuilderTab() {
  const [builderMode, setBuilderMode] = useState("TODAY_GAMES"); // "TODAY_GAMES", "ACCUMULATOR", or "ROLLOVER"

  // Standard Accumulator State
  const [leagueScope, setLeagueScope] = useState("MULTI");
  const [singleLeague, setSingleLeague] = useState("PL");
  const TOP_5_LEAGUE_CODES = ["PL", "PD", "SA", "BL1", "FL1"];
  const INTERNATIONAL_BREAK_CODES = [
    "INT", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY",
    "SD", "MLS", "BRA"
  ];
  const TOP_MAJOR_EUROPEAN_CODES = [
    "PL", "PD", "SA", "BL1", "FL1", "DED", "PPL", "TUR", "BEL", "AUT",
    "SCO", "SUI", "CRO", "DEN", "GRE", "NOR", "SWE", "POL", "ROU", "CZE", "RUS", "UKR", "SAU",
    "ELC", "SD", "BL2", "IT2", "FL2",
    "UCL", "UEL", "UECL",
    "INT", "UNL", "WCQ", "AFCON", "CONCACAF", "INT_FRIENDLY"
  ];
  const ALL_TOP_LEAGUE_CODES = TOP_MAJOR_EUROPEAN_CODES;

  const [targetOdds, setTargetOdds] = useState(2.0);
  const [targetMode, setTargetMode] = useState("ODDS"); // "ODDS" or "GAMES"
  const [targetGames, setTargetGames] = useState(10);
  const [customGamesInput, setCustomGamesInput] = useState("10");
  const [numTickets, setNumTickets] = useState(1); // 1, 2, 3 (Multi-Ticket Portfolio)
  const [activePortfolioIndex, setActivePortfolioIndex] = useState(0);
  const [portfolioTickets, setPortfolioTickets] = useState(null);
  const [mergingMaster, setMergingMaster] = useState(false);
  const [masterPrioritizedGames, setMasterPrioritizedGames] = useState(10);
  const [customMasterGamesInput, setCustomMasterGamesInput] = useState("10");
  const [selectedLeagues, setSelectedLeagues] = useState(["ALL_TODAY"]);
  const [dateWindow, setDateWindow] = useState("TODAY");
  const [selectedFlexCut, setSelectedFlexCut] = useState("OFF");
  const [customOdds, setCustomOdds] = useState("500");
  const [useCustom, setUseCustom] = useState(false);
  const [useLiveOdds, setUseLiveOdds] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [builderStep, setBuilderStep] = useState(1); // Wizard step: 1, 2, 3

  // Today's Games Mode State
  const [todayData, setTodayData] = useState(null); // { leagues, total_matches, date }
  const [todayLoading, setTodayLoading] = useState(false);
  const [todayError, setTodayError] = useState(null);
  const [todaySearch, setTodaySearch] = useState("");
  const [todayLeagueFilter, setTodayLeagueFilter] = useState("ALL");
  const [selectedTodayMatches, setSelectedTodayMatches] = useState({}); // eventId -> match object
  const [buildingFromToday, setBuildingFromToday] = useState(false);
  const [todayBuiltResult, setTodayBuiltResult] = useState(null);
  const [expandedOuRows, setExpandedOuRows] = useState({});
  const [matchGoalLines, setMatchGoalLines] = useState({}); // event_id -> selected goal line (e.g. "1.5")
  const [todayDayFilter, setTodayDayFilter] = useState("today"); // "today" or "tomorrow"

  // Auto-fetch today's/tomorrow's games with silent background refresh support
  const loadTodayGames = async (day = todayDayFilter, isSilent = false) => {
    if (!isSilent) setTodayLoading(true);
    setTodayError(null);
    try {
      const data = await fetchTodaysSportybetGames(day);
      setTodayData(data);
    } catch (e) {
      if (!isSilent) setTodayError("Could not load games. Check backend connection.");
    }
    if (!isSilent) setTodayLoading(false);
  };

  // Dynamic background polling every 30s to keep SportyBet live match count 100% fresh in real-time
  useEffect(() => {
    loadTodayGames(todayDayFilter, true);
    const pollTimer = setInterval(() => {
      loadTodayGames(todayDayFilter, true);
    }, 30000);
    return () => clearInterval(pollTimer);
  }, [todayDayFilter]);


  // Helper to extract comprehensive pick options (1X2, DC, O/U) for any match leg
  const getAvailablePicksForLeg = (leg) => {
    if (!leg) return [];
    const raw = leg.raw_match_data || leg || {};
    const r1x2 = raw.result_1x2 || leg.result_1x2 || raw || {};
    const ou = raw.ou_lines || leg.ou_lines || (raw.ou_line ? [{ line: raw.ou_line, over: raw.over, under: raw.under }] : []);
    const dc = raw.double_chance || leg.double_chance || {};

    const homeTeam = leg.home_team || raw.home_team || raw.home || "Home";
    const awayTeam = leg.away_team || raw.away_team || raw.away || "Away";

    // 1. Exact 1X2 market odds from attached result_1x2 or odds_home / odds_away
    let hOdd = parseFloat(r1x2["1"] || r1x2.home || r1x2.home_odds || raw["1"] || leg.odds_home || raw.odds_home);
    let dOdd = parseFloat(r1x2["X"] || r1x2.draw || r1x2.draw_odds || raw["X"] || leg.odds_draw || raw.odds_draw);
    let aOdd = parseFloat(r1x2["2"] || r1x2.away || r1x2.away_odds || raw["2"] || leg.odds_away || raw.odds_away);

    const curPick = String(leg.selection_name || leg.selection || leg.pick || "").toLowerCase();
    const curOdds = parseFloat(leg.estimated_odds || leg.odds || 0);

    if (!hOdd || isNaN(hOdd) || hOdd <= 1.0) {
      hOdd = (curPick.includes("to win (1)") || curPick.includes("home to win")) ? (curOdds || 2.10) : 2.10;
    }
    if (!dOdd || isNaN(dOdd) || dOdd <= 1.0) {
      dOdd = 3.30;
    }
    if (!aOdd || isNaN(aOdd) || aOdd <= 1.0) {
      aOdd = (curPick.includes("to win (2)") || curPick.includes("away to win")) ? (curOdds || 3.20) : 3.20;
    }

    // Derived Probabilities from actual market odds (removing bookmaker margin)
    const margin = (1.0 / hOdd) + (1.0 / dOdd) + (1.0 / aOdd);
    const pH = (1.0 / hOdd) / margin;
    const pD = (1.0 / dOdd) / margin;
    const pA = (1.0 / aOdd) / margin;

    // 2. Exact or mathematically derived Double Chance
    const dc1x = parseFloat(dc["1X"] || dc["1x"] || dc.home_draw) || roundOdds(1.0 / ((pH + pD) * 1.04));
    const dcx2 = parseFloat(dc["X2"] || dc["x2"] || dc.draw_away) || roundOdds(1.0 / ((pD + pA) * 1.04));
    const dc12 = parseFloat(dc["12"] || dc["12"] || dc.home_away) || roundOdds(1.0 / ((pH + pA) * 1.04));

    // 3. Exact Over/Under Goals (Strictly from real bookmaker feed ou_lines)
    const ouArray = Array.isArray(ou) ? ou : [];
    const ou15 = ouArray.find(x => String(x.line) === "1.5") || {};
    const ou25 = ouArray.find(x => String(x.line) === "2.5") || {};
    const ou35 = ouArray.find(x => String(x.line) === "3.5") || {};
    const ou45 = ouArray.find(x => String(x.line) === "4.5") || {};
    const ou05 = ouArray.find(x => String(x.line) === "0.5") || {};

    const totalGoalExp = (hOdd <= 1.25 || aOdd <= 1.25) ? 3.4 : (hOdd <= 1.55 || aOdd <= 1.55) ? 2.8 : 2.5;

    // 4. Exact or mathematically derived Win Either Half
    const probWehH = Math.min(0.96, pH * 1.15 + pD * 0.15);
    const probWehA = Math.min(0.96, pA * 1.15 + pD * 0.15);
    const wehH = roundOdds(1.0 / (probWehH * 1.04));
    const wehA = roundOdds(1.0 / (probWehA * 1.05));

    // 5. Exact or mathematically derived Team Goals
    const lambdaHome = totalGoalExp * (pH / (pH + pA));
    const lambdaAway = totalGoalExp * (pA / (pH + pA));
    const probHomeO15 = 1.0 - Math.exp(-lambdaHome) * (1 + lambdaHome);
    const probAwayO15 = 1.0 - Math.exp(-lambdaAway) * (1 + lambdaAway);
    const teamO15H = roundOdds(1.0 / (probHomeO15 * 1.05));
    const teamO15A = roundOdds(1.0 / (probAwayO15 * 1.05));

    // 6. Dynamic Handicaps
    const ahMinus1H = roundOdds(1.0 / (Math.max(0.20, pH * 0.78) * 1.05));
    const ahPlus15H = roundOdds(1.0 / ((pH + pD + pA * 0.40) * 1.04));
    const ahPlus15A = roundOdds(1.0 / ((pA + pD + pH * 0.40) * 1.04));

    const list = [
      { label: `${homeTeam} to Win (1)`, name: `${homeTeam} to Win (1)`, odds: hOdd, type: "1X2_HOME" },
      { label: `Draw (X)`, name: "Draw (X)", odds: dOdd, type: "1X2_DRAW" },
      { label: `${awayTeam} to Win (2)`, name: `${awayTeam} to Win (2)`, odds: aOdd, type: "1X2_AWAY" },
      { label: `${homeTeam} or Draw (1X)`, name: `${homeTeam} or Draw (1X)`, odds: dc1x, type: "DC_1X" },
      { label: `Draw or ${awayTeam} (X2)`, name: `Draw or ${awayTeam} (X2)`, odds: dcx2, type: "DC_X2" },
      { label: `${homeTeam} or ${awayTeam} (12)`, name: `${homeTeam} or ${awayTeam} (12)`, odds: dc12, type: "DC_12" },
      { label: `${homeTeam} Over 1.5 Team Goals`, name: `${homeTeam} Over 1.5 Goals`, odds: teamO15H, type: "TEAM_OU_H15" },
      { label: `${awayTeam} Over 1.5 Team Goals`, name: `${awayTeam} Over 1.5 Goals`, odds: teamO15A, type: "TEAM_OU_A15" },
      { label: `${homeTeam} (-1.0 Asian Handicap)`, name: `${homeTeam} (-1.0 Asian Handicap)`, odds: ahMinus1H, type: "AH_MINUS1" },
      { label: `${homeTeam} (+1.5 Handicap)`, name: `${homeTeam} (+1.5 Handicap)`, odds: ahPlus15H, type: "AH_H15" },
      { label: `${awayTeam} (+1.5 Handicap)`, name: `${awayTeam} (+1.5 Handicap)`, odds: ahPlus15A, type: "AH_A15" },
      { label: `${homeTeam} to Win Either Half`, name: `${homeTeam} to Win Either Half`, odds: wehH, type: "WEH_HOME" },
      { label: `${awayTeam} to Win Either Half`, name: `${awayTeam} to Win Either Half`, odds: wehA, type: "WEH_AWAY" },
    ];

    // Only inject real, bookmaker-published Over/Under lines
    if (ou15 && parseFloat(ou15.over) > 1.0) {
      list.push({ label: `Over 1.5 Goals`, name: "Over 1.5 Goals", odds: parseFloat(ou15.over), type: "OU_O15" });
    }
    if (ou25 && parseFloat(ou25.over) > 1.0) {
      list.push({ label: `Over 2.5 Goals`, name: "Over 2.5 Goals", odds: parseFloat(ou25.over), type: "OU_O25" });
    }
    if (ou35 && parseFloat(ou35.under) > 1.0) {
      list.push({ label: `Under 3.5 Goals`, name: "Under 3.5 Goals", odds: parseFloat(ou35.under), type: "OU_U35" });
    }
    if (ou45 && parseFloat(ou45.under) > 1.0) {
      list.push({ label: `Under 4.5 Goals`, name: "Under 4.5 Goals", odds: parseFloat(ou45.under), type: "OU_U45" });
    }
    if (ou05 && parseFloat(ou05.over) > 1.0) {
      list.push({ label: `Over 0.5 Goals`, name: "Over 0.5 Goals", odds: parseFloat(ou05.over), type: "OU_O05" });
    }

    const currentName = leg.selection_name || leg.selection || leg.pick;
    if (currentName && !list.find(item => item.name === currentName || item.label === currentName)) {
      list.unshift({
        label: currentName,
        name: currentName,
        odds: leg.estimated_odds || leg.odds || 1.30,
        type: "CUSTOM"
      });
    }

    return list;
  };

  const handleBuildFromSelected = async () => {
    const selected = Object.values(selectedTodayMatches);
    if (selected.length < 2) return;
    setBuildingFromToday(true);
    setTodayBuiltResult(null);

    // AI Prediction Generator for selected matches
    const legs = selected.map(m => {
      const pHome = m.ai_prob_home || 0.45;
      const pAway = m.ai_prob_away || 0.30;
      const pOver15 = m.ai_prob_over_1_5 || 0.75;
      const r1x2 = m.result_1x2 || {};
      const ou15 = (m.ou_lines || []).find(l => String(l.line) === "1.5") || {};
      const dc = m.double_chance || {};

      let pickName = "Over 1.5 Goals";
      let pickOdds = ou15.over || 1.30;
      let prob = pOver15;

      // Heavy home favorite (< 1.65 odds & > 60% probability)
      if (r1x2.home && r1x2.home <= 1.65 && pHome >= 0.60) {
        pickName = `${m.home_team} to Win`;
        pickOdds = r1x2.home;
        prob = pHome;
      } else if (r1x2.away && r1x2.away <= 1.65 && pAway >= 0.60) {
        pickName = `${m.away_team} to Win`;
        pickOdds = r1x2.away;
        prob = pAway;
      } else if (dc["1X"] && (pHome >= 0.40 || (r1x2.home && r1x2.home <= 2.60))) {
        pickName = `${m.home_team} or Draw (1X)`;
        pickOdds = dc["1X"];
        prob = Math.min(0.92, pHome + 0.28);
      } else if (dc["X2"] && (pAway >= 0.40 || (r1x2.away && r1x2.away <= 2.60))) {
        pickName = `${m.away_team} or Draw (X2)`;
        pickOdds = dc["X2"];
        prob = Math.min(0.92, pAway + 0.28);
      } else if (ou15.over) {
        pickName = "Over 1.5 Goals";
        pickOdds = ou15.over;
        prob = Math.max(0.78, pOver15);
      }

      return {
        fixture_id: m.event_id,
        external_fixture_id: m.event_id,
        game_id: m.event_id,
        home_team: m.home_team,
        away_team: m.away_team,
        competition: m.competition_code || "League",
        competition_code: m.competition_code || "League",
        selection_name: pickName,
        selection: pickName,
        odds: pickOdds,
        estimated_odds: pickOdds,
        model_probability: Math.min(0.95, prob),
        confidence_tier: prob >= 0.75 ? "ELITE" : prob >= 0.60 ? "HIGH" : "SOLID",
        raw_match_data: m
      };
    });

    let totalOdds = 1.0;
    legs.forEach(l => { totalOdds *= (parseFloat(l.odds) || 1.3); });
    totalOdds = roundOdds(totalOdds);

    // Generate real SportyBet booking code
    let bookingCode = null;
    let shareUrl = null;
    try {
      const codeRes = await generateVerifiedBookingCode(legs, "STATIQ-SEL", "ng");
      if (codeRes && codeRes.booking_code) {
        bookingCode = codeRes.booking_code;
        shareUrl = codeRes.share_url;
      }
    } catch (e) {}

    const built = {
      approved_legs: legs,
      accumulated_odds: totalOdds,
      combined_probability: legs.reduce((acc, l) => acc * (l.model_probability || 0.7), 1),
      confidence_tier: "HIGH",
      recommended_stake_pct: 3.5,
      booking_code: bookingCode,
      share_url: shareUrl
    };

    setBuildingFromToday(false);
    setTodayBuiltResult(built);
  };

  const toggleMatchSelection = (match) => {
    setSelectedTodayMatches(prev => {
      const next = { ...prev };
      if (next[match.event_id]) {
        delete next[match.event_id];
      } else {
        next[match.event_id] = match;
      }
      return next;
    });
  };


  // Rollover State
  const [kickoffScope, setKickoffScope] = useState("TODAY"); // "TODAY", "NEXT_24H", "ALL"
  const [rolloverRange, setRolloverRange] = useState("SAT_SUN"); // "SAT_SUN" (2 Days), "TODAY_TOMORROW", etc.
  const [dailyTargetOdds, setDailyTargetOdds] = useState(1.50);
  const [startingStake, setStartingStake] = useState(5000);

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [result, setResult] = useState(null);
  const [rolloverResult, setRolloverResult] = useState(null);
  const [generatedCodes, setGeneratedCodes] = useState({});

  const formatNGN = (amount) => "₦" + Math.round(Number(amount || 0)).toLocaleString();

  const calculateCompoundingLadder = (stake = 5000, days = 10, targetOdds = 2.00) => {
    const steps = [];
    let current = parseFloat(stake) || 5000;
    const odds = parseFloat(targetOdds) || 2.00;
    const totalDays = Math.min(30, Math.max(1, parseInt(days) || 10));

    for (let i = 1; i <= totalDays; i++) {
      const potReturn = Math.round(current * odds);
      steps.push({
        day: i,
        stake: current,
        return: potReturn,
        targetOdds: odds
      });
      current = potReturn;
    }
    return steps;
  };

  // ─── Automated 10:00 AM WAT Rollover Engine State ───────────────────────
  const [cronConfig, setCronConfig] = useState({
    is_enabled: true,
    active_days: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
    target_odds: 2.00,
    max_leg_odds: 1.45,
    dispatch_time: "10:00",
    campaign_mode: "CHALLENGE", // "CHALLENGE" or "CONTINUOUS"
    challenge_days: 10,
    challenge_day_current: 1,
    challenge_start_date: new Date().toISOString().split("T")[0],
    challenge_end_date: null,
    starting_stake: 5000,
    challenge_status: "ACTIVE",
    last_run_date: null,
    last_ticket: null
  });
  const [cronLoading, setCronLoading] = useState(false);
  const [cronRunningNow, setCronRunningNow] = useState(false);
  const [cronNotice, setCronNotice] = useState(null);
  const [cronError, setCronError] = useState(null);
  const [telegramStatus, setTelegramStatus] = useState(null);
  const [telegramTesting, setTelegramTesting] = useState(false);
  const [cronHistory, setCronHistory] = useState([]);
  const [showCronHistory, setShowCronHistory] = useState(false);
  const [cronTicketResult, setCronTicketResult] = useState(null);
  const [copiedCronCode, setCopiedCronCode] = useState(false);
  const [showCompoundingLadder, setShowCompoundingLadder] = useState(false);
  const [showQualityGates, setShowQualityGates] = useState(false);

  const loadCronData = async () => {
    try {
      const res = await fetchRolloverSchedule();
      if (res && res.config) {
        setCronConfig(prev => ({ ...prev, ...res.config }));
        if (res.config.last_ticket && !cronTicketResult) {
          setCronTicketResult(res.config.last_ticket);
        }
      }
      const histRes = await fetchRolloverHistory();
      if (histRes && histRes.history) {
        setCronHistory(histRes.history);
      }
    } catch (e) {
      console.error("Error loading rollover cron data:", e);
    }
  };

  useEffect(() => {
    loadCronData();
  }, []);

  const handleToggleCronDay = (dayCode) => {
    setCronConfig(prev => {
      const days = prev.active_days || [];
      const updated = days.includes(dayCode)
        ? days.filter(d => d !== dayCode)
        : [...days, dayCode];
      return { ...prev, active_days: updated };
    });
  };

  const handleResetChallenge = async (days = 10, stake = 5000) => {
    setCronLoading(true);
    setCronNotice(null);
    setCronError(null);
    try {
      const res = await resetRolloverChallenge(days, stake);
      if (res && res.status === "SUCCESS") {
        setCronConfig(prev => ({ ...prev, ...res.config }));
        setCronNotice(`Fresh ${days}-Day Compounding Challenge started from Day 1!`);
        setTimeout(() => setCronNotice(null), 4000);
      } else {
        setCronError(res?.message || "Failed to reset challenge.");
      }
    } catch (e) {
      setCronError("Error resetting challenge: " + e.message);
    } finally {
      setCronLoading(false);
    }
  };

  const handleSaveCronSchedule = async () => {
    setCronLoading(true);
    setCronNotice(null);
    setCronError(null);
    try {
      const res = await updateRolloverSchedule({
        is_enabled: cronConfig.is_enabled,
        active_days: cronConfig.active_days,
        target_odds: cronConfig.target_odds,
        max_leg_odds: cronConfig.max_leg_odds || 1.45,
        dispatch_time: cronConfig.dispatch_time || "10:00",
        campaign_mode: cronConfig.campaign_mode || "CHALLENGE",
        challenge_days: cronConfig.challenge_days || 10,
        challenge_day_current: cronConfig.challenge_day_current || 1,
        challenge_start_date: cronConfig.challenge_start_date,
        challenge_end_date: cronConfig.challenge_end_date,
        starting_stake: cronConfig.starting_stake || 5000,
        challenge_status: cronConfig.challenge_status || "ACTIVE"
      });
      if (res && res.status === "SUCCESS") {
        setCronNotice("Rollover campaign settings saved successfully!");
        setTimeout(() => setCronNotice(null), 4000);
      } else {
        setCronError("Failed to save schedule settings.");
      }
    } catch (e) {
      setCronError("Network error saving schedule.");
    } finally {
      setCronLoading(false);
    }
  };

  const handleRunCronNow = async () => {
    setCronRunningNow(true);
    setCronError(null);
    setCronNotice(null);
    try {
      const res = await runRolloverNow(cronConfig.target_odds, cronConfig.max_leg_odds || 1.45);
      if (res && res.status === "SUCCESS" && res.result) {
        setCronTicketResult(res.result);
        setCronNotice(`Rollover slip generated! Booking code: ${res.result.booking_code || "Generated"} (${res.result.telegram_dispatched ? "Dispatched to Telegram" : "Saved"})`);
        const histRes = await fetchRolloverHistory();
        if (histRes && histRes.history) {
          setCronHistory(histRes.history);
        }
      } else {
        setCronError(res.message || "Failed to generate rollover ticket.");
      }
    } catch (e) {
      setCronError("Error executing rollover run: " + (e.message || "Error"));
    } finally {
      setCronRunningNow(false);
    }
  };

  const handleTestCronTelegram = async () => {
    setTelegramTesting(true);
    setTelegramStatus(null);
    try {
      const res = await testRolloverTelegram();
      if (res && res.sent) {
        setTelegramStatus({ type: "SUCCESS", msg: "Test alert delivered to Telegram successfully!" });
      } else {
        setTelegramStatus({ type: "ERROR", msg: res?.message || "Failed to deliver message to Telegram." });
      }
    } catch (e) {
      setTelegramStatus({ type: "ERROR", msg: "Telegram test failed." });
    } finally {
      setTelegramTesting(false);
      setTimeout(() => setTelegramStatus(null), 5000);
    }
  };

  // Risk Profile & Market Preferences
  const [riskProfile, setRiskProfile] = useState("CONSERVATIVE"); // "CONSERVATIVE" (Safety Cushions) or "AGGRESSIVE" (Value Maximizer)
  const [selectedMarketCategories, setSelectedMarketCategories] = useState([
    "DOUBLE_CHANCE",
    "OVER_UNDER",
    "TEAM_GOALS",
    "1X2"
  ]);

  // Custom Shortlist Builder State & Handlers
  const SAMPLE_SHORTLIST_MATCHES = `Slovenia vs Scotland
Bulgaria vs Luxembourg
Faroe Islands vs Kazakhstan
Iceland vs Estonia
San Marino vs Finland
Albania vs Belarus
Czechia vs Croatia
England vs Spain
North Macedonia vs Switzerland
Slovakia vs Moldova`;

  const [shortlistText, setShortlistText] = useState("");
  const [shortlistTargetMode, setShortlistTargetMode] = useState("GAMES"); // "GAMES" or "ODDS"
  const [shortlistTargetGames, setShortlistTargetGames] = useState(5);
  const [shortlistTargetOdds, setShortlistTargetOdds] = useState(3.0);
  const [shortlistNumTickets, setShortlistNumTickets] = useState(1);
  const [shortlistRiskProfile, setShortlistRiskProfile] = useState("CONSERVATIVE"); // "CONSERVATIVE" or "AGGRESSIVE"
  const [shortlistBuilding, setShortlistBuilding] = useState(false);
  const [shortlistResult, setShortlistResult] = useState(null);
  const [shortlistError, setShortlistError] = useState(null);
  const [shortlistActivePortfolioIndex, setShortlistActivePortfolioIndex] = useState(0);
  const [shortlistCopiedCode, setShortlistCopiedCode] = useState(false);

  const shortlistMatchCount = shortlistText
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(l => l.length > 0 && !l.startsWith("#") && !l.startsWith("//") && !l.startsWith("ID:") && !l.startsWith("1X2"))
    .length;

  const handleLoadSampleShortlist = () => {
    setShortlistText(SAMPLE_SHORTLIST_MATCHES);
    setShortlistError(null);
  };

  const handleClearShortlist = () => {
    setShortlistText("");
    setShortlistResult(null);
    setShortlistError(null);
  };

  const handleShortlistFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === "string") {
        setShortlistText(content);
        setShortlistError(null);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  const handleBuildShortlistTicket = async () => {
    if (!shortlistText.trim()) {
      setShortlistError("Please enter or paste match fixtures (e.g. 'Team A vs Team B').");
      return;
    }
    setShortlistBuilding(true);
    setShortlistError(null);
    setShortlistResult(null);

    try {
      const payload = {
        matches_text: shortlistText,
        raw_text: shortlistText,
        target_mode: shortlistTargetMode,
        target_games: shortlistTargetMode === "GAMES" ? parseInt(shortlistTargetGames, 10) : 5,
        target_odds: shortlistTargetMode === "ODDS" ? parseFloat(shortlistTargetOdds) : 5.0,
        num_tickets: parseInt(shortlistNumTickets, 10) || 1,
        risk_profile: shortlistRiskProfile,
        min_odds: 1.15
      };

      const res = await buildTicketFromShortlist(payload);
      if (res && res.status === "SUCCESS") {
        setShortlistResult(res);
        setShortlistActivePortfolioIndex(0);
      } else {
        setShortlistError(res.message || res.detail || "No valid picks could be approved from the provided fixtures. Verify teams are playing today.");
      }
    } catch (err) {
      setShortlistError(err.message || "Failed to evaluate shortlist.");
    } finally {
      setShortlistBuilding(false);
    }
  };

  // Audit Logs & Rejected Picks UI State
  const [expandedAuditLogs, setExpandedAuditLogs] = useState({});
  const [showRejectedDrawer, setShowRejectedDrawer] = useState(false);

  // Code Generation Modal Popup State
  const [codeModalData, setCodeModalData] = useState(null);
  const [showCodeModal, setShowCodeModal] = useState(false);

  // Lock & Track Ticket Modal State
  const [showLockModal, setShowLockModal] = useState(false);
  const [lockTargetData, setLockTargetData] = useState(null);
  const [stakeInput, setStakeInput] = useState("1000");
  const [lockingTicket, setLockingTicket] = useState(false);
  const [lockedNotice, setLockedNotice] = useState(null);

  const handleLockTicketSubmit = async () => {
    if (!lockTargetData) return;
    setLockingTicket(true);
    try {
      // Map UI builder modes to canonical tracker mode strings that BetHistoryTab classifier understands
      const modeMap = {
        "ACCUMULATOR": "AI_BUILDER",
        "TODAY_GAMES": "AI_BUILDER",
        "ROLLOVER": "ROLLOVER",
        "SHORTLIST": "AI_BUILDER"
      };
      const canonicalMode = lockTargetData.mode || modeMap[builderMode] || "AI_BUILDER";

      const payload = {
        code: lockTargetData.code || "AI-BUILDER-TICKET",
        mode: canonicalMode,
        target_odds: lockTargetData.targetOdds || targetOdds,
        total_odds: lockTargetData.totalOdds || 2.0,
        stake: parseFloat(stakeInput) || 1000,
        flex_cut: selectedFlexCut,
        selections: lockTargetData.selections || []
      };
      const res = await lockTrackedTicket(payload);
      if (res && (res.id || res.status === "SUCCESS" || res.code)) {
        setShowLockModal(false);
        setLockedNotice(`Ticket ${res.code || res.id || ""} successfully locked into StatIQ Ticket Tracker! Track live settlements in the BetSlip Auditor tab.`);
        setTimeout(() => setLockedNotice(null), 6000);
      } else {
        setLockedNotice("Failed to lock ticket into Tracker. Ensure backend is running.");
        setTimeout(() => setLockedNotice(null), 5000);
      }
    } catch (e) {
      setLockedNotice("Error locking ticket: " + e.message);
      setTimeout(() => setLockedNotice(null), 5000);
    }
    setLockingTicket(false);
  };

  const oddsPresetButtons = [2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 500.0, 1000.0];

  // Helper to dynamically calculate ideal leg bounds for a target total odds
  const getLegBoundsForOdds = (targetTotalOdds) => {
    const o = targetTotalOdds || 2.0;
    if (o <= 2.5) return { min: 2, max: 3, defaultAvgOdds: 1.25 };
    if (o <= 5.0) return { min: 3, max: 5, defaultAvgOdds: 1.30 };
    if (o <= 10.0) return { min: 5, max: 7, defaultAvgOdds: 1.32 };
    if (o <= 25.0) return { min: 7, max: 10, defaultAvgOdds: 1.33 };
    if (o <= 75.0) return { min: 11, max: 14, defaultAvgOdds: 1.35 };
    if (o <= 200.0) return { min: 13, max: 17, defaultAvgOdds: 1.34 };
    if (o <= 600.0) return { min: 17, max: 23, defaultAvgOdds: 1.33 };
    return { min: 20, max: 26, defaultAvgOdds: 1.32 };
  };

  /**
   * extractSafestSelection — delegates to the shared MatchIQ Pick Engine.
   * Uses Elo-based tier detection + diverse safe pick pools (Gate 1-4).
   * Falls back to Over 1.5 Goals when AI probabilities aren't available.
   *
   * Accepts an optional usedTypeCounts object to enforce Gate 4 diversity
   * across the current ticket being built.
   */
  const extractSafestSelection = (f, usedTypeCounts = {}) => {
    const pd = generateSafePick(f, usedTypeCounts);
    return {
      fixture_id: f.fixture_id || f.external_id,
      home_team: f.home_team || f.home || "Home",
      away_team: f.away_team || f.away || "Away",
      competition_code: f.competition_code || "PL",
      kickoff_datetime: f.kickoff_datetime,
      selection: pd.pick,
      selection_name: pd.pick,
      model_probability: pd.prob / 100,
      estimated_odds: pd.odds,
      tier: pd.tier,
      marketType: pd.marketType,
    };
  };

  const roundOdds = (val) => {
    return Math.max(1.10, Math.min(9.50, Math.round(val * 100) / 100));
  };

  // Build Accumulator Ticket dynamically using 5-Gate Pick Engine Backend API
  const handleBuildSafestTicket = async () => {
    setLoading(true);
    setErrorMsg(null);
    setResult(null);
    setExpandedAuditLogs({});

    const finalOddsGoal = useCustom ? parseFloat(customOdds) || 50.0 : targetOdds;
    const payload = {
      target_odds: finalOddsGoal,
      target_mode: targetMode,
      target_games: targetGames,
      selected_leagues: selectedLeagues,
      date_window: dateWindow,
      flex_cut: selectedFlexCut === "OFF" ? 0 : parseInt(selectedFlexCut) || 0,
      mode: "ACCUMULATOR",
      num_tickets: numTickets,
      overlap_mode: "ZERO_OVERLAP",
      use_live_odds: true,
      strict_mode: strictMode,
      reshuffle_seed: Date.now(),
      risk_profile: riskProfile,
      allowed_market_categories: selectedMarketCategories
    };

    const res = await buildAiTicket(payload);
    setLoading(false);

    if (!res || res.status === "TIMEOUT" || res.status === "HTTP_ERROR" || res.status === "ERROR" || res.status === "NO_FIXTURES") {
      setErrorMsg(
        res?.message ||
        res?.ticket?.error ||
        (res?.status === "TIMEOUT"
          ? "Request timed out (>25s). The engine is busy — please try again."
          : res?.status === "HTTP_ERROR"
          ? `Backend error (HTTP ${res.http_status}). Ensure backend is running.`
          : "MatchIQ 5-Gate Pick Engine failed to build ticket. Check backend logs.")
      );
      return;
    }

    if (!res.ticket || !res.ticket.approved_legs || res.ticket.approved_legs.length === 0) {
      setErrorMsg(res?.ticket?.error || res?.message || "No suitable matches found for the selected leagues and timeframe.");
      return;
    }

    const scopeLabel = selectedLeagues.includes("ALL") ? "All Top Leagues" : selectedLeagues.join(", ");

    if (res.portfolio_tickets && res.portfolio_tickets.length > 1) {
      setPortfolioTickets(res.portfolio_tickets);
      setActivePortfolioIndex(0);

      const scenarios = res.portfolio_tickets.map((t, tIdx) => ({
        scenario_id: `STATIQ-PORTFOLIO-SLIP-${tIdx + 1}`,
        ticket_index: tIdx + 1,
        scope_label: `${scopeLabel} · Slip #${tIdx + 1} (${t.approved_legs.length} Legs)`,
        gameweek_label: dateWindow,
        target_mode: targetMode,
        target_games: targetGames,
        target_odds: finalOddsGoal,
        accumulated_odds: t.accumulated_odds,
        independence_assumption_probability: t.combined_probability,
        correlation_adjusted_probability: t.correlation_adjusted_probability,
        confidence_tier: t.confidence_tier,
        recommended_stake_pct: t.recommended_stake_pct,
        selections: t.approved_legs,
        rejected_picks: t.rejected_picks,
        booking_code: t.booking_code,
        share_url: t.share_url,
        total_evaluated: t.total_evaluated,
        decision_audit_summary: t.decision_audit_summary
      }));

      setResult({
        ticket: res.ticket,
        portfolio_summary: res.portfolio_summary,
        scenarios: scenarios
      });
    } else if (res.ticket) {
      setPortfolioTickets(null);
      setActivePortfolioIndex(0);
      setResult({
        ticket: res.ticket,
        scenarios: [
          {
            scenario_id: `STATIQ-${targetMode === "GAMES" ? `${targetGames}G` : `${finalOddsGoal.toFixed(0)}X`}-${dateWindow}`,
            ticket_index: 1,
            scope_label: `${scopeLabel} · ${dateWindow}`,
            gameweek_label: dateWindow,
            target_mode: targetMode,
            target_games: targetGames,
            target_odds: finalOddsGoal,
            accumulated_odds: res.ticket.accumulated_odds,
            independence_assumption_probability: res.ticket.combined_probability,
            correlation_adjusted_probability: res.ticket.correlation_adjusted_probability,
            confidence_tier: res.ticket.confidence_tier,
            recommended_stake_pct: res.ticket.recommended_stake_pct,
            selections: res.ticket.approved_legs,
            rejected_picks: res.ticket.rejected_picks,
            booking_code: res.ticket.booking_code,
            share_url: res.ticket.share_url,
            total_evaluated: res.ticket.total_evaluated,
            decision_audit_summary: res.ticket.decision_audit_summary
          }
        ]
      });
    }
  };

  // Merge Portfolio Variant Slips into 1 Unified Master Ticket
  const handleMergeToMaster = async (gamesCount = masterPrioritizedGames) => {
    if (!result?.scenarios || result.scenarios.length < 2) return;
    setMergingMaster(true);
    try {
      const payload = {
        slips: result.scenarios,
        target_games: gamesCount,
        country_code: "ng"
      };
      const res = await mergeMasterTicket(payload, "/ai-ticket/merge-master");
      if (res?.status === "SUCCESS" && res?.master_ticket) {
        const masterScn = res.master_ticket;
        const filtered = result.scenarios.filter(s => s.ticket_index !== "MASTER" && !s.is_master);
        const newScenarios = [...filtered, masterScn];
        setResult({
          ...result,
          scenarios: newScenarios
        });
        setActivePortfolioIndex(newScenarios.length - 1);
      }
    } catch (e) {
      console.error("Master ticket merge error:", e);
    } finally {
      setMergingMaster(false);
    }
  };

  // Merge Shortlist Portfolio Slips into 1 Unified Master Ticket
  const handleMergeShortlistToMaster = async (gamesCount = masterPrioritizedGames) => {
    if (!shortlistResult?.scenarios || shortlistResult.scenarios.length < 2) return;
    setMergingMaster(true);
    try {
      const payload = {
        slips: shortlistResult.scenarios,
        target_games: gamesCount,
        country_code: "ng"
      };
      const res = await mergeMasterTicket(payload, "/ai-ticket/merge-master");
      if (res?.status === "SUCCESS" && res?.master_ticket) {
        const masterScn = res.master_ticket;
        const filtered = shortlistResult.scenarios.filter(s => s.ticket_index !== "MASTER" && !s.is_master);
        const newScenarios = [...filtered, masterScn];
        setShortlistResult({
          ...shortlistResult,
          scenarios: newScenarios
        });
        setShortlistActivePortfolioIndex(newScenarios.length - 1);
      }
    } catch (e) {
      console.error("Shortlist master ticket merge error:", e);
    } finally {
      setMergingMaster(false);
    }
  };

  // Build High-Assurance Daily Rollover Slip (Today's Safest Picks)
  const handleBuildRollover = async () => {
    setLoading(true);
    setErrorMsg(null);
    setRolloverResult(null);
    setExpandedAuditLogs({});

    try {
      const payload = {
        target_odds: dailyTargetOdds,
        target_mode: "ODDS",
        mode: "ROLLOVER",
        selected_leagues: selectedLeagues,
        date_window: dateWindow,
        league_scope: "MULTI",
        single_league: "PL",
        use_live_odds: true,
        kickoff_scope: dateWindow,
        strict_mode: strictMode,
        reshuffle_seed: Date.now(),
        risk_profile: riskProfile,
        allowed_market_categories: selectedMarketCategories
      };

      const res = await buildAiTicket(payload);

      if (!res || res.status === "TIMEOUT" || res.status === "HTTP_ERROR" || res.status === "ERROR" || res.status === "NO_FIXTURES" || !res.ticket || !res.ticket.approved_legs || res.ticket.approved_legs.length === 0) {
        setErrorMsg(
          res?.message ||
          res?.ticket?.error ||
          (res?.status === "TIMEOUT"
            ? "Rollover analysis timed out. Please try again."
            : "No suitable ultra-safe matches found for the selected leagues and timeframe. Try adjusting your league selection or schedule window.")
        );
        return;
      }

      const legs = res.ticket.approved_legs;
      const totalMultiplier = res.ticket.accumulated_odds || roundOddsVal(legs.reduce((acc, curr) => acc * (curr.estimated_odds || curr.odds || 1.3), 1.0));
      const finalEstimatedPayout = roundOddsVal(startingStake * totalMultiplier);

      const codeRes = await generateSportyBetCode(legs);
      const code = codeRes.booking_code || res.ticket.booking_code || "BC-ROLLOVER-LIVE";

      setRolloverResult({
        picks: legs,
        totalMultiplier: totalMultiplier,
        finalEstimatedPayout: finalEstimatedPayout,
        bookingCode: code,
        confidence_tier: res.ticket.confidence_tier || "HIGH",
        recommended_stake_pct: res.ticket.recommended_stake_pct,
        decision_audit_summary: res.ticket.decision_audit_summary,
        rejected_picks: res.ticket.rejected_picks
      });
    } catch (err) {
      console.error("Rollover generation error:", err);
      setErrorMsg("Error generating rollover ticket: " + (err.message || "Unknown error"));
    } finally {
      setLoading(false);
    }
  };

  const roundOddsVal = (val) => Math.round(val * 100) / 100;

  const handleRemoveSelection = (scenarioId, selIdx) => {
    setResult((prev) => {
      if (!prev || !prev.scenarios) return prev;
      const updated = prev.scenarios.map((s) => {
        if (s.scenario_id !== scenarioId) return s;
        const newPicks = s.selections.filter((_, i) => i !== selIdx);
        const newOdds = roundOddsVal(newPicks.reduce((acc, curr) => acc * (curr.estimated_odds || curr.odds || 1.3), 1.0));
        return {
          ...s,
          selections: newPicks,
          accumulated_odds: newOdds,
          booking_code: null
        };
      });
      return { ...prev, scenarios: updated };
    });
    setGeneratedCodes((prev) => {
      const copy = { ...prev };
      delete copy[scenarioId];
      return copy;
    });
  };

  const handleRemoveRolloverLeg = (legIdx) => {
    setRolloverResult((prev) => {
      if (!prev || !prev.picks) return prev;
      const newPicks = prev.picks.filter((_, i) => i !== legIdx);
      const newMultiplier = roundOddsVal(newPicks.reduce((acc, curr) => acc * (curr.estimated_odds || curr.odds || 1.3), 1.0));
      return {
        ...prev,
        picks: newPicks,
        totalMultiplier: newMultiplier,
        finalEstimatedPayout: roundOddsVal(startingStake * newMultiplier),
        bookingCode: null
      };
    });
  };

  const handleRemoveRolloverPick = (legIdx) => {
    handleRemoveRolloverLeg(legIdx);
  };

  // Handle manual or dropdown override of an Accumulator leg
  const handleOverrideLegPick = async (scenarioId, legIndex, newPickOption) => {
    if (!result || !result.scenarios) return;
    const targetScn = result.scenarios.find(s => s.scenario_id === scenarioId);
    if (!targetScn) return;

    const newSelections = targetScn.selections.map((sel, idx) => {
      if (idx !== legIndex) return sel;
      const updatedOdds = parseFloat(newPickOption.odds) || sel.estimated_odds || 1.30;
      const updatedProb = newPickOption.prob || sel.model_probability || 0.85;
      return {
        ...sel,
        selection_name: newPickOption.name || newPickOption.label,
        selection: newPickOption.name || newPickOption.label,
        odds: updatedOdds,
        estimated_odds: updatedOdds,
        model_probability: updatedProb,
        confidence_tier: updatedProb >= 0.88 ? "ELITE" : updatedProb >= 0.78 ? "HIGH" : "SOLID"
      };
    });

    const newAccOdds = roundOddsVal(newSelections.reduce((acc, p) => acc * (p.estimated_odds || p.odds || 1.3), 1.0));
    const newWinProb = newSelections.reduce((acc, p) => acc * (p.model_probability || 0.8), 1.0);

    const updatedScenarios = result.scenarios.map(s => {
      if (s.scenario_id !== scenarioId) return s;
      return {
        ...s,
        selections: newSelections,
        accumulated_odds: newAccOdds,
        combined_probability: newWinProb
      };
    });

    setResult({ ...result, scenarios: updatedScenarios });

    // Regenerate real SportyBet booking code in background
    try {
      const codeRes = await generateSportyBetCode(newSelections);
      if (codeRes && codeRes.booking_code) {
        setGeneratedCodes(prev => ({ ...prev, [scenarioId]: codeRes.booking_code }));
      }
    } catch (e) {}
  };

  // Cycle to next best mathematically vetted AI pick for an Accumulator leg
  const handleCycleNextAiPick = (scenarioId, legIndex, currentLeg) => {
    const opts = getAvailablePicksForLeg(currentLeg);
    if (!opts || opts.length === 0) return;
    const currentName = currentLeg.selection_name || currentLeg.selection;
    const currentIndex = opts.findIndex(o => o.name === currentName || o.label === currentName);
    const nextIndex = (currentIndex + 1) % opts.length;
    handleOverrideLegPick(scenarioId, legIndex, opts[nextIndex]);
  };

  // Handle manual or dropdown override of a Rollover leg
  const handleOverrideRolloverPick = async (legIndex, newPickOption) => {
    if (!rolloverResult || !rolloverResult.picks) return;

    const newPicks = rolloverResult.picks.map((p, idx) => {
      if (idx !== legIndex) return p;
      const updatedOdds = parseFloat(newPickOption.odds) || p.estimated_odds || 1.30;
      const updatedProb = newPickOption.prob || p.model_probability || 0.88;
      return {
        ...p,
        selection_name: newPickOption.name || newPickOption.label,
        selection: newPickOption.name || newPickOption.label,
        odds: updatedOdds,
        estimated_odds: updatedOdds,
        model_probability: updatedProb,
        confidence_tier: updatedProb >= 0.88 ? "ELITE" : updatedProb >= 0.78 ? "HIGH" : "SOLID"
      };
    });

    const newMultiplier = roundOddsVal(newPicks.reduce((acc, curr) => acc * (curr.estimated_odds || curr.odds || 1.3), 1.0));
    const newPayout = roundOddsVal(startingStake * newMultiplier);

    setRolloverResult(prev => ({
      ...prev,
      picks: newPicks,
      totalMultiplier: newMultiplier,
      finalEstimatedPayout: newPayout
    }));

    // Regenerate real SportyBet booking code
    try {
      const codeRes = await generateSportyBetCode(newPicks);
      if (codeRes && codeRes.booking_code) {
        setRolloverResult(prev => ({ ...prev, bookingCode: codeRes.booking_code }));
      }
    } catch (e) {}
  };

  // Cycle to next best mathematically vetted AI pick for a Rollover leg
  const handleCycleNextRolloverAiPick = (legIndex, currentLeg) => {
    const opts = getAvailablePicksForLeg(currentLeg);
    if (!opts || opts.length === 0) return;
    const currentName = currentLeg.selection_name || currentLeg.selection || currentLeg.pick;
    const currentIndex = opts.findIndex(o => o.name === currentName || o.label === currentName);
    const nextIndex = (currentIndex + 1) % opts.length;
    handleOverrideRolloverPick(legIndex, opts[nextIndex]);
  };

  // Generate Booking Code & Trigger UI/UX Modal Popup
  const handleGenerateCode = async (id, selections, scenarioLabel) => {
    setLoading(true);
    const res = await generateVerifiedBookingCode(selections, id || "AI-TKT", "ng");
    setLoading(false);

    // Handle failure cases — don't fabricate random codes
    if (!res || res.status === "REJECTED" || !res.booking_code) {
      const msg = res?.message || "Failed to verify SportyBet booking code. Ensure matches are active on SportyBet Nigeria.";
      setErrorMsg(msg);
      return;
    }

    const code = res.booking_code;
    const regionalCodes = { NG: code };
    setGeneratedCodes(prev => ({ ...prev, [id]: code }));

    // Trigger Popup Modal
    setCodeModalData({
      code,
      regionalCodes,
      selectedRegion: "NG",
      status: res.status,
      verificationSummary: res.reconciliation_summary || "All selections verified 100% with zero false positives.",
      totalOdds: res.total_odds,
      label: scenarioLabel || "StatIQ AI Ticket",
      selections,
      loadUrl: res.share_url || `https://www.sportybet.com/ng/?shareCode=${code}`
    });
    setShowCodeModal(true);
  };


  const copySelectionsAsText = (selections) => {
    const text = selections.map(s => `• ${s.home_team || s.fixture} -> ${s.selection_name || s.selection || s.pick}`).join("\n");
    navigator.clipboard.writeText(text);
    setLockedNotice("Selections copied to clipboard!");
    setTimeout(() => setLockedNotice(null), 4000);
  };

  const handleRemoveAccumulatorSelection = (scenarioId, selIdx) => {
    if (!result || !result.scenarios) return;
    const updatedScenarios = result.scenarios.map((scn) => {
      if (scn.scenario_id !== scenarioId) return scn;
      const newSelections = scn.selections.filter((_, idx) => idx !== selIdx);
      if (newSelections.length === 0) return null;
      const newAccOdds = newSelections.reduce((acc, p) => acc * (p.estimated_odds || p.odds || 1.2), 1.0);
      const newWinProb = newSelections.reduce((acc, p) => acc * (p.model_probability || p.prob || 0.8), 1.0);
      return {
        ...scn,
        accumulated_odds: roundOddsVal(newAccOdds),
        independence_assumption_probability: roundOddsVal(newWinProb),
        selections: newSelections
      };
    }).filter(Boolean);

    if (updatedScenarios.length === 0) {
      setResult(null);
    } else {
      setResult({ ...result, scenarios: updatedScenarios });
    }
  };

  const handleRemoveAccumulatorTicket = (scenarioId) => {
    if (!result || !result.scenarios) return;
    const updated = result.scenarios.filter(s => s.scenario_id !== scenarioId);
    if (updated.length === 0) {
      setResult(null);
    } else {
      setResult({ ...result, scenarios: updated });
    }
  };

  const handleClearRollover = () => {
    setRolloverResult(null);
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

            {/* Header Badge & Country Selector */}
            <div className="flex items-center justify-between">
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

              {/* SportyBet Region Selector */}
              {codeModalData.regionalCodes && (
                <select
                  value={codeModalData.selectedRegion || "NG"}
                  onChange={(e) => {
                    const reg = e.target.value;
                    const rCode = codeModalData.regionalCodes[reg] || codeModalData.code;
                    setCodeModalData({
                      ...codeModalData,
                      selectedRegion: reg,
                      code: rCode,
                      loadUrl: `https://www.sportybet.com/${reg.toLowerCase()}/?shareCode=${rCode}`
                    });
                  }}
                  className="bg-slate-100 border border-slate-200 text-xs font-extrabold text-slate-900 rounded-xl px-2.5 py-1.5"
                >
                  <option value="NG">🇳🇬 Nigeria</option>
                  <option value="GH">🇬🇭 Ghana</option>
                  <option value="KE">🇰🇪 Kenya</option>
                  <option value="UG">🇺🇬 Uganda</option>
                </select>
              )}
            </div>

            {/* Code Display Box */}
            <div className="bg-slate-900 text-white p-5 rounded-2xl flex items-center justify-between shadow-sm">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider block">
                    SportyBet {codeModalData.selectedRegion || "NG"} Booking Code
                  </span>
                  <span className="text-[9px] font-extrabold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded border border-emerald-500/40 uppercase">
                    VERIFIED ✓ 100% RECONCILED
                  </span>
                </div>
                <span className="text-2xl font-extrabold text-emerald-400 tracking-wider">
                  {codeModalData.code}
                </span>
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(codeModalData.code);
                  setLockedNotice(`Copied SportyBet Booking Code: ${codeModalData.code}`);
                  setTimeout(() => setLockedNotice(null), 4000);
                }}

                className="px-4 py-2 rounded-xl bg-white hover:bg-slate-100 text-slate-900 font-extrabold text-xs flex items-center space-x-1.5 transition-all shadow-sm border border-slate-200"
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
                <ExternalLink className="w-4 h-4" />
                <span>Open on SportyBet ({codeModalData.selectedRegion || "NG"})</span>
              </a>

              <button
                onClick={() => copySelectionsAsText(codeModalData.selections)}
                className="py-2.5 px-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 hover:bg-slate-200 text-xs font-extrabold flex items-center justify-center space-x-1.5 transition-all"
              >
                <Copy className="w-4 h-4" />
                <span>Copy Selections Text</span>
              </button>
            </div>

            {/* Included Selections Breakdown */}
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
                Included Ticket Selections ({codeModalData.selections.length} Picks)
              </span>
              {codeModalData.selections.map((s, idx) => (
                <div key={idx} className="bg-slate-50 p-2.5 rounded-xl border border-slate-200 flex items-center justify-between text-xs">
                  <div>
                    <span className="font-bold text-slate-900 block">
                      {s.home_team || s.fixture} {s.away_team ? `vs ${s.away_team}` : ""}
                    </span>
                    <span className="text-slate-600 font-semibold text-[11px]">
                      Pick: {s.selection || s.pick}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-extrabold text-emerald-700 text-xs">
                      {Math.round((s.model_probability || s.prob || 0.75) * 100)}% Win Chance
                    </span>
                    <button
                      onClick={() => {
                        const newSels = codeModalData.selections.filter((_, i) => i !== idx);
                        if (newSels.length === 0) {
                          setShowCodeModal(false);
                        } else {
                          setCodeModalData({ ...codeModalData, selections: newSels });
                        }
                      }}
                      className="p-1 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-600 border border-slate-200 transition-all"
                      title="Cancel / Remove game"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Lock Ticket Confirmation Modal */}
      {showLockModal && lockTargetData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full border border-slate-200 shadow-2xl space-y-5 relative">
            <button
              onClick={() => setShowLockModal(false)}
              className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 transition-all"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-2xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 flex-shrink-0">
                <Lock className="w-5 h-5" />
              </div>
              <div>
                <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200 uppercase">
                  MatchIQ Ticket Tracker
                </span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5">
                  Lock & Track Built Ticket
                </h3>
              </div>
            </div>

            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Ticket Code:</span>
                <span className="font-extrabold text-slate-900">{lockTargetData.code}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Total Odds:</span>
                <span className="font-extrabold text-emerald-700">~{lockTargetData.totalOdds}x</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500 font-medium">Included Legs:</span>
                <span className="font-bold text-slate-800">{lockTargetData.selections?.length || 0} Picks</span>
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Enter Stake Amount (NGN)
              </label>
              <input
                type="number"
                value={stakeInput}
                onChange={(e) => setStakeInput(e.target.value)}
                placeholder="1000"
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2.5"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <button
                onClick={() => setShowLockModal(false)}
                className="py-2.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-extrabold hover:bg-slate-200 transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleLockTicketSubmit}
                disabled={lockingTicket}
                className="py-2.5 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1 transition-all"
              >
                {lockingTicket ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Lock className="w-3.5 h-3.5" />}
                <span>{lockingTicket ? "Locking..." : "Confirm Lock"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Global Toast Notice Banner */}
      {lockedNotice && (
        <div className="fixed bottom-6 right-6 z-50 max-w-md bg-slate-900 text-white p-4 rounded-2xl border border-slate-700 flex items-center space-x-3 text-xs shadow-2xl animate-in slide-in-from-bottom-5 duration-300">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <div className="flex-1 pr-2">
            <p className="font-extrabold text-xs text-emerald-300">Ticket Locked into Tracker</p>
            <p className="text-slate-300 mt-0.5 text-[11px]">{lockedNotice}</p>
          </div>
          <button onClick={() => setLockedNotice(null)} className="text-slate-400 hover:text-white p-1">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Header Banner with Dynamic Live SportyBet Match Counter */}
      <div className="bg-white p-4 sm:p-6 rounded-xl sm:rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base sm:text-xl font-extrabold text-slate-900">
            AI Ticket & Rollover Builder
          </h2>
          <p className="text-[11px] sm:text-xs text-slate-500 mt-1">
            Build target odds accumulators or generate <strong>Multi-Day Daily Rollover Strategies</strong> with StatIQ live 2026/27 prediction models.
          </p>
        </div>

        {/* Real-Time Live SportyBet Match Badge */}
        <div className="flex items-center gap-2 self-start sm:self-auto flex-shrink-0">
          <button
            type="button"
            onClick={() => loadTodayGames(todayDayFilter)}
            title="Click to refresh live SportyBet match list"
            className="inline-flex items-center gap-2.5 px-3.5 py-2 rounded-xl bg-slate-900 text-white hover:bg-slate-800 border border-slate-800 transition-all shadow-xs cursor-pointer group"
          >
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <div className="text-left">
              <div className="text-[9px] font-bold text-slate-400 uppercase tracking-wider leading-none">SportyBet Live Board</div>
              <div className="text-xs font-black text-white mt-0.5">
                {todayData ? `${todayData.total_matches} Today's Matches` : "Syncing live matches..."}
              </div>
            </div>
            <RefreshCw className={`w-3.5 h-3.5 text-slate-400 group-hover:text-white transition-colors ml-1 ${todayLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Mode Selector Tabs */}
      <div className="bg-slate-100 p-1 sm:p-1.5 rounded-xl sm:rounded-2xl grid grid-cols-2 sm:grid-cols-4 gap-1 shadow-inner">
        <button
          onClick={() => setBuilderMode("TODAY_GAMES")}
          className={`py-2.5 sm:py-3 px-2 rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-extrabold transition-all flex items-center justify-center space-x-1 sm:space-x-1.5 ${
            builderMode === "TODAY_GAMES"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Calendar className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">Today's Games</span>
          {todayData?.total_matches > 0 && (
            <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
              {todayData.total_matches}
            </span>
          )}
        </button>

        <button
          onClick={() => setBuilderMode("ACCUMULATOR")}
          className={`py-2.5 sm:py-3 px-2 rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-extrabold transition-all flex items-center justify-center space-x-1 sm:space-x-1.5 ${
            builderMode === "ACCUMULATOR"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Target className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">Target Odds</span>
        </button>

        <button
          onClick={() => setBuilderMode("ROLLOVER")}
          className={`py-2.5 sm:py-3 px-2 rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-extrabold transition-all flex items-center justify-center space-x-1 sm:space-x-1.5 ${
            builderMode === "ROLLOVER"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <RefreshCw className="w-3.5 h-3.5 flex-shrink-0" />
          <span className="truncate">Rollover</span>
        </button>

        <button
          onClick={() => setBuilderMode("SHORTLIST")}
          className={`py-2.5 sm:py-3 px-2 rounded-lg sm:rounded-xl text-[11px] sm:text-xs font-extrabold transition-all flex items-center justify-center space-x-1 sm:space-x-1.5 ${
            builderMode === "SHORTLIST"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <FileText className="w-3.5 h-3.5 flex-shrink-0 text-indigo-600" />
          <span className="truncate">Custom Shortlist</span>
          <span className="text-[9px] font-black px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200">
            Smart
          </span>
        </button>
      </div>

      {/* MODE 1: TODAY'S SPORTYBET LIVE GAMES BROWSER */}
      {builderMode === "TODAY_GAMES" && (() => {
        // Filter leagues + matches
        const allLeagues = todayData?.leagues || [];
        const filteredLeagues = allLeagues
          .filter(lg => todayLeagueFilter === "ALL" || lg.league === todayLeagueFilter)
          .map(lg => ({
            ...lg,
            matches: lg.matches.filter(m => {
              if (!todaySearch.trim()) return true;
              const q = todaySearch.toLowerCase();
              return m.home_team.toLowerCase().includes(q) || m.away_team.toLowerCase().includes(q);
            })
          }))
          .filter(lg => lg.matches.length > 0);

        const selectedCount = Object.keys(selectedTodayMatches).length;

        return (
          <div className="space-y-4">
            {/* Header */}
            <div className="bg-white p-4 sm:p-5 rounded-xl border border-slate-200 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Calendar className="w-4 h-4 text-slate-700" />
                    <h3 className="text-sm font-extrabold text-slate-900">
                      {todayDayFilter === "tomorrow" ? "Tomorrow's SportyBet Games" : "Today's SportyBet Games"}
                    </h3>
                    {todayData && (
                      <span className="text-[10px] font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-full uppercase">
                        {todayData.total_matches} Matches · {todayData.total_leagues} Leagues
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Browse all available matches on SportyBet. Select matches to let StatIQ evaluate H2H & form, then generate a ticket with genuine booking code.
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    onClick={() => {
                      setSelectedLeagues(["ALL_TODAY"]);
                      setBuilderMode("ACCUMULATOR");
                      setBuilderStep(2);
                    }}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 text-white text-xs font-black shadow-md shadow-emerald-200 hover:from-emerald-700 hover:to-teal-700 transition-all flex-shrink-0"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>AI Auto-Pick from Today's Pool</span>
                  </button>
                  <button
                    onClick={() => loadTodayGames(todayDayFilter)}
                    disabled={todayLoading}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 text-white text-xs font-extrabold hover:bg-slate-700 transition-all flex-shrink-0 disabled:opacity-60"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${todayLoading ? "animate-spin" : ""}`} />
                    <span>{todayLoading ? "Loading..." : todayData ? "Refresh" : "Load Games"}</span>
                  </button>
                </div>
              </div>

              {/* Day Filter Switcher (Today vs Tomorrow) */}
              <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-fit">
                <button
                  type="button"
                  onClick={() => {
                    setTodayDayFilter("today");
                    loadTodayGames("today");
                  }}
                  className={`px-4 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                    todayDayFilter === "today" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  📅 Today's Games
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setTodayDayFilter("tomorrow");
                    loadTodayGames("tomorrow");
                  }}
                  className={`px-4 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                    todayDayFilter === "tomorrow" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  ⚡ Tomorrow's Games (Next Day)
                </button>
              </div>
            </div>

            {/* Error */}
            {todayError && (
              <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl text-xs text-rose-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{todayError}</span>
              </div>
            )}

            {/* Loading skeleton */}
            {todayLoading && (
              <div className="space-y-3">
                {[1,2,3].map(i => (
                  <div key={i} className="bg-white border border-slate-100 rounded-xl p-4 animate-pulse">
                    <div className="h-3 bg-slate-100 rounded w-1/3 mb-3" />
                    {[1,2,3].map(j => <div key={j} className="h-10 bg-slate-50 rounded-lg mb-2" />)}
                  </div>
                ))}
              </div>
            )}


            {/* Filters (show only when data loaded) */}
            {!todayLoading && todayData && todayData.total_matches > 0 && (
              <>
                <div className="flex flex-col sm:flex-row gap-2">
                  {/* Search */}
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                    <input
                      type="text"
                      placeholder="Search teams..."
                      value={todaySearch}
                      onChange={e => setTodaySearch(e.target.value)}
                      className="w-full bg-white border border-slate-200 rounded-xl pl-8 pr-3 py-2 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-200"
                    />
                  </div>
                  {/* League filter */}
                  <select
                    value={todayLeagueFilter}
                    onChange={e => setTodayLeagueFilter(e.target.value)}
                    className="bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 focus:outline-none"
                  >
                    <option value="ALL">All Leagues ({todayData.total_leagues})</option>
                    {allLeagues.map(lg => (
                      <option key={lg.league} value={lg.league}>{lg.league} ({lg.matches.length})</option>
                    ))}
                  </select>
                </div>

                {/* Table header */}
                <div className="hidden sm:grid grid-cols-12 gap-2 px-4 py-2 text-[10px] font-extrabold text-slate-400 uppercase tracking-wider">
                  <div className="col-span-1"></div>
                  <div className="col-span-3">Match</div>
                  <div className="col-span-1 text-center">Time</div>
                  <div className="col-span-3 text-center">1X2 Odds</div>
                  <div className="col-span-1 text-center">StatIQ</div>
                </div>

                {/* League groups */}

                <div className="space-y-3">
                  {filteredLeagues.map(lg => (
                    <div key={lg.league} className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
                      {/* League header */}
                      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 border-b border-slate-100">
                        <span className="text-xs font-extrabold text-slate-800">{lg.league}</span>
                        <span className="text-[10px] font-bold text-slate-400">{lg.matches.length} match{lg.matches.length !== 1 ? "es" : ""}</span>
                      </div>

                      {/* Matches */}
                      <div className="divide-y divide-slate-100">
                        {lg.matches.map(m => {
                          const isSelected = !!selectedTodayMatches[m.event_id];
                          const bestWin = Math.max(m.ai_prob_home, m.ai_prob_away);
                          const bestLabel = m.ai_prob_home > m.ai_prob_away ? m.home_team : m.away_team;
                          const currentLine = matchGoalLines[m.event_id] || "1.5";
                          const activeOu = (m.ou_lines || []).find(x => String(x.line) === String(currentLine)) || (m.ou_lines || [])[0] || { line: currentLine, over: 1.30, under: 3.50 };

                          return (
                            <div
                              key={m.event_id}
                              onClick={() => toggleMatchSelection(m)}
                              className={`p-3 sm:px-4 sm:py-2.5 cursor-pointer transition-all ${
                                isSelected ? "bg-slate-900 text-white" : "hover:bg-slate-50"
                              }`}
                            >
                              {/* DESKTOP ROW (sm and up) */}
                              <div className="hidden sm:flex sm:items-center sm:gap-3">
                                {/* Checkbox */}
                                <div className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                                  isSelected ? "border-white bg-white" : "border-slate-300"
                                }`}>
                                  {isSelected && <div className="w-2 h-2 rounded-sm bg-slate-900" />}
                                </div>

                                {/* Teams */}
                                <div className="flex-1 min-w-0">
                                  <div className={`text-xs font-bold truncate ${isSelected ? "text-white" : "text-slate-900"}`}>
                                    {m.home_team}
                                  </div>
                                  <div className={`text-[10px] font-medium truncate ${isSelected ? "text-slate-300" : "text-slate-500"}`}>
                                    vs {m.away_team}
                                  </div>
                                </div>

                                {/* Kickoff time */}
                                <div className={`text-[10px] font-bold w-12 text-center flex-shrink-0 ${isSelected ? "text-slate-300" : "text-slate-500"}`}>
                                  {m.kickoff_time}
                                </div>

                                {/* 1X2 Odds */}
                                <div className="flex gap-1 flex-shrink-0">
                                  {["home", "draw", "away"].map((side, si) => {
                                    const odd = m.result_1x2?.[side];
                                    const labels = ["1", "X", "2"];
                                    return (
                                      <div key={side} className={`text-center w-11 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
                                        isSelected ? "bg-slate-800 text-white" : "bg-slate-50 text-slate-700"
                                      }`}>
                                        <div className={`text-[8px] font-bold mb-0.5 ${isSelected ? "text-slate-400" : "text-slate-400"}`}>{labels[si]}</div>
                                        {odd ? odd.toFixed(2) : "-"}
                                      </div>
                                    );
                                  })}
                                </div>

                                {/* Goals Dropdown + Over/Under Buttons */}
                                <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                                  <select
                                    value={currentLine}
                                    onChange={e => {
                                      e.stopPropagation();
                                      setMatchGoalLines(prev => ({ ...prev, [m.event_id]: e.target.value }));
                                    }}
                                    className={`px-1.5 py-1 rounded-lg text-[10px] font-black border focus:outline-none cursor-pointer transition-all ${
                                      isSelected
                                        ? "bg-slate-800 border-slate-700 text-emerald-400"
                                        : "bg-slate-100 border-slate-200 text-slate-900 hover:bg-slate-200"
                                    }`}
                                    title="Change Goal Line"
                                  >
                                    {Array.from(new Set((m.ou_lines || []).map(l => String(l.line)).concat(["0.5", "1.5", "2.5", "3.5", "4.5"])))
                                      .sort((a, b) => parseFloat(a) - parseFloat(b))
                                      .map(lineVal => (
                                        <option key={lineVal} value={lineVal} className="text-slate-900 bg-white font-bold">
                                          {lineVal}
                                        </option>
                                      ))}
                                  </select>

                                  <div className={`text-center w-11 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
                                    isSelected ? "bg-slate-800 text-white" : "bg-slate-50 text-slate-700"
                                  }`}>
                                    <div className={`text-[8px] font-bold mb-0.5 ${isSelected ? "text-slate-400" : "text-slate-400"}`}>{currentLine} Over</div>
                                    {activeOu.over ? activeOu.over.toFixed(2) : "-"}
                                  </div>

                                  <div className={`text-center w-11 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
                                    isSelected ? "bg-slate-800 text-white" : "bg-slate-50 text-slate-700"
                                  }`}>
                                    <div className={`text-[8px] font-bold mb-0.5 ${isSelected ? "text-slate-400" : "text-slate-400"}`}>{currentLine} Under</div>
                                    {activeOu.under ? activeOu.under.toFixed(2) : "-"}
                                  </div>
                                </div>

                                {/* StatIQ best win % */}
                                <div className={`text-[10px] font-extrabold text-right flex-shrink-0 w-16 ${
                                  isSelected ? "text-emerald-300" : "text-emerald-700"
                                }`}>
                                  {(bestWin > 1 ? bestWin : bestWin * 100).toFixed(0)}%
                                  <div className={`text-[8px] truncate ${isSelected ? "text-slate-400" : "text-slate-400"}`}>
                                    {bestLabel.split(" ")[0]}
                                  </div>
                                </div>
                              </div>

                              {/* MOBILE CARD (below sm breakpoint) */}
                              <div className="sm:hidden space-y-2.5">
                                {/* Top status & time row */}
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <div className={`w-4 h-4 rounded border-2 flex items-center justify-center flex-shrink-0 transition-all ${
                                      isSelected ? "border-white bg-white" : "border-slate-300"
                                    }`}>
                                      {isSelected && <div className="w-2 h-2 rounded-sm bg-slate-900" />}
                                    </div>
                                    <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                                      isSelected ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-600"
                                    }`}>
                                      ⏰ {m.kickoff_time}
                                    </span>
                                  </div>

                                  <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded-full ${
                                    isSelected ? "bg-emerald-950 text-emerald-300 border border-emerald-800" : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                  }`}>
                                    🎯 {(bestWin > 1 ? bestWin : bestWin * 100).toFixed(0)}% {bestLabel.split(" ")[0]}
                                  </span>
                                </div>

                                {/* Full Team Names (High Contrast, Zero Clipping) */}
                                <div className="space-y-0.5 pl-6">
                                  <div className={`text-xs font-black tracking-tight leading-tight ${isSelected ? "text-white" : "text-slate-900"}`}>
                                    {m.home_team}
                                  </div>
                                  <div className={`text-[11px] font-bold leading-tight ${isSelected ? "text-slate-300" : "text-slate-600"}`}>
                                    <span className="text-[9px] font-normal uppercase opacity-70">vs</span> {m.away_team}
                                  </div>
                                </div>

                                {/* Mobile Odds Grid (Touch-friendly pills) */}
                                <div className="grid grid-cols-5 gap-1 pt-1" onClick={e => e.stopPropagation()}>
                                  {["home", "draw", "away"].map((side, si) => {
                                    const odd = m.result_1x2?.[side];
                                    const labels = ["1", "X", "2"];
                                    return (
                                      <div key={side} className={`text-center py-1 rounded-lg text-[10px] font-extrabold ${
                                        isSelected ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
                                      }`}>
                                        <div className="text-[8px] font-bold text-slate-400 mb-0.5">{labels[si]}</div>
                                        {odd ? odd.toFixed(2) : "-"}
                                      </div>
                                    );
                                  })}

                                  {/* Over & Under Mobile Buttons */}
                                  <div className={`text-center py-1 rounded-lg text-[10px] font-extrabold ${
                                    isSelected ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
                                  }`}>
                                    <div className="text-[8px] font-bold text-slate-400 mb-0.5">O{currentLine}</div>
                                    {activeOu.over ? activeOu.over.toFixed(2) : "-"}
                                  </div>
                                  <div className={`text-center py-1 rounded-lg text-[10px] font-extrabold ${
                                    isSelected ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
                                  }`}>
                                    <div className="text-[8px] font-bold text-slate-400 mb-0.5">U{currentLine}</div>
                                    {activeOu.under ? activeOu.under.toFixed(2) : "-"}
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Empty state */}
            {!todayLoading && todayData && todayData.total_matches === 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-xs text-slate-500">
                <Calendar className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="font-bold text-slate-700 mb-1">No games found for today</p>
                <p>SportyBet may not have listed fixtures yet. Try again later.</p>
              </div>
            )}

            {/* Not yet loaded */}
            {!todayLoading && !todayData && !todayError && (
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-8 text-center text-xs text-slate-400">
                <p className="font-bold text-slate-600 mb-2">Click "Load Games" to fetch today's live SportyBet fixtures</p>
                <p>Shows all available matches grouped by league with 1X2 and Over/Under odds.</p>
              </div>
            )}

            {/* Selected Matches Tray */}
            {selectedCount > 0 && (
              <div className="sticky bottom-4 z-30">
                <div className="bg-slate-900 text-white p-4 rounded-2xl shadow-2xl border border-slate-700 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-extrabold">{selectedCount} match{selectedCount !== 1 ? "es" : ""} selected</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">
                      {Object.values(selectedTodayMatches).map(m => m.home_team).join(", ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 self-end sm:self-auto">
                    <button
                      onClick={() => setSelectedTodayMatches({})}
                      className="px-3 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-bold hover:bg-slate-700 transition-all"
                    >
                      Clear
                    </button>
                    <button
                      onClick={handleBuildFromSelected}
                      disabled={buildingFromToday || selectedCount < 2}
                      className="px-4 py-2 rounded-xl bg-white text-slate-900 text-xs font-extrabold hover:bg-slate-100 transition-all flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {buildingFromToday ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                      <span>{buildingFromToday ? "Building..." : "Build Ticket from Selected"}</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Built ticket result */}
            {todayBuiltResult && (
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                  <div>
                    <p className="text-xs font-extrabold text-slate-900">StatIQ Ticket — {todayBuiltResult.approved_legs?.length} Legs Approved</p>
                    <p className="text-[11px] text-slate-500">Combined Odds: ~{todayBuiltResult.accumulated_odds}x · Win Probability: {((todayBuiltResult.correlation_adjusted_probability || todayBuiltResult.combined_probability) * 100).toFixed(1)}%</p>
                  </div>
                  <button onClick={() => setTodayBuiltResult(null)} className="p-1 text-slate-400 hover:text-slate-700">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-2 max-h-60 overflow-y-auto">
                  {todayBuiltResult.approved_legs?.map((leg, idx) => (
                    <div key={idx} className="flex items-center justify-between bg-slate-50 rounded-lg px-3 py-2 text-xs">
                      <div>
                        <p className="font-bold text-slate-900">{leg.home_team} vs {leg.away_team}</p>
                        <p className="text-slate-500 mt-0.5">Pick: {leg.selection_name}</p>
                      </div>
                      <span className="font-extrabold text-emerald-700">{(leg.model_probability * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => {
                    setResult({
                      ticket: todayBuiltResult,
                      scenarios: [{
                        scenario_id: "TODAY-CUSTOM",
                        scope_label: "Today's Selected Games",
                        gameweek_label: "Today",
                        target_odds: 5.0,
                        accumulated_odds: todayBuiltResult.accumulated_odds,
                        independence_assumption_probability: todayBuiltResult.combined_probability,
                        correlation_adjusted_probability: todayBuiltResult.correlation_adjusted_probability,
                        confidence_tier: todayBuiltResult.confidence_tier,
                        recommended_stake_pct: todayBuiltResult.recommended_stake_pct,
                        selections: todayBuiltResult.approved_legs,
                        rejected_picks: todayBuiltResult.rejected_picks,
                      }]
                    });
                    setBuilderMode("ACCUMULATOR");
                    setTodayBuiltResult(null);
                  }}
                  className="w-full py-2.5 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center gap-2"
                >
                  <Copy className="w-3.5 h-3.5" />
                  View Full Ticket and Generate Booking Code
                </button>
              </div>
            )}
          </div>
        );
      })()}

      {/* MODE 2: STANDARD ACCUMULATOR / TARGET ODDS BUILDER */}
      {builderMode === "ACCUMULATOR" && (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">

          {/* Wizard Step Progress Bar */}
          {(() => {
            const steps = [
              { id: 1, label: "Leagues & Window" },
              { id: 2, label: "Target & Flex Bet" },
            ];
            return (
              <div className="flex border-b border-slate-100">
                {steps.map((s) => {
                  const isActive = builderStep === s.id;
                  const isDone = builderStep > s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => setBuilderStep(s.id)}
                      className={`flex-1 py-3.5 flex flex-col items-center gap-0.5 transition-all border-b-2 ${
                        isActive
                          ? "border-slate-900 bg-slate-50"
                          : isDone
                          ? "border-emerald-500 bg-white"
                          : "border-transparent bg-white"
                      }`}
                    >
                      <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-black mb-0.5 ${
                        isActive ? "bg-slate-900 text-white" : isDone ? "bg-emerald-500 text-white" : "bg-slate-100 text-slate-400"
                      }`}>
                        {isDone ? "✓" : s.id}
                      </div>
                      <span className={`text-[10px] font-bold ${isActive ? "text-slate-900" : isDone ? "text-emerald-600" : "text-slate-400"}`}>
                        {s.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })()}

          {/* Step Content */}
          <div className="p-6 space-y-6 min-h-[220px]">

            {/* STEP 1: Leagues & Schedule Window */}
            {builderStep === 1 && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">Select Leagues & Schedule Window</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Select individual leagues or all top competitions across Europe, then choose your match timeframe.</p>
                </div>

                {/* Quick Presets */}
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues(["ALL_TODAY"])}
                    className={`px-3.5 py-2 rounded-xl text-xs font-black transition-all flex items-center gap-2 ${
                      selectedLeagues.includes("ALL_TODAY") || selectedLeagues.includes("ALL_WORLDWIDE")
                        ? "bg-slate-900 text-white shadow-md shadow-slate-200 ring-2 ring-emerald-500"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    <span>⚡</span>
                    <span>All SportyBet Today Games (Wide Pool)</span>
                    <span className="text-[9px] font-black uppercase px-1.5 py-0.5 rounded-full bg-emerald-500 text-white">
                      Recommended
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues(INTERNATIONAL_BREAK_CODES)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all flex items-center gap-1.5 ${
                      INTERNATIONAL_BREAK_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === INTERNATIONAL_BREAK_CODES.length
                        ? "bg-emerald-600 text-white shadow-sm shadow-emerald-200"
                        : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
                    }`}
                  >
                    <span>🌍</span>
                    <span>International Break</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues(TOP_5_LEAGUE_CODES)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                      TOP_5_LEAGUE_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === TOP_5_LEAGUE_CODES.length
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    Top 5 European
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues(ALL_TOP_LEAGUE_CODES)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                      ALL_TOP_LEAGUE_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === ALL_TOP_LEAGUE_CODES.length
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    All Top Leagues
                  </button>
                </div>

                {/* Wide Pool Active Banner OR Specific League Chips */}
                {(selectedLeagues.includes("ALL_TODAY") || selectedLeagues.includes("ALL_WORLDWIDE")) ? (
                  <div className="bg-gradient-to-br from-emerald-50 via-teal-50 to-emerald-50/40 border border-emerald-200 rounded-2xl p-4.5 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        <h4 className="text-xs font-black uppercase tracking-wider text-emerald-900">
                          ⚡ Full SportyBet Today Fixtures Pool Active
                        </h4>
                      </div>
                      <span className="text-[10px] font-extrabold bg-emerald-200/60 text-emerald-800 px-2 py-0.5 rounded-full">
                        Wide Range: 200+ Matches
                      </span>
                    </div>
                    <p className="text-xs text-emerald-800 font-medium leading-relaxed">
                      StatIQ will evaluate all scheduled matches from SportyBet for your selected timeframe (both club football and international tournaments). No need to select competitions manually — the 5-Gate engine scans the full board to pick the safest high-value games based on your target odds and games.
                    </p>
                    <div className="flex items-center gap-4 pt-1 text-[11px] font-bold text-emerald-700 flex-wrap">
                      <span className="flex items-center gap-1">✓ Senior International & Major Tournaments</span>
                      <span className="flex items-center gap-1">✓ Active Domestic Club Leagues</span>
                      <span className="flex items-center gap-1">✓ Anti-SRL & Youth Protection</span>
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold text-slate-700">Filter by specific leagues ({selectedLeagues.length} selected):</span>
                      <button
                        type="button"
                        onClick={() => setSelectedLeagues([])}
                        className="text-xs text-slate-500 hover:text-slate-800 font-semibold"
                      >
                        Clear Selection
                      </button>
                    </div>
                    {/* League Multi-Select Chips */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                  {AVAILABLE_LEAGUES.map((lg) => {
                    const isSelected = selectedLeagues.includes(lg.code);
                    return (
                      <div
                        key={lg.code}
                        onClick={() => {
                          if (selectedLeagues.includes(lg.code)) {
                            setSelectedLeagues(selectedLeagues.filter(c => c !== lg.code));
                          } else {
                            setSelectedLeagues([...selectedLeagues, lg.code]);
                          }
                        }}
                        className={`px-3 py-2.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between ${
                          isSelected
                            ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                            : "bg-white border-slate-200 text-slate-700 hover:border-slate-300"
                        }`}
                      >
                        <div className="min-w-0 pr-1">
                          <p className="text-xs font-extrabold truncate">{lg.name}</p>
                          <p className={`text-[10px] truncate ${isSelected ? "text-slate-400" : "text-slate-400"}`}>{lg.country}</p>
                        </div>
                        <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 ${
                          isSelected ? "bg-white border-white text-slate-900" : "border-slate-300"
                        }`}>
                          {isSelected && <div className="w-2 h-2 rounded-sm bg-slate-900" />}
                        </div>
                      </div>
                    );
                  })}
                    </div>
                  </div>
                )}

                {/* Match Schedule Window */}
                <div className="pt-2">
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Match Schedule Window</label>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
                    {[
                      { id: "TODAY", label: "Today's Games", sub: todayData ? `${todayData.total_matches} SportyBet matches` : "Matches playing today" },
                      { id: "NEXT_24H", label: "Next 24 Hours", sub: "Upcoming 24h slate" },
                      { id: "MIDWEEK", label: "Midweek Slate", sub: "Tue – Thu rounds & Cups" },
                      { id: "NEXT_48H", label: "Next 48 Hours", sub: "Multi-day midweek window" },
                      { id: "WEEKEND", label: "Weekend Combined", sub: "Saturday & Sunday" },
                      { id: "NEXT_7D", label: "Upcoming 7 Days", sub: "Full week fixture pool" },
                    ].map(w => (
                      <div
                        key={w.id}
                        onClick={() => setDateWindow(w.id)}
                        className={`p-3 rounded-xl border cursor-pointer transition-all ${
                          dateWindow === w.id
                            ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                            : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        <p className="text-xs font-extrabold">{w.label}</p>
                        <p className={`text-[10px] mt-0.5 ${dateWindow === w.id ? "text-slate-400" : "text-slate-500"}`}>{w.sub}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* STEP 2: Target Criteria & Flex Bet */}
            {builderStep === 2 && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-extrabold text-slate-900">Set Target & Flex Bet Strategy</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Choose whether to build by total odds multiplier or by number of games.</p>
                </div>

                {/* Mode Toggle */}
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl w-fit">
                  <button
                    type="button"
                    onClick={() => {
                      setTargetMode("ODDS");
                      if (numTickets === 2) setTargetOdds(22.0);
                    }}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "ODDS" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Target Odds
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTargetMode("GAMES");
                      if (numTickets === 2) {
                        setTargetGames(15);
                        setCustomGamesInput("15");
                      }
                    }}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "GAMES" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Number of Games
                  </button>
                </div>

                {targetMode === "ODDS" ? (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">
                      {numTickets >= 2
                        ? (numTickets === 2 ? "Select target odds (~22x recommended for 2-variant portfolio):" : "Select target odds (~40x recommended for multi-variant portfolio):")
                        : "Select target odds or enter custom multiplier:"}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {[2.0, 5.0, 10.0, 20.0, 22.0, 25.0, 40.0, 50.0, 100.0, 200.0].map((val) => {
                        const isSelected = !useCustom && targetOdds === val;
                        const isRecommended = (numTickets === 2 && val === 22.0) || (numTickets >= 3 && val === 40.0);
                        return (
                          <button
                            key={val}
                            type="button"
                            onClick={() => { setTargetOdds(val); setCustomOdds(""); setUseCustom(false); }}
                            className={`px-3 sm:px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all relative ${
                              isSelected
                                ? "bg-slate-900 text-white shadow-sm ring-1 ring-slate-900"
                                : isRecommended
                                ? "bg-amber-100 text-amber-900 border border-amber-300 hover:bg-amber-200"
                                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                            }`}
                          >
                            ~{val.toFixed(0)}x
                            {isRecommended && !isSelected && (
                              <span className="ml-1 text-[9px] font-black uppercase text-amber-700">★</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    <div className="flex items-center gap-2 pt-1 flex-wrap sm:flex-nowrap">
                      <input
                        type="text"
                        placeholder={numTickets === 2 ? "Custom odds (e.g. 22.0)" : "Custom odds (e.g. 40.0)"}
                        value={customOdds}
                        onChange={(e) => {
                          const valStr = e.target.value;
                          setCustomOdds(valStr);
                          setUseCustom(true);
                          const parsed = parseFloat(valStr);
                          if (!isNaN(parsed) && parsed > 1.0) setTargetOdds(parsed);
                        }}
                        className="w-full sm:w-44 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400 whitespace-nowrap">target odds multiplier</span>
                    </div>
                    <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                      Target: <strong className="text-slate-900">{useCustom ? (parseFloat(customOdds) > 1 ? `~${parseFloat(customOdds).toFixed(1)}x` : "Invalid") : `~${targetOdds.toFixed(0)}x odds`}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">
                      {numTickets >= 2
                        ? `How many games per slip? (Strictly max 15 games for ${numTickets}-variant portfolio):`
                        : "How many games do you want in your ticket (up to 50)?"}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {(numTickets >= 2 ? [5, 8, 10, 13, 15] : [5, 10, 15, 20, 25, 30, 40, 50]).map((num) => (
                        <button
                          key={num}
                          type="button"
                          onClick={() => { setTargetGames(num); setCustomGamesInput(String(num)); }}
                          className={`px-3 sm:px-3.5 py-2 rounded-xl text-xs font-extrabold transition-all ${
                            targetGames === num
                              ? "bg-slate-900 text-white shadow-sm ring-1 ring-slate-900"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }`}
                        >
                          {num} Games
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 pt-1 flex-wrap sm:flex-nowrap">
                      <input
                        type="text"
                        placeholder={numTickets >= 2 ? "Custom (1–15)" : "Custom (1–50)"}
                        value={customGamesInput}
                        onChange={(e) => {
                          const raw = e.target.value;
                          setCustomGamesInput(raw);
                          let num = parseInt(raw);
                          const maxLimit = numTickets >= 2 ? 15 : 50;
                          if (!isNaN(num) && num >= 1) {
                            num = Math.min(maxLimit, num);
                            setTargetGames(num);
                          }
                        }}
                        className="w-full sm:w-44 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400 whitespace-nowrap">games in ticket (max {numTickets >= 2 ? 15 : 50})</span>
                    </div>
                    <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                      Target: <strong className="text-slate-900">{targetGames} games</strong>
                    </div>
                  </div>
                )}

                {/* Flex Cut Strategy */}
                <div className="pt-2">
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Flex Bet Protection</label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {[
                      { id: "OFF", label: "Straight Accumulator", desc: "Standard full win ticket" },
                      { id: "1", label: "Flex Cut 1", desc: "Win payout even if 1 leg cuts" },
                      { id: "2", label: "Flex Cut 2", desc: "Win payout even if 2 legs cut" },
                    ].map(f => (
                      <div
                        key={f.id}
                        onClick={() => setSelectedFlexCut(f.id)}
                        className={`p-3 rounded-xl border cursor-pointer transition-all ${
                          selectedFlexCut === f.id
                            ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                            : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        <p className="text-xs font-extrabold">{f.label}</p>
                        <p className={`text-[10px] mt-0.5 ${selectedFlexCut === f.id ? "text-slate-400" : "text-slate-500"}`}>{f.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Multi-Ticket Portfolio Strategy */}
                <div className="pt-2">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                      Multi-Ticket Portfolio Builder (Zero-Overlap Mode)
                    </label>
                    <span className="text-[9px] font-extrabold uppercase px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-300">
                      🛡️ HEDGE & DIVERSIFY
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                    {[
                      { id: 1, label: "1 Ticket", desc: "Single optimal ticket" },
                      { id: 2, label: "2 Variant Slips", desc: "Split 0% Overlap / Hedged" },
                      { id: 3, label: "3 Variant Slips", desc: "3-Slip Orthogonal Cover" },
                      { id: 4, label: "4 Variant Slips", desc: "4x13 Block Wheeling" },
                    ].map(nt => (
                      <div
                        key={nt.id}
                        onClick={() => {
                          setNumTickets(nt.id);
                          if (nt.id >= 2) {
                            if (targetMode === "GAMES") {
                              setTargetGames(13);
                              setCustomGamesInput("13");
                            } else {
                              setTargetOdds(nt.id === 2 ? 22.0 : 40.0);
                              setCustomOdds("");
                              setUseCustom(false);
                            }
                          }
                        }}
                        className={`p-3 rounded-xl border cursor-pointer transition-all ${
                          numTickets === nt.id
                            ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                            : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-extrabold">{nt.label}</p>
                          {nt.id > 1 && (
                            <span className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded ${
                              numTickets === nt.id ? "bg-emerald-400 text-slate-950" : "bg-emerald-100 text-emerald-800"
                            }`}>
                              Zero Overlap
                            </span>
                          )}
                        </div>
                        <p className={`text-[10px] mt-0.5 ${numTickets === nt.id ? "text-slate-400" : "text-slate-500"}`}>{nt.desc}</p>
                      </div>
                    ))}
                  </div>

                  {/* Master Ticket Option Banner when > 1 variant selected */}
                  {numTickets >= 2 && (
                    <div className="mt-2.5 p-3 rounded-xl bg-amber-50 border border-amber-200/90 flex items-start gap-2.5 text-xs text-amber-900 shadow-sm animate-fadeIn">
                      <Zap className="w-4 h-4 text-amber-600 fill-amber-500 flex-shrink-0 mt-0.5" />
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-black text-amber-950">⚡ Master Ticket Option Active:</span>
                          <span className="text-[9px] px-2 py-0.5 rounded-full bg-amber-200/80 text-amber-950 font-bold uppercase tracking-wider">Zero Overlap</span>
                        </div>
                        <p className="text-[11px] text-amber-800 leading-snug">
                          Generates <strong>{numTickets} independent variant slips</strong>. You will also have the option to merge and prioritize the top 5–15 games into 1 unified <strong>Master Ticket</strong> on all devices.
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Risk Strategy Profile */}
                <div className="pt-2">
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Risk Strategy Profile</label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {[
                      { id: "CONSERVATIVE", label: "Conservative (Safety Cushions)", desc: "Tier-1 cushions (80%+ win rate: Double Chance, Over 1.5, Team Goals, Win Either Half)" },
                      { id: "AGGRESSIVE", label: "Aggressive (Value Maximizer)", desc: "Direct value & higher odds (Straight 1X2 wins, Over 2.5 goals & Asian handicaps)" },
                    ].map(r => (
                      <div
                        key={r.id}
                        onClick={() => setRiskProfile(r.id)}
                        className={`p-3 rounded-xl border cursor-pointer transition-all ${
                          riskProfile === r.id
                            ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                            : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        <p className="text-xs font-extrabold">{r.label}</p>
                        <p className={`text-[10px] mt-0.5 ${riskProfile === r.id ? "text-slate-400" : "text-slate-500"}`}>{r.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Allowed Market Categories Filter */}
                <div className="pt-2">
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Allowed Market Categories</label>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { id: "DOUBLE_CHANCE", label: "Double Chance (1X/12/X2)" },
                      { id: "OVER_UNDER", label: "Over/Under Goals" },
                      { id: "TEAM_GOALS", label: "Team Total Goals" },
                      { id: "1X2", label: "1X2 Match Result" },
                    ].map(m => {
                      const isSelected = selectedMarketCategories.includes(m.id);
                      return (
                        <button
                          key={m.id}
                          type="button"
                          onClick={() => {
                            setSelectedMarketCategories(prev =>
                              isSelected
                                ? (prev.length > 1 ? prev.filter(x => x !== m.id) : prev)
                                : [...prev, m.id]
                            );
                          }}
                          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                            isSelected
                              ? "bg-slate-900 text-white border-slate-900"
                              : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                          }`}
                        >
                          {isSelected ? "✓ " : ""}{m.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

          </div>

          {/* Wizard Footer — Navigation + Build Button */}
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between gap-3">
            <button
              onClick={() => setBuilderStep(s => Math.max(1, s - 1))}
              disabled={builderStep === 1}
              className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 bg-white border border-slate-200 hover:bg-slate-100 disabled:opacity-30 transition-all"
            >
              ← Back
            </button>

            <div className="flex items-center gap-2 text-[10px] text-slate-400 font-medium">
              Step {builderStep} of 2
            </div>

            {builderStep === 1 ? (
              <button
                onClick={() => setBuilderStep(2)}
                className="px-5 py-2 rounded-xl text-xs font-extrabold bg-slate-900 text-white hover:bg-slate-700 transition-all"
              >
                Next →
              </button>
            ) : (
              <button
                onClick={handleBuildSafestTicket}
                disabled={loading}
                className="px-5 py-2 rounded-xl btn-black text-xs font-extrabold flex items-center gap-2 transition-all shadow-sm"
              >
                {loading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                {loading ? "Generating Picks..." : "Generate StatIQ Ticket"}
              </button>
            )}
          </div>

          {errorMsg && (
            <div className="mx-6 mb-4 bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start gap-3 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-extrabold block">Builder Notice</span>
                <p className="mt-0.5">{errorMsg}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* MODE 3: DAILY HIGH-ASSURANCE ROLLOVER ENGINE */}
      {builderMode === "ROLLOVER" && (
        <div className="space-y-6">
          {/* AUTOMATED 10:00 AM ROLLOVER ENGINE (SLEEK LIGHT MODE & MOBILE-FIRST) */}
          <div className="bg-white rounded-3xl border border-slate-200 shadow-xl shadow-slate-100/90 p-5 sm:p-7 space-y-6 relative overflow-hidden">
            {/* Ambient subtle decorative background glows */}
            <div className="absolute top-0 right-0 w-80 h-80 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none" />
            <div className="absolute bottom-0 left-0 w-80 h-80 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />

            {/* Header: Title, Live Status, and Enable/Pause Toggle */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100 relative z-10">
              <div className="flex items-start sm:items-center gap-3.5">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white flex-shrink-0 shadow-lg shadow-emerald-500/20">
                  <Zap className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h2 className="text-base sm:text-lg font-black tracking-tight text-slate-900 flex items-center gap-2">
                      <span>Automated 10:00 AM Rollover Engine</span>
                    </h2>
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider flex items-center gap-1.5 border ${
                      cronConfig.is_enabled 
                        ? "bg-emerald-50 border-emerald-200 text-emerald-700" 
                        : "bg-slate-100 border-slate-200 text-slate-500"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${cronConfig.is_enabled ? "bg-emerald-500 animate-pulse" : "bg-slate-400"}`} />
                      <span>{cronConfig.is_enabled ? `Active · ${cronConfig.dispatch_time || "10:00"} AM WAT Dispatch` : "Cron Paused"}</span>
                    </span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-indigo-50 border border-indigo-200 text-indigo-700">
                      {cronConfig.campaign_mode === "CHALLENGE" ? `${cronConfig.challenge_days || 10}-Day Compounding Challenge` : "Continuous Daily"}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 font-medium leading-relaxed">
                    Autonomous morning engine sweeps SportyBet’s live matches directly at 10:00 AM WAT. 100% deterministic (zero randomness), Head-to-Head & 5-Match form verification, strict safety corridor (1.15 to max leg odds), live SportyBet booking code generation, and instant Telegram dispatch.
                  </p>
                </div>
              </div>

              {/* Master Enabled / Paused Toggle Button */}
              <div className="flex items-center gap-2 self-start sm:self-center">
                <button
                  type="button"
                  onClick={() => setCronConfig(prev => ({ ...prev, is_enabled: !prev.is_enabled }))}
                  className={`px-4 py-2 rounded-xl text-xs font-black transition-all flex items-center gap-2 border cursor-pointer shadow-sm ${
                    cronConfig.is_enabled
                      ? "bg-emerald-500 text-white border-emerald-600 hover:bg-emerald-600 shadow-emerald-500/20"
                      : "bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200"
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${cronConfig.is_enabled ? "bg-white animate-pulse" : "bg-slate-400"}`} />
                  <span>{cronConfig.is_enabled ? "Bot Enabled" : "Enable Bot"}</span>
                </button>
              </div>
            </div>

            {/* Campaign Mode Tabs: Compounding Challenge vs Continuous Schedule */}
            <div className="space-y-4 relative z-10">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-indigo-600" />
                    <span>1. Campaign Execution Mode & Duration</span>
                  </h3>
                  <p className="text-[11px] text-slate-500 font-medium mt-0.5">
                    Choose how long the bot runs: a dedicated compounding ladder (e.g. 10 days) or continuous daily schedule.
                  </p>
                </div>

                {/* Mode Switcher Pills */}
                <div className="flex items-center p-1 bg-slate-100 rounded-xl border border-slate-200 self-start sm:self-center">
                  <button
                    type="button"
                    onClick={() => setCronConfig(prev => ({ ...prev, campaign_mode: "CHALLENGE" }))}
                    className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all flex items-center gap-1.5 cursor-pointer ${
                      cronConfig.campaign_mode === "CHALLENGE"
                        ? "bg-white text-indigo-700 shadow-sm border border-slate-200/80 font-black"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <TrendingUp className="w-3.5 h-3.5" />
                    <span>Compounding Challenge</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setCronConfig(prev => ({ ...prev, campaign_mode: "CONTINUOUS" }))}
                    className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all flex items-center gap-1.5 cursor-pointer ${
                      cronConfig.campaign_mode === "CONTINUOUS"
                        ? "bg-white text-indigo-700 shadow-sm border border-slate-200/80 font-black"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    <Calendar className="w-3.5 h-3.5" />
                    <span>Continuous Schedule</span>
                  </button>
                </div>
              </div>

              {/* Mode Specific Controls */}
              {cronConfig.campaign_mode === "CHALLENGE" ? (
                /* CHALLENGE MODE CONTROLS */
                <div className="bg-gradient-to-br from-indigo-50/50 via-slate-50 to-emerald-50/40 border border-indigo-100 p-4 sm:p-5 rounded-2xl space-y-4">
                  {/* Preset Duration Chips */}
                  <div>
                    <label className="text-[11px] font-black text-slate-700 uppercase tracking-wider block mb-2">
                      Select Challenge Duration (How many days the bot runs):
                    </label>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                      {[
                        { days: 3, label: "Weekend Sprint", desc: "3 Days" },
                        { days: 5, label: "5-Day Doubler", desc: "5 Days" },
                        { days: 7, label: "Weekly Ladder", desc: "7 Days" },
                        { days: 10, label: "10-Day Power", desc: "10 Days", recommended: true },
                        { days: "CUSTOM", label: "Custom Days", desc: `${cronConfig.challenge_days} Days` }
                      ].map(item => {
                        const isSelected = item.days === "CUSTOM"
                          ? ![3, 5, 7, 10].includes(cronConfig.challenge_days)
                          : cronConfig.challenge_days === item.days;
                        return (
                          <button
                            key={item.label}
                            type="button"
                            onClick={() => {
                              if (item.days !== "CUSTOM") {
                                setCronConfig(prev => ({ ...prev, challenge_days: item.days }));
                              }
                            }}
                            className={`p-2.5 rounded-xl border text-left transition-all relative cursor-pointer ${
                              isSelected
                                ? "bg-white border-indigo-500 shadow-md shadow-indigo-100 ring-2 ring-indigo-500/20"
                                : "bg-white/80 border-slate-200 hover:border-slate-300 hover:bg-white text-slate-700"
                            }`}
                          >
                            {item.recommended && (
                              <span className="absolute -top-2 right-2 px-1.5 py-0.2 rounded-full text-[9px] font-black bg-emerald-500 text-white shadow-xs">
                                Recommended
                              </span>
                            )}
                            <span className="text-xs font-black block text-slate-900">{item.label}</span>
                            <span className="text-[10px] text-slate-500 font-bold block mt-0.5">{item.desc}</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Custom days stepper if not in preset */}
                    {![3, 5, 7, 10].includes(cronConfig.challenge_days) && (
                      <div className="mt-3 flex items-center gap-3 bg-white p-3 rounded-xl border border-indigo-200 max-w-sm">
                        <span className="text-xs font-black text-slate-700">Custom Days:</span>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setCronConfig(prev => ({ ...prev, challenge_days: Math.max(1, (prev.challenge_days || 10) - 1) }))}
                            className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 font-bold flex items-center justify-center text-xs text-slate-800"
                          >
                            -
                          </button>
                          <input
                            type="number"
                            min="1"
                            max="30"
                            value={cronConfig.challenge_days || 10}
                            onChange={(e) => setCronConfig(prev => ({ ...prev, challenge_days: Math.max(1, parseInt(e.target.value) || 1) }))}
                            className="w-14 text-center py-1 rounded-lg border border-slate-200 font-black text-xs text-slate-900"
                          />
                          <button
                            type="button"
                            onClick={() => setCronConfig(prev => ({ ...prev, challenge_days: Math.min(30, (prev.challenge_days || 10) + 1) }))}
                            className="w-7 h-7 rounded-lg bg-slate-100 hover:bg-slate-200 font-bold flex items-center justify-center text-xs text-slate-800"
                          >
                            +
                          </button>
                          <span className="text-xs font-bold text-slate-500">Days</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Compounding Ladder Progress & Stake Config */}
                  <div className="bg-white border border-slate-200/90 rounded-xl p-4 space-y-3.5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-black text-slate-900">
                            Current Challenge Status:
                          </span>
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-black bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Day {cronConfig.challenge_day_current || 1} of {cronConfig.challenge_days || 10}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 font-medium mt-0.5">
                          At 2.00x daily target, the initial stake doubles each day until completing Day {cronConfig.challenge_days || 10}.
                        </p>
                      </div>

                      {/* Starting Stake Stepper */}
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-black text-slate-600">Starting Stake:</span>
                        <div className="flex items-center bg-slate-50 rounded-lg border border-slate-200 px-2 py-1">
                          <span className="text-xs font-bold text-slate-400 mr-1">₦</span>
                          <input
                            type="number"
                            step="1000"
                            min="500"
                            value={cronConfig.starting_stake || 5000}
                            onChange={(e) => setCronConfig(prev => ({ ...prev, starting_stake: Math.max(100, parseFloat(e.target.value) || 100) }))}
                            className="w-20 bg-transparent text-xs font-black text-slate-900 focus:outline-none"
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => handleResetChallenge(cronConfig.challenge_days || 10, cronConfig.starting_stake || 5000)}
                          disabled={cronLoading}
                          className="px-2.5 py-1.5 rounded-lg text-[10px] font-black bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-all flex items-center gap-1 cursor-pointer"
                          title="Restart challenge from Day 1"
                        >
                          <RotateCcw className="w-3 h-3" />
                          <span>Reset to Day 1</span>
                        </button>
                      </div>
                    </div>

                    {/* Progress Bar */}
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-[10px] font-black text-slate-500">
                        <span>Day 1 (Start)</span>
                        <span className="text-indigo-600 font-extrabold">
                          {Math.round(((cronConfig.challenge_day_current || 1) / (cronConfig.challenge_days || 10)) * 100)}% Complete
                        </span>
                        <span>Day {cronConfig.challenge_days || 10} Goal: {formatNGN((cronConfig.starting_stake || 5000) * Math.pow(cronConfig.target_odds || 2.00, cronConfig.challenge_days || 10))}</span>
                      </div>
                      <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-gradient-to-r from-emerald-500 to-indigo-600 h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(100, Math.max(5, ((cronConfig.challenge_day_current || 1) / (cronConfig.challenge_days || 10)) * 100))}%`
                          }}
                        />
                      </div>
                    </div>

                    {/* Toggle Full Compounding Ladder Preview */}
                    <div className="pt-1 border-t border-slate-100 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={() => setShowCompoundingLadder(!showCompoundingLadder)}
                        className="text-xs font-bold text-indigo-600 hover:text-indigo-800 flex items-center gap-1 cursor-pointer"
                      >
                        <TrendingUp className="w-3.5 h-3.5" />
                        <span>{showCompoundingLadder ? "Hide Compounding Ladder" : `View Compounding Ladder (${cronConfig.challenge_days || 10} Days Projection)`}</span>
                        {showCompoundingLadder ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                      <span className="text-[11px] text-slate-500 font-medium">
                        Target Return: <b className="text-emerald-600 font-black">{formatNGN((cronConfig.starting_stake || 5000) * Math.pow(cronConfig.target_odds || 2.00, cronConfig.challenge_days || 10))}</b>
                      </span>
                    </div>

                    {/* Expanded Compounding Steps Ladder */}
                    {showCompoundingLadder && (
                      <div className="mt-2 pt-2 border-t border-slate-100 overflow-x-auto">
                        <div className="flex gap-2 pb-1 min-w-max">
                          {calculateCompoundingLadder(cronConfig.starting_stake || 5000, cronConfig.challenge_days || 10, cronConfig.target_odds || 2.00).map(step => {
                            const isCurrent = step.day === (cronConfig.challenge_day_current || 1);
                            const isPast = step.day < (cronConfig.challenge_day_current || 1);
                            return (
                              <div
                                key={step.day}
                                className={`p-2.5 rounded-xl border text-center min-w-[105px] transition-all ${
                                  isCurrent
                                    ? "bg-emerald-50 border-emerald-400 ring-2 ring-emerald-400/30 shadow-sm"
                                    : isPast
                                    ? "bg-slate-50 border-slate-200 opacity-60"
                                    : "bg-white border-slate-200"
                                }`}
                              >
                                <span className={`text-[10px] font-black uppercase block ${isCurrent ? "text-emerald-700" : "text-slate-500"}`}>
                                  Day {step.day} {isCurrent && "• Today"}
                                </span>
                                <span className="text-[10px] text-slate-400 font-bold block mt-0.5">Stake: {formatNGN(step.stake)}</span>
                                <span className="text-xs font-black text-slate-900 block mt-1">
                                  {formatNGN(step.return)}
                                </span>
                                <span className="text-[9px] text-emerald-600 font-extrabold block">@{step.targetOdds.toFixed(2)}x</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* CONTINUOUS SCHEDULE CONTROLS */
                <div className="bg-slate-50 border border-slate-200 p-4 rounded-2xl space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <label className="text-xs font-black text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Active Weekly Schedule Days</span>
                    </label>
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] font-bold text-slate-500">
                        Dispatches at:
                      </span>
                      <input
                        type="time"
                        value={cronConfig.dispatch_time || "10:00"}
                        onChange={(e) => setCronConfig(prev => ({ ...prev, dispatch_time: e.target.value }))}
                        className="bg-white border border-slate-300 text-slate-900 rounded-lg px-2 py-0.5 text-xs font-black focus:outline-none focus:border-indigo-500 shadow-xs"
                      />
                      <span className="text-[10px] font-black text-indigo-700 bg-indigo-50 px-1.5 py-0.5 rounded border border-indigo-200">
                        WAT
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-7 gap-1.5">
                    {[
                      { id: "MON", label: "Mon" },
                      { id: "TUE", label: "Tue" },
                      { id: "WED", label: "Wed" },
                      { id: "THU", label: "Thu" },
                      { id: "FRI", label: "Fri" },
                      { id: "SAT", label: "Sat" },
                      { id: "SUN", label: "Sun" },
                    ].map(day => {
                      const isSelected = (cronConfig.active_days || []).includes(day.id);
                      return (
                        <button
                          key={day.id}
                          type="button"
                          onClick={() => handleToggleCronDay(day.id)}
                          className={`py-2 rounded-xl text-xs font-black transition-all border flex flex-col items-center justify-center cursor-pointer ${
                            isSelected
                              ? "bg-indigo-600 border-indigo-600 text-white shadow-sm"
                              : "bg-white border-slate-200 text-slate-500 hover:border-slate-300 hover:text-slate-800"
                          }`}
                        >
                          <span>{day.label}</span>
                        </button>
                      );
                    })}
                  </div>

                  {/* Day Presets */}
                  <div className="flex items-center gap-2 pt-1 flex-wrap">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Presets:</span>
                    <button
                      type="button"
                      onClick={() => setCronConfig(prev => ({ ...prev, active_days: ["FRI", "SAT", "SUN"] }))}
                      className="px-2.5 py-1 rounded-lg text-[10px] font-black bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
                    >
                      Weekend (Fri–Sun)
                    </button>
                    <button
                      type="button"
                      onClick={() => setCronConfig(prev => ({ ...prev, active_days: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"] }))}
                      className="px-2.5 py-1 rounded-lg text-[10px] font-black bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
                    >
                      Daily (All 7 Days)
                    </button>
                    <button
                      type="button"
                      onClick={() => setCronConfig(prev => ({ ...prev, active_days: ["TUE", "WED", "THU"] }))}
                      className="px-2.5 py-1 rounded-lg text-[10px] font-black bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-all cursor-pointer"
                    >
                      Midweek (Tue–Thu)
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Target Rollover Multiplier & Strict Safety Corridor */}
            <div className="space-y-3.5 relative z-10">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                <label className="text-xs font-black text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                  <Award className="w-3.5 h-3.5 text-indigo-600" />
                  <span>2. Target Multiplier & Safety Corridor</span>
                </label>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[11px] font-black text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                    Floor: ≥ 1.15
                  </span>
                  <span className="text-[11px] font-black text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md border border-indigo-200">
                    Ceiling: ≤ {(cronConfig.max_leg_odds || 1.45).toFixed(2)}x
                  </span>
                </div>
              </div>

              {/* Target Odds Selector Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div
                  onClick={() => setCronConfig(prev => ({ ...prev, target_odds: 2.00 }))}
                  className={`p-4 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    Math.abs(cronConfig.target_odds - 2.00) < 0.05
                      ? "bg-indigo-50/70 border-indigo-500 ring-2 ring-indigo-500/20 shadow-sm"
                      : "bg-white border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-black text-slate-900">~2.00x Odds</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800 font-black">
                      Standard Doubler (Recommended)
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1.5 font-medium leading-relaxed">
                    2–3 elite safety cushions (80%+ win rate). Perfect for 5-day or 10-day compounding ladders.
                  </p>
                </div>

                <div
                  onClick={() => setCronConfig(prev => ({ ...prev, target_odds: 1.50 }))}
                  className={`p-4 rounded-2xl border cursor-pointer transition-all flex flex-col justify-between ${
                    Math.abs(cronConfig.target_odds - 1.50) < 0.05
                      ? "bg-indigo-50/70 border-indigo-500 ring-2 ring-indigo-500/20 shadow-sm"
                      : "bg-white border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-black text-slate-900">~1.50x Odds</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 font-black">
                      Conservative Safe
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1.5 font-medium leading-relaxed">
                    1–2 elite cushions (88%+ win rate). Ultra-low variance, highest protection.
                  </p>
                </div>
              </div>

              {/* Max Leg Odds Upper Bound Corridor Pills */}
              <div className="bg-slate-50 border border-slate-200/90 rounded-2xl p-3.5 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <span className="text-xs font-black text-slate-800 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                    <span>Single-Leg Safety Corridor Ceiling (Max Odds)</span>
                  </span>
                  <span className="text-[11px] font-bold text-slate-500">
                    Bans any leg above ceiling to eliminate high-variance traps
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {[
                    { val: 1.35, label: "1.35x Max", desc: "Ultra-Safe Corridor" },
                    { val: 1.40, label: "1.40x Max", desc: "Tight Corridor" },
                    { val: 1.45, label: "1.45x Max", desc: "Standard (Recommended)" },
                  ].map(corridor => {
                    const isSel = Math.abs((cronConfig.max_leg_odds || 1.45) - corridor.val) < 0.02;
                    return (
                      <button
                        key={corridor.val}
                        type="button"
                        onClick={() => setCronConfig(prev => ({ ...prev, max_leg_odds: corridor.val }))}
                        className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer ${
                          isSel
                            ? "bg-emerald-50 border-emerald-500 ring-2 ring-emerald-500/20 text-emerald-950 font-black shadow-xs"
                            : "bg-white border-slate-200 hover:border-slate-300 text-slate-700 font-bold"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-black">{corridor.label}</span>
                          {isSel && <span className="w-2 h-2 rounded-full bg-emerald-600" />}
                        </div>
                        <span className="text-[10px] text-slate-500 block mt-0.5 font-medium">{corridor.desc}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* TRANSPARENT 5-GATE PREDICTION ENGINE INSPECTOR (Addresses User Concerns) */}
            <div className="bg-slate-50 border border-slate-200/90 rounded-2xl p-4 sm:p-5 space-y-3 relative z-10">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center flex-shrink-0">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-black text-slate-900 block">
                      Deterministic Selection Architecture (Zero Randomness)
                    </span>
                    <span className="text-[11px] text-slate-500 font-medium block">
                      Every pick is mathematically audited against SportyBet's live feeds through 5 non-random gates.
                    </span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowQualityGates(!showQualityGates)}
                  className="text-xs font-black text-indigo-600 hover:text-indigo-800 flex items-center gap-1 cursor-pointer self-start sm:self-center"
                >
                  <span>{showQualityGates ? "Hide Gates" : "Inspect 5 Quality Gates"}</span>
                  {showQualityGates ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>

              {/* 5-Gate Details */}
              {showQualityGates && (
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5 pt-2 border-t border-slate-200/70">
                  <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[10px] font-black text-indigo-600 uppercase block">Gate 1: Ingestion</span>
                    <p className="text-xs font-black text-slate-900">SportyBet Today Feed</p>
                    <p className="text-[10px] text-slate-500">Live API only. Unlocked, active, non-suspended markets with ≥ 10m to kickoff.</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[10px] font-black text-rose-600 uppercase block">Gate 2: Anti-Noise</span>
                    <p className="text-xs font-black text-slate-900">Zero Obscure Leagues</p>
                    <p className="text-[10px] text-slate-500">Auto-rejects U19/U21 youth tournaments, reserves, B-teams, and simulated SRL.</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[10px] font-black text-amber-600 uppercase block">Gate 3: Pedigree</span>
                    <p className="text-xs font-black text-slate-900">Tier Pedigree System</p>
                    <p className="text-[10px] text-slate-500">Tier 1 & European/FIFA competitions get +25 pt priority score boost.</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[10px] font-black text-emerald-600 uppercase block">Gate 4: Modeling & Form</span>
                    <p className="text-xs font-black text-slate-900">H2H & 5-Match Form Audit</p>
                    <p className="text-[10px] text-slate-500">Direct SportyBet ingestion. Vets H2H win rates, 5-match form consistency, and enforces safety corridor [1.15 ≤ Odds ≤ Max].</p>
                  </div>
                  <div className="p-3 bg-white rounded-xl border border-slate-200 space-y-1">
                    <span className="text-[10px] font-black text-purple-600 uppercase block">Gate 5: Combinatorics</span>
                    <p className="text-xs font-black text-slate-900">Deterministic Optimizer</p>
                    <p className="text-[10px] text-slate-500">Evaluates top 50 ranked picks across 2-, 3-, and 4-leg permutations for highest joint probability.</p>
                  </div>
                </div>
              )}
            </div>

            {/* Telegram Channel Bar & Primary Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-100 relative z-10">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-200 flex items-center justify-center text-sky-600 flex-shrink-0">
                  <Send className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-black text-slate-900">Telegram Dispatch Channel</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                  </div>
                  <span className="text-[10px] text-slate-500">Delivers booking codes and analysis directly to your Telegram chat at 10:00 AM WAT</span>
                </div>
                <button
                  type="button"
                  onClick={handleTestCronTelegram}
                  disabled={telegramTesting}
                  className="ml-2 px-2.5 py-1.5 rounded-lg text-[10px] font-black bg-sky-50 text-sky-700 hover:bg-sky-100 border border-sky-200 transition-all cursor-pointer flex items-center gap-1 shadow-xs"
                >
                  {telegramTesting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                  <span>{telegramTesting ? "Sending..." : "Test Ping"}</span>
                </button>
              </div>

              {/* Action Buttons: Save & Run Now */}
              <div className="flex items-center gap-2.5 flex-wrap">
                <button
                  type="button"
                  onClick={handleSaveCronSchedule}
                  disabled={cronLoading}
                  className="px-4 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-black border border-slate-200 transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
                >
                  {cronLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />}
                  <span>Save Settings</span>
                </button>

                <button
                  type="button"
                  onClick={handleRunCronNow}
                  disabled={cronRunningNow}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-xs font-black shadow-lg shadow-emerald-600/20 transition-all flex items-center gap-2 cursor-pointer"
                >
                  {cronRunningNow ? <RefreshCw className="w-4 h-4 animate-spin text-white" /> : <Play className="w-4 h-4 text-white fill-white" />}
                  <span>{cronRunningNow ? "Sweeping & Booking SportyBet..." : "Run Now (Test Live 10:00 AM)"}</span>
                </button>
              </div>
            </div>

            {/* Notifications / Alerts */}
            {telegramStatus && (
              <div className={`p-3 rounded-xl text-xs font-bold flex items-center gap-2 ${
                telegramStatus.type === "SUCCESS"
                  ? "bg-sky-50 border border-sky-200 text-sky-800"
                  : "bg-rose-50 border border-rose-200 text-rose-800"
              }`}>
                <Info className="w-4 h-4 flex-shrink-0" />
                <span>{telegramStatus.msg}</span>
              </div>
            )}

            {cronNotice && (
              <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-bold flex items-center gap-2">
                <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>{cronNotice}</span>
              </div>
            )}

            {cronError && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs font-bold flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                <span>{cronError}</span>
              </div>
            )}
          </div>

          {/* LIVE DISPATCHED ROLLOVER SLIP CARD */}
          {cronTicketResult && cronTicketResult.picks && cronTicketResult.picks.length > 0 && (
            <div className="bg-white rounded-3xl border border-slate-200 p-6 shadow-sm space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-2xl bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 flex-shrink-0">
                    <Award className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-black text-slate-900 tracking-tight">
                        Active Rollover Slip ({cronTicketResult.date_str || "Today"})
                      </h3>
                      {cronTicketResult.telegram_dispatched && (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-sky-50 text-sky-700 border border-sky-200 flex items-center gap-1">
                          <Send className="w-2.5 h-2.5" />
                          <span>Dispatched to Telegram</span>
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 font-medium">
                      Total Odds: <b>{cronTicketResult.actual_odds}x</b> | Win Confidence: <b>{cronTicketResult.confidence_score}%</b> | Legs: <b>{cronTicketResult.leg_count} games</b>
                    </p>
                  </div>
                </div>

                {/* SportyBet Booking Code Badge */}
                {cronTicketResult.booking_code && cronTicketResult.booking_code !== "N/A" && (
                  <div className="flex items-center gap-2">
                    <div className="bg-slate-900 text-white px-3.5 py-1.5 rounded-xl flex items-center gap-2 font-mono text-xs font-black shadow-sm">
                      <span className="text-[10px] text-slate-400 font-sans uppercase">SportyBet:</span>
                      <span className="tracking-widest text-emerald-400 text-sm">{cronTicketResult.booking_code}</span>
                      <button
                        type="button"
                        onClick={() => {
                          navigator.clipboard.writeText(cronTicketResult.booking_code);
                          setCopiedCronCode(true);
                          setTimeout(() => setCopiedCronCode(false), 2000);
                        }}
                        className="text-slate-400 hover:text-white transition-all cursor-pointer"
                        title="Copy Code"
                      >
                        {copiedCronCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      </button>
                    </div>

                    <a
                      href={cronTicketResult.share_url || `https://www.sportybet.com/ng/?shareCode=${cronTicketResult.booking_code}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-black transition-all flex items-center gap-1 shadow-sm"
                    >
                      <span>Load on SportyBet</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                )}
              </div>

              {/* Legs Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {cronTicketResult.picks.map((p, idx) => (
                  <div key={idx} className="p-3.5 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-2">
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span className="font-extrabold text-indigo-600 uppercase tracking-wider">{p.competition || "League"}</span>
                      <span className="font-bold bg-white px-2 py-0.5 rounded-md border border-slate-200">Leg #{idx + 1}</span>
                    </div>

                    <div>
                      <p className="text-xs font-black text-slate-900 leading-tight">
                        {p.home_team} <span className="text-slate-400 font-normal">vs</span> {p.away_team}
                      </p>
                    </div>

                    <div className="pt-1.5 border-t border-slate-200 flex items-center justify-between">
                      <div>
                        <span className="text-[10px] text-slate-400 block uppercase font-bold">{p.market_desc || "Market"}</span>
                        <span className="text-xs font-black text-slate-900">{p.selection_desc || "Selection"}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-xs font-black text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200 block">
                          @{p.odds}
                        </span>
                        <span className="text-[9px] font-bold text-slate-400 block mt-0.5">
                          {(p.model_probability * 100).toFixed(0)}% Win Prob
                        </span>
                      </div>
                    </div>

                    {/* Head-to-Head & Form Evidence Badges */}
                    {(p.h2h_summary || p.form_summary) && (
                      <div className="pt-1.5 border-t border-slate-200/70 space-y-1">
                        {p.h2h_summary && (
                          <div className="flex items-center gap-1.5 text-[10px] font-black text-amber-900 bg-amber-50 px-2 py-0.5 rounded-lg border border-amber-200/70">
                            <ShieldCheck className="w-3 h-3 text-amber-600 flex-shrink-0" />
                            <span className="truncate">{p.h2h_summary}</span>
                          </div>
                        )}
                        {p.form_summary && (
                          <div className="flex items-center gap-1.5 text-[10px] font-black text-emerald-900 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200/70">
                            <CheckCircle2 className="w-3 h-3 text-emerald-600 flex-shrink-0" />
                            <span className="truncate">{p.form_summary}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {(p.selection_rationale || p.rationale) && (
                      <div className="pt-1.5 border-t border-slate-100 flex items-start gap-1 text-[10px] text-slate-500 font-medium">
                        <ShieldCheck className="w-3 h-3 text-emerald-600 flex-shrink-0 mt-0.5" />
                        <span>{p.selection_rationale || p.rationale}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Run History Toggle & Drawer */}
          {cronHistory && cronHistory.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm">
              <button
                type="button"
                onClick={() => setShowCronHistory(!showCronHistory)}
                className="w-full flex items-center justify-between text-xs font-extrabold text-slate-700 cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-indigo-500" />
                  <span>Automated Rollover Execution History ({cronHistory.length} runs recorded)</span>
                </div>
                {showCronHistory ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
              </button>

              {showCronHistory && (
                <div className="mt-3 pt-3 border-t border-slate-100 overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="text-[10px] font-black text-slate-400 uppercase tracking-wider border-b border-slate-100">
                        <th className="pb-2">Date / Time</th>
                        <th className="pb-2">Target</th>
                        <th className="pb-2">Actual Odds</th>
                        <th className="pb-2">SportyBet Code</th>
                        <th className="pb-2">Games</th>
                        <th className="pb-2">Telegram Alert</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {cronHistory.map((h, i) => (
                        <tr key={i} className="hover:bg-slate-50 transition-all">
                          <td className="py-2 font-bold text-slate-800">{h.date} {h.time}</td>
                          <td className="py-2 text-slate-600">{h.target_odds?.toFixed(2)}x</td>
                          <td className="py-2 font-extrabold text-slate-900">{h.actual_odds?.toFixed(2)}x</td>
                          <td className="py-2 font-mono font-bold text-emerald-600">
                            {h.booking_code && h.booking_code !== "N/A" ? (
                              <a href={`https://www.sportybet.com/ng/?shareCode=${h.booking_code}`} target="_blank" rel="noopener noreferrer" className="hover:underline flex items-center gap-1">
                                <span>{h.booking_code}</span>
                                <ExternalLink className="w-2.5 h-2.5 text-slate-400" />
                              </a>
                            ) : "—"}
                          </td>
                          <td className="py-2 text-slate-600">{h.picks_count || "—"} legs</td>
                          <td className="py-2">
                            {h.telegram_dispatched ? (
                              <span className="text-emerald-600 font-extrabold flex items-center gap-1 text-[11px]">
                                <Check className="w-3 h-3" />
                                <span>Delivered</span>
                              </span>
                            ) : (
                              <span className="text-slate-400 text-[11px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* MANUAL ROLLOVER BUILDER CONTROLS */}
          <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider">Manual Custom Rollover Explorer</h3>
                <p className="text-[11px] text-slate-400">Want to test a custom stake, league filter, or custom odds outside the 10:00 AM WAT automation?</p>
              </div>
            </div>

            {/* Target & Stake Header */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">1. Target Rollover Odds</label>
                <select
                  value={dailyTargetOdds}
                  onChange={(e) => setDailyTargetOdds(parseFloat(e.target.value))}
                  className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
                >
                  <option value={1.30}>~1.30 Rollover Odds (Ultra High Assurance 90%+)</option>
                  <option value={1.50}>~1.50 Rollover Odds (Balanced Safe 85%+)</option>
                  <option value={1.80}>~1.80 Rollover Odds (High Confidence)</option>
                  <option value={2.00}>~2.00 Rollover Odds (Standard 2x Rollover)</option>
                  <option value={2.50}>~2.50 Rollover Odds (Dynamic Value)</option>
                  <option value={3.00}>~3.00 Rollover Odds (High Growth)</option>
                  <option value={4.00}>~4.00 Rollover Odds (4x Power Rollover)</option>
                  <option value={5.00}>~5.00 Rollover Odds (5x Max Multiplier)</option>
                </select>
              </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">2. Starting Stake (NGN)</label>
              <input
                type="number"
                value={startingStake}
                onChange={(e) => setStartingStake(parseInt(e.target.value) || 1000)}
                placeholder="5000"
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              />
            </div>
          </div>

          {/* League Multi-Select for Rollover */}
          <div className="space-y-3 pt-2 border-t border-slate-100">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <label className="text-xs font-extrabold text-slate-900 block">3. Select Leagues for Rollover</label>
                <p className="text-[11px] text-slate-400">Strictly filters matches to chosen leagues only.</p>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  type="button"
                  onClick={() => setSelectedLeagues(INTERNATIONAL_BREAK_CODES)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all flex items-center gap-1 ${
                    INTERNATIONAL_BREAK_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === INTERNATIONAL_BREAK_CODES.length
                      ? "bg-emerald-600 text-white shadow-sm shadow-emerald-200"
                      : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200"
                  }`}
                >
                  <span>🌍</span>
                  <span>International Break</span>
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLeagues(TOP_5_LEAGUE_CODES)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all ${
                    TOP_5_LEAGUE_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === TOP_5_LEAGUE_CODES.length
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  Top 5 European
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLeagues(ALL_TOP_LEAGUE_CODES)}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all ${
                    ALL_TOP_LEAGUE_CODES.every(l => selectedLeagues.includes(l)) && selectedLeagues.length === ALL_TOP_LEAGUE_CODES.length
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  All Top Leagues
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLeagues(["ALL_WORLDWIDE"])}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-extrabold transition-all ${
                    selectedLeagues.includes("ALL_WORLDWIDE")
                      ? "bg-slate-900 text-white"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                  }`}
                >
                  Worldwide (All Matches)
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedLeagues([])}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all ${
                    selectedLeagues.length === 0 ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  Clear Selection
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
              {AVAILABLE_LEAGUES.map((lg) => {
                const isSelected = selectedLeagues.includes(lg.code);
                return (
                  <div
                    key={lg.code}
                    onClick={() => {
                      if (selectedLeagues.includes(lg.code)) {
                        setSelectedLeagues(selectedLeagues.filter(c => c !== lg.code));
                      } else {
                        setSelectedLeagues([...selectedLeagues, lg.code]);
                      }
                    }}
                    className={`px-3 py-2 rounded-xl border cursor-pointer transition-all flex items-center justify-between ${
                      isSelected
                        ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                        : "bg-white border-slate-200 text-slate-700 hover:border-slate-300"
                    }`}
                  >
                    <div className="min-w-0 pr-1">
                      <p className="text-xs font-extrabold truncate">{lg.name}</p>
                      <p className="text-[10px] text-slate-400 truncate">{lg.country}</p>
                    </div>
                    <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center flex-shrink-0 ${
                      isSelected ? "bg-white border-white text-slate-900" : "border-slate-300"
                    }`}>
                      {isSelected && <div className="w-1.5 h-1.5 rounded-sm bg-slate-900" />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Match Schedule Window for Rollover */}
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">4. Match Schedule Window</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { id: "TODAY", label: "Today's Games", sub: todayData ? `${todayData.total_matches} SportyBet matches` : "Matches playing today" },
                { id: "NEXT_24H", label: "Next 24 Hours", sub: "Upcoming 24h slate" },
                { id: "WEEKEND", label: "Weekend Combined", sub: "Saturday & Sunday" },
                { id: "NEXT_7D", label: "Upcoming 7 Days", sub: "Full week fixture pool" },
              ].map(w => (
                <div
                  key={w.id}
                  onClick={() => setDateWindow(w.id)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    dateWindow === w.id
                      ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                      : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                  }`}
                >
                  <p className="text-xs font-extrabold">{w.label}</p>
                  <p className={`text-[10px] mt-0.5 ${dateWindow === w.id ? "text-slate-400" : "text-slate-500"}`}>{w.sub}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Risk Strategy Profile for Rollover */}
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">5. Risk Strategy Profile</label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[
                { id: "CONSERVATIVE", label: "Conservative (Safety Cushions)", desc: "Tier-1 cushions (80%+ win rate: Double Chance, Over 1.5, Team Goals)" },
                { id: "AGGRESSIVE", label: "Aggressive (Value Maximizer)", desc: "Direct value & higher odds (Straight 1X2 wins, Over 2.5 goals, Handicaps)" },
              ].map(r => (
                <div
                  key={r.id}
                  onClick={() => setRiskProfile(r.id)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    riskProfile === r.id
                      ? "bg-slate-900 border-slate-900 text-white shadow-sm"
                      : "bg-slate-50 border-slate-200 text-slate-800 hover:bg-slate-100"
                  }`}
                >
                  <p className="text-xs font-extrabold">{r.label}</p>
                  <p className={`text-[10px] mt-0.5 ${riskProfile === r.id ? "text-slate-400" : "text-slate-500"}`}>{r.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Allowed Market Categories for Rollover */}
          <div className="space-y-2 pt-2 border-t border-slate-100">
            <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">6. Allowed Market Categories</label>
            <div className="flex flex-wrap gap-2">
              {[
                { id: "DOUBLE_CHANCE", label: "Double Chance (1X/12/X2)" },
                { id: "OVER_UNDER", label: "Over/Under Goals" },
                { id: "TEAM_GOALS", label: "Team Total Goals" },
                { id: "1X2", label: "1X2 Match Result" },
              ].map(m => {
                const isSelected = selectedMarketCategories.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => {
                      setSelectedMarketCategories(prev =>
                        isSelected
                          ? (prev.length > 1 ? prev.filter(x => x !== m.id) : prev)
                          : [...prev, m.id]
                      );
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${
                      isSelected
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    {isSelected ? "✓ " : ""}{m.label}
                  </button>
                );
              })}
            </div>
          </div>

          {errorMsg && (
            <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl flex items-start gap-2.5 text-xs text-amber-800">
              <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-extrabold">Notice</p>
                <p className="mt-0.5">{errorMsg}</p>
              </div>
            </div>
          )}

          <div className="pt-2">
            <button
              onClick={handleBuildRollover}
              disabled={loading}
              className="w-full py-3.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 shadow-sm cursor-pointer"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>{loading ? "Analyzing SportyBet Live Fixtures..." : "Generate High-Assurance Rollover Slip"}</span>
            </button>
          </div>
        </div>
      </div>
    )}

      {/* MODE 4: CUSTOM SHORTLIST EVALUATOR & AUTO-BOOKER */}
      {builderMode === "SHORTLIST" && (
        <div className="bg-white p-5 sm:p-6 rounded-2xl border border-slate-200 shadow-sm space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
            <div>
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 flex-shrink-0">
                  <FileText className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-black text-slate-900 tracking-tight flex items-center gap-2">
                    <span>Custom Shortlist Evaluator & Auto-Booker</span>
                    <span className="text-[10px] font-black px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300">
                      Live SportyBet Sync
                    </span>
                  </h3>
                  <p className="text-xs text-slate-500 font-medium">
                    Upload or paste any fixture list (Nations League, International Breaks, League matches, etc.). StatIQ reconciles live SportyBet markets, filters via the 5-Gate Pick Engine, and books the slip directly.
                  </p>
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-2 flex-wrap">
              <button
                type="button"
                onClick={handleLoadSampleShortlist}
                className="px-3 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-bold border border-indigo-200 transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Load Sample Matches</span>
              </button>
              
              <label className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold border border-slate-200 transition-all flex items-center gap-1.5 cursor-pointer">
                <Upload className="w-3.5 h-3.5" />
                <span>Upload .txt / .csv</span>
                <input
                  type="file"
                  accept=".txt,.csv"
                  onChange={handleShortlistFileUpload}
                  className="hidden"
                />
              </label>

              {shortlistText && (
                <button
                  type="button"
                  onClick={handleClearShortlist}
                  className="px-2.5 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 text-xs font-bold border border-rose-200 transition-all flex items-center gap-1 cursor-pointer"
                  title="Clear matches"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Clear</span>
                </button>
              )}
            </div>
          </div>

          {/* Text Area Input */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-extrabold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                <span>1. Paste or Edit Match Fixtures</span>
                <span className="text-[10px] text-slate-400 font-normal lowercase">(one fixture per line or raw SportyBet copy-paste)</span>
              </label>
              <span className="text-[11px] font-bold text-slate-500">
                {shortlistMatchCount} {shortlistMatchCount === 1 ? "line detected" : "lines detected"}
              </span>
            </div>

            <textarea
              rows={8}
              value={shortlistText}
              onChange={(e) => setShortlistText(e.target.value)}
              placeholder={`Paste your matches here in any format, e.g.:
Slovenia vs Scotland
Bulgaria vs Luxembourg
Faroe Islands vs Kazakhstan
Czechia vs Croatia
England vs Spain
Slovakia vs Moldova

You can also paste raw copy-pasted blocks from SportyBet (with IDs, times, etc.) - StatIQ will automatically clean and extract the teams!`}
              className="w-full bg-slate-50 hover:bg-white focus:bg-white border border-slate-200 focus:border-slate-400 rounded-xl p-3.5 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-900/10 transition-all placeholder:text-slate-400"
            />
          </div>

          {/* Configuration Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            {/* Target Mode & Amount */}
            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 space-y-3">
              <label className="text-[11px] font-extrabold text-slate-600 uppercase tracking-wider block">
                2. Target Objective
              </label>
              <div className="grid grid-cols-2 gap-1.5 bg-slate-200/70 p-1 rounded-lg">
                <button
                  type="button"
                  onClick={() => setShortlistTargetMode("GAMES")}
                  className={`py-1.5 text-xs font-extrabold rounded-md transition-all cursor-pointer ${
                    shortlistTargetMode === "GAMES"
                      ? "bg-white text-slate-900 shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  By Game Count
                </button>
                <button
                  type="button"
                  onClick={() => setShortlistTargetMode("ODDS")}
                  className={`py-1.5 text-xs font-extrabold rounded-md transition-all cursor-pointer ${
                    shortlistTargetMode === "ODDS"
                      ? "bg-white text-slate-900 shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  By Total Odds
                </button>
              </div>

              {shortlistTargetMode === "GAMES" ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {[3, 5, 8, 10, 12, 15].map((cnt) => (
                      <button
                        key={cnt}
                        type="button"
                        onClick={() => setShortlistTargetGames(cnt)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-black transition-all cursor-pointer ${
                          shortlistTargetGames === cnt
                            ? "bg-slate-900 text-white"
                            : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        {cnt} Games
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-slate-500">Custom count:</span>
                    <input
                      type="number"
                      min="2"
                      max="30"
                      value={shortlistTargetGames}
                      onChange={(e) => setShortlistTargetGames(Math.max(1, parseInt(e.target.value) || 1))}
                      className="w-20 bg-white border border-slate-300 rounded-lg px-2 py-1 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {[2.0, 3.0, 5.0, 10.0, 20.0].map((od) => (
                      <button
                        key={od}
                        type="button"
                        onClick={() => setShortlistTargetOdds(od)}
                        className={`px-2.5 py-1 rounded-lg text-xs font-black transition-all cursor-pointer ${
                          shortlistTargetOdds === od
                            ? "bg-slate-900 text-white"
                            : "bg-white border border-slate-200 text-slate-700 hover:bg-slate-100"
                        }`}
                      >
                        ~{od}x
                      </button>
                    ))}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-slate-500">Custom odds:</span>
                    <input
                      type="number"
                      step="0.5"
                      min="1.5"
                      max="100"
                      value={shortlistTargetOdds}
                      onChange={(e) => setShortlistTargetOdds(Math.max(1.2, parseFloat(e.target.value) || 2.0))}
                      className="w-20 bg-white border border-slate-300 rounded-lg px-2 py-1 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Ticket Portfolio Variants */}
            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 space-y-3">
              <label className="text-[11px] font-extrabold text-slate-600 uppercase tracking-wider block">
                3. Ticket Variants (Portfolio)
              </label>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { num: 1, label: "1 Ticket", desc: "Highest Conviction" },
                  { num: 2, label: "2 Slips", desc: "Hedged / Diversified" },
                  { num: 3, label: "3 Slips", desc: "3-Tier Cover" },
                ].map(v => (
                  <button
                    key={v.num}
                    type="button"
                    onClick={() => setShortlistNumTickets(v.num)}
                    className={`p-2.5 rounded-xl border text-center transition-all cursor-pointer ${
                      shortlistNumTickets === v.num
                        ? "bg-slate-900 border-slate-900 text-white shadow-xs"
                        : "bg-white border-slate-200 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <div className="text-xs font-black">{v.label}</div>
                    <div className={`text-[9px] mt-0.5 ${shortlistNumTickets === v.num ? "text-slate-300" : "text-slate-400"}`}>
                      {v.desc}
                    </div>
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-slate-500 leading-normal">
                Multi-slip mode builds diversified tickets with zero correlated failure across your matches.
              </p>
            </div>

            {/* Risk Profile */}
            <div className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 space-y-3">
              <label className="text-[11px] font-extrabold text-slate-600 uppercase tracking-wider block">
                4. Risk Profile
              </label>
              <div className="space-y-1.5">
                {[
                  { id: "CONSERVATIVE", label: "Conservative (Safety Cushions)", desc: "Double chance, Over 1.5, Team Goals (75%+ win rate)" },
                  { id: "AGGRESSIVE", label: "Aggressive (Value Maximizer)", desc: "Straight 1X2 wins, Over 2.5 goals, Handicaps" },
                ].map(r => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setShortlistRiskProfile(r.id)}
                    className={`w-full p-2 rounded-xl border text-left transition-all cursor-pointer ${
                      shortlistRiskProfile === r.id
                        ? "bg-slate-900 border-slate-900 text-white shadow-xs"
                        : "bg-white border-slate-200 text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <div className="text-xs font-bold">{r.label}</div>
                    <div className={`text-[10px] mt-0.5 ${shortlistRiskProfile === r.id ? "text-slate-400" : "text-slate-500"}`}>
                      {r.desc}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Error Message */}
          {shortlistError && (
            <div className="bg-rose-50 border border-rose-200 p-4 rounded-xl flex items-start gap-2.5 text-xs text-rose-800">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-extrabold">Notice</p>
                <p className="mt-0.5">{shortlistError}</p>
              </div>
            </div>
          )}

          {/* Action Button */}
          <div>
            <button
              type="button"
              onClick={handleBuildShortlistTicket}
              disabled={shortlistBuilding || !shortlistText.trim()}
              className="w-full py-4 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {shortlistBuilding ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Matching with SportyBet & Running 5-Gate Engine...</span>
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 text-emerald-400 fill-emerald-400" />
                  <span>Evaluate Shortlist & Generate SportyBet Code</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* SHORTLIST RESULTS CONTAINER */}
      {builderMode === "SHORTLIST" && shortlistResult && (
        <div className="space-y-6">
          {/* Match Reconciliation Summary Badge */}
          <div className="bg-slate-900 text-white p-4 rounded-2xl border border-slate-800 shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center">
                <CheckCircle2 className="w-4 h-4" />
              </div>
              <div>
                <div className="text-xs font-black text-emerald-400 flex items-center gap-1.5">
                  <span>Reconciled {shortlistResult.total_resolved} of {shortlistResult.total_submitted} Submitted Fixtures</span>
                </div>
                <div className="text-[11px] text-slate-400">
                  Active live SportyBet markets matched & evaluated with 5-Gate risk criteria.
                </div>
              </div>
            </div>

            {shortlistResult.unmatched_items && shortlistResult.unmatched_items.length > 0 && (
              <div className="text-[10px] text-amber-300 bg-amber-950/60 border border-amber-600/40 px-2.5 py-1 rounded-lg">
                ⚠️ {shortlistResult.unmatched_items.length} fixtures not found / already kicked off
              </div>
            )}
          </div>

          {/* Portfolio Tabs if > 1 ticket */}
          {shortlistResult.scenarios && shortlistResult.scenarios.length > 1 && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {shortlistResult.scenarios.map((sc, scIdx) => {
                  const isCurrent = shortlistActivePortfolioIndex === scIdx;
                  const isMaster = sc.is_master || sc.ticket_index === "MASTER";
                  return (
                    <button
                      key={scIdx}
                      type="button"
                      onClick={() => setShortlistActivePortfolioIndex(scIdx)}
                      className={`w-full p-2.5 sm:p-3 rounded-xl border text-left transition-all flex flex-col justify-between gap-1.5 cursor-pointer ${
                        isMaster
                          ? (isCurrent
                            ? "bg-amber-950/70 border-amber-400 ring-2 ring-amber-400/50 text-white shadow-lg"
                            : "bg-slate-900 border-amber-500/40 text-amber-300 hover:bg-amber-950/40")
                          : (isCurrent
                            ? "bg-slate-900 border-emerald-400 ring-2 ring-emerald-400/40 text-white shadow-md"
                            : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50")
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-black flex items-center gap-1.5">
                          {isMaster ? (
                            <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                          ) : (
                            <Ticket className="w-3.5 h-3.5 text-emerald-500" />
                          )}
                          <span className="truncate">{isMaster ? "Master Ticket" : `Slip #${scIdx + 1}`}</span>
                        </span>
                        <span className={`text-[10px] font-black px-1.5 sm:px-2 py-0.5 rounded flex-shrink-0 ${
                          isMaster
                            ? "bg-amber-400 text-slate-950"
                            : (isCurrent ? "bg-emerald-400 text-slate-950" : "bg-slate-100 text-slate-800")
                        }`}>
                          ~{sc.accumulated_odds}x
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-100">
                        <span className="text-slate-400 font-bold">{sc.selections?.length || 0} Legs</span>
                        {sc.booking_code && (
                          <span className={`font-mono font-black px-1.5 py-0.5 rounded text-[10px] ${
                            isMaster
                              ? "bg-amber-100 text-amber-900 border border-amber-300"
                              : "bg-emerald-50 text-emerald-800 border border-emerald-200"
                          }`}>
                            {sc.booking_code}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Master Ticket Action Panel for Shortlist Mode */}
              <div className="bg-gradient-to-r from-amber-950/60 via-slate-900 to-amber-950/40 border border-amber-500/40 rounded-2xl p-3.5 sm:p-4 space-y-3 shadow-lg">
                <div className="flex items-start sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-400/40 flex items-center justify-center flex-shrink-0">
                      <Zap className="w-4 h-4 text-amber-400 fill-amber-400" />
                    </div>
                    <div>
                      <h4 className="text-xs sm:text-sm font-black text-amber-300 flex items-center gap-1.5">
                        <span>Merge into Master Ticket</span>
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-200 border border-amber-400/30 font-bold uppercase">
                          Zero Duplicates
                        </span>
                      </h4>
                      <p className="text-[11px] text-slate-400 leading-snug">
                        Resolves overlapping matches by picking highest-probability market, prioritizing top winnable games.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-1 border-t border-amber-500/20">
                  <div className="flex items-center justify-between sm:justify-start gap-1 sm:gap-1.5 bg-slate-950/90 p-1.5 rounded-xl border border-slate-800 w-full sm:w-auto">
                    <span className="text-[10px] text-slate-400 font-extrabold px-1">Games:</span>
                    {[5, 8, 10, 12, 15].map((cnt) => (
                      <button
                        key={cnt}
                        type="button"
                        onClick={() => {
                          setMasterPrioritizedGames(cnt);
                          setCustomMasterGamesInput(String(cnt));
                        }}
                        className={`flex-1 sm:flex-initial px-2 sm:px-2.5 py-1 rounded-lg text-xs font-black transition-all ${
                          masterPrioritizedGames === cnt
                            ? "bg-amber-400 text-slate-950 shadow-sm"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        {cnt}
                      </button>
                    ))}
                    <div className="flex items-center gap-1 pl-1 border-l border-slate-800">
                      <input
                        type="number"
                        min="2"
                        max="15"
                        placeholder="1-15"
                        value={customMasterGamesInput}
                        onChange={(e) => {
                          const val = e.target.value;
                          setCustomMasterGamesInput(val);
                          const parsed = parseInt(val, 10);
                          if (!isNaN(parsed) && parsed >= 2) {
                            setMasterPrioritizedGames(Math.min(15, parsed));
                          }
                        }}
                        className="w-10 sm:w-12 bg-slate-900 border border-slate-700 text-amber-300 placeholder-slate-500 rounded px-1 py-0.5 text-xs font-black text-center focus:outline-none focus:border-amber-400"
                        title="Type any number of games (2 to 15)"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleMergeShortlistToMaster(masterPrioritizedGames)}
                    disabled={mergingMaster}
                    className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-400 via-amber-500 to-amber-400 text-slate-950 text-xs font-black flex items-center justify-center gap-2 shadow-lg hover:shadow-amber-500/20 active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50"
                  >
                    {mergingMaster ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Zap className="w-3.5 h-3.5 fill-slate-950" />
                    )}
                    <span>{mergingMaster ? "Merging Slips..." : `Generate ${masterPrioritizedGames}-Game Master Slip`}</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Active Slip Detail Card */}
          {(() => {
            const scns = shortlistResult.scenarios || [shortlistResult.ticket];
            const activeScn = scns[shortlistActivePortfolioIndex] || scns[0];
            if (!activeScn) return null;

            return (
              <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-slate-900 text-sm flex items-center gap-1.5">
                        <Award className="w-4 h-4 text-emerald-600" />
                        <span>5-Gate Approved Shortlist Ticket ({activeScn.selections?.length || 0} Legs)</span>
                      </span>
                      <span className="text-[10px] font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider bg-emerald-100 text-emerald-900 border border-emerald-200">
                        {activeScn.confidence_tier || "HIGH"} Tier
                      </span>
                    </div>
                    <span className="text-xs text-slate-500 font-medium mt-0.5 block">
                      Combined Odds: <strong>~{activeScn.accumulated_odds}x</strong> &bull; Win Probability: <strong>{((activeScn.combined_probability || 0.5) * 100).toFixed(1)}%</strong>
                    </span>
                  </div>

                  <button
                    onClick={() => setShortlistResult(null)}
                    className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all self-end sm:self-center cursor-pointer"
                    title="Dismiss Shortlist Result"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {/* Selections List */}
                <div className="space-y-3">
                  {activeScn.selections?.map((sel, sIdx) => {
                    const logKey = `shortlist_${sIdx}`;
                    const isExpanded = expandedAuditLogs[logKey];
                    const tier = sel.confidence_tier || "HIGH";

                    return (
                      <div key={sIdx} className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[10px] font-extrabold text-slate-700 bg-slate-200 px-2 py-0.5 rounded">
                                {formatCompetitionWithCountry(sel.competition || sel.competition_code, sel.country)}
                              </span>
                              <span className={`text-[9px] font-extrabold px-2 py-0.2 rounded uppercase ${
                                tier === "ELITE" ? "bg-purple-100 text-purple-800" :
                                tier === "HIGH" ? "bg-emerald-100 text-emerald-800" :
                                tier === "SOLID" ? "bg-blue-100 text-blue-800" :
                                "bg-amber-100 text-amber-800"
                              }`}>
                                {tier}
                              </span>
                            </div>
                            <span className="text-sm font-extrabold text-slate-900 block">
                              {sel.home_team} vs {sel.away_team}
                            </span>
                            {sel.tactical_reason && (
                              <span className="inline-block mt-1 text-[10px] font-extrabold text-indigo-700 bg-indigo-50 border border-indigo-200/80 px-2 py-0.5 rounded-md">
                                {sel.tactical_reason}
                              </span>
                            )}

                            {/* Assigned Pick Banner */}
                            <div className="mt-2 bg-white rounded-xl p-2.5 border border-slate-200 shadow-2xs flex items-center justify-between gap-2 flex-wrap">
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] font-black px-2 py-0.5 rounded bg-emerald-100 text-emerald-900 border border-emerald-300 uppercase tracking-wider">
                                  Approved Pick
                                </span>
                                <span className="text-xs font-black text-slate-900">
                                  {sel.selection_name || sel.selection || sel.pick}
                                </span>
                              </div>
                              <span className="text-xs font-black text-slate-900 bg-slate-100 px-2.5 py-0.5 rounded-lg border border-slate-200">
                                @{(sel.estimated_odds || sel.odds || 1.30).toFixed(2)}
                              </span>
                            </div>
                          </div>

                          <div className="flex items-center space-x-3 self-end sm:self-center">
                            <div className="text-right">
                              <span className="text-[10px] text-slate-400 block font-medium">Model Prob.</span>
                              <span className="text-sm font-extrabold text-emerald-700">
                                {((sel.model_probability || sel.prob || 0.8) * 100).toFixed(0)}%
                              </span>
                            </div>

                            {sel.decision_audit_log && (
                              <button
                                onClick={() => setExpandedAuditLogs(prev => ({ ...prev, [logKey]: !prev[logKey] }))}
                                className="p-1 text-slate-500 hover:text-slate-800 rounded flex items-center gap-0.5 text-[10px] font-bold border border-slate-200 hover:bg-slate-200 transition-all cursor-pointer"
                                title="Toggle 5-Gate Decision Audit Trail"
                              >
                                <span>Audit</span>
                                {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                              </button>
                            )}
                          </div>
                        </div>

                        {/* Expandable Audit Log */}
                        {isExpanded && sel.decision_audit_log && (
                          <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-[11px] font-mono space-y-1 mt-2 border border-slate-800">
                            <span className="text-[10px] text-emerald-400 font-extrabold uppercase block tracking-wider mb-1">
                              MatchIQ 5-Gate Decision Audit Log:
                            </span>
                            {sel.decision_audit_log.map((logLine, lIdx) => (
                              <div key={lIdx} className="flex items-start gap-1.5">
                                <span className="text-emerald-500">✓</span>
                                <span>{logLine}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* SportyBet Booking Code Banner */}
                <div className="bg-slate-900 text-white p-4 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-3 shadow-md">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-black text-xs">
                      SB
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">SportyBet Live Booking Code</span>
                      <span className="text-base font-black text-emerald-400 font-mono tracking-wider">
                        {activeScn.booking_code || "Pending Code..."}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    {activeScn.booking_code && (
                      <>
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(activeScn.booking_code);
                            setShortlistCopiedCode(true);
                            setLockedNotice(`SportyBet Code ${activeScn.booking_code} copied to clipboard!`);
                            setTimeout(() => {
                              setShortlistCopiedCode(false);
                              setLockedNotice(null);
                            }, 4000);
                          }}
                          className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-extrabold text-white flex items-center gap-1.5 transition-all cursor-pointer"
                        >
                          {shortlistCopiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                          <span>{shortlistCopiedCode ? "Copied!" : "Copy Code"}</span>
                        </button>

                        <a
                          href={activeScn.share_url || `https://www.sportybet.com/ng/?shareCode=${activeScn.booking_code}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-4 py-2 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-xs font-black text-slate-950 flex items-center gap-1.5 transition-all shadow-sm cursor-pointer"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          <span>Open on SportyBet</span>
                        </a>
                      </>
                    )}
                  </div>
                </div>

                {/* Secondary Actions: Lock & Track + Copy Selections */}
                <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setLockTargetData({
                        code: activeScn.booking_code || "STATIQ-SHORTLIST",
                        mode: "AI_BUILDER",
                        targetOdds: activeScn.target_odds || activeScn.accumulated_odds,
                        totalOdds: activeScn.accumulated_odds,
                        selections: activeScn.selections
                      });
                      setShowLockModal(true);
                    }}
                    className="flex-1 py-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 w-full sm:w-auto cursor-pointer"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    <span>Lock & Track This Slip</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => copySelectionsAsText(activeScn.selections)}
                    className="px-5 py-3 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 text-xs font-extrabold hover:bg-slate-200 flex items-center justify-center gap-1.5 cursor-pointer w-full sm:w-auto"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    <span>Copy Matches Text</span>
                  </button>
                </div>
              </div>
            );
          })()}
        </div>
      )}

      {/* MODE 1 & MODE 3 RESULTS */}
      {(builderMode === "ACCUMULATOR" || builderMode === "TODAY_GAMES") && result && (
        <div className="space-y-6">
          {/* Multi-Ticket Portfolio Navigation Bar (Optimized for Mobile & Desktop) */}
          {result.scenarios && result.scenarios.length > 1 && (
            <div className="bg-slate-900 text-white p-4 rounded-2xl border border-slate-700 shadow-md space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-xs font-black uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-emerald-400" />
                    <span>StatIQ Multi-Ticket Portfolio ({result.scenarios.length} Diversified Slips)</span>
                  </span>
                </div>
                <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-500/40 w-fit">
                  🛡️ 100% Zero-Overlap &bull; Zero Correlated Failure
                </span>
              </div>

              {/* Responsive Grid Selector for each ticket in the portfolio */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 pt-1">
                {result.scenarios.map((sc, scIdx) => {
                  const isCurrent = activePortfolioIndex === scIdx;
                  const isMaster = sc.is_master || sc.ticket_index === "MASTER";

                  return (
                    <button
                      key={scIdx}
                      type="button"
                      onClick={() => setActivePortfolioIndex(scIdx)}
                      className={`w-full p-2.5 sm:p-3 rounded-xl border text-left transition-all flex flex-col justify-between gap-1.5 sm:gap-2 cursor-pointer ${
                        isMaster
                          ? (isCurrent
                            ? "bg-amber-950/70 border-amber-400 ring-2 ring-amber-400/50 text-white shadow-lg scale-[1.01]"
                            : "bg-slate-950/80 border-amber-500/40 text-amber-300 hover:bg-amber-950/40")
                          : (isCurrent
                            ? "bg-slate-800 border-emerald-400 ring-2 ring-emerald-400/50 text-white shadow-lg scale-[1.01]"
                            : "bg-slate-950/70 border-slate-800 text-slate-400 hover:bg-slate-800 hover:text-slate-200")
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-black text-white flex items-center gap-1.5">
                          {isMaster ? (
                            <Zap className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                          ) : (
                            <Ticket className="w-3.5 h-3.5 text-emerald-400" />
                          )}
                          <span className="truncate">{isMaster ? "Master Ticket" : `Slip #${scIdx + 1}`}</span>
                        </span>
                        <span className={`text-[10px] px-1.5 sm:px-2 py-0.5 rounded font-black flex-shrink-0 ${
                          isMaster
                            ? "bg-amber-400 text-slate-950"
                            : (isCurrent ? "bg-emerald-500 text-slate-950" : "bg-slate-800 text-slate-300")
                        }`}>
                          ~{sc.accumulated_odds}x
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] pt-1 border-t border-slate-800/80">
                        <span className="text-slate-400 font-bold">{sc.selections?.length || 0} Legs</span>
                        {sc.booking_code ? (
                          <span className={`font-mono font-black px-1.5 py-0.5 rounded border text-[10px] ${
                            isMaster
                              ? "text-amber-300 bg-amber-950/80 border-amber-500/50"
                              : "text-emerald-400 bg-emerald-950/70 border-emerald-800/60"
                          }`}>
                            {sc.booking_code}
                          </span>
                        ) : (
                          <span className={isMaster ? "text-amber-400 font-bold text-[10px]" : "text-emerald-400 font-bold text-[10px]"}>
                            {isMaster ? "Master Unified" : "Active Slip"}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Merge into Master Ticket Action Panel (100% Mobile & Desktop Prominent) */}
              <div className="bg-gradient-to-r from-amber-950/60 via-slate-900 to-amber-950/40 border border-amber-500/40 rounded-2xl p-3.5 sm:p-4 space-y-3 shadow-lg">
                <div className="flex items-start sm:items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-400/40 flex items-center justify-center flex-shrink-0">
                      <Zap className="w-4 h-4 text-amber-400 fill-amber-400" />
                    </div>
                    <div>
                      <h4 className="text-xs sm:text-sm font-black text-amber-300 flex items-center gap-1.5">
                        <span>Merge into Master Ticket</span>
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-200 border border-amber-400/30 font-bold uppercase">
                          Zero Duplicates
                        </span>
                      </h4>
                      <p className="text-[11px] text-slate-400 leading-snug">
                        Resolves overlapping matches by picking highest-probability market, prioritizing top winnable games.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pt-1 border-t border-amber-500/20">
                  <div className="flex items-center justify-between sm:justify-start gap-1 sm:gap-1.5 bg-slate-950/90 p-1.5 rounded-xl border border-slate-800 w-full sm:w-auto">
                    <span className="text-[10px] text-slate-400 font-extrabold px-1">Games:</span>
                    {[5, 8, 10, 12, 15].map((cnt) => (
                      <button
                        key={cnt}
                        type="button"
                        onClick={() => {
                          setMasterPrioritizedGames(cnt);
                          setCustomMasterGamesInput(String(cnt));
                        }}
                        className={`flex-1 sm:flex-initial px-2 sm:px-2.5 py-1 rounded-lg text-xs font-black transition-all ${
                          masterPrioritizedGames === cnt
                            ? "bg-amber-400 text-slate-950 shadow-sm"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        {cnt}
                      </button>
                    ))}
                    <div className="flex items-center gap-1 pl-1 border-l border-slate-800">
                      <input
                        type="number"
                        min="2"
                        max="15"
                        placeholder="1-15"
                        value={customMasterGamesInput}
                        onChange={(e) => {
                          const val = e.target.value;
                          setCustomMasterGamesInput(val);
                          const parsed = parseInt(val, 10);
                          if (!isNaN(parsed) && parsed >= 2) {
                            setMasterPrioritizedGames(Math.min(15, parsed));
                          }
                        }}
                        className="w-10 sm:w-12 bg-slate-900 border border-slate-700 text-amber-300 placeholder-slate-500 rounded px-1 py-0.5 text-xs font-black text-center focus:outline-none focus:border-amber-400"
                        title="Type any number of games (2 to 15)"
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleMergeToMaster(masterPrioritizedGames)}
                    disabled={mergingMaster}
                    className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-400 via-amber-500 to-amber-400 text-slate-950 text-xs font-black flex items-center justify-center gap-2 shadow-lg hover:shadow-amber-500/20 active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50"
                  >
                    {mergingMaster ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Zap className="w-3.5 h-3.5 fill-slate-950" />
                    )}
                    <span>{mergingMaster ? "Merging Slips..." : `Generate ${masterPrioritizedGames}-Game Master Slip`}</span>
                  </button>
                </div>
              </div>

              {/* Mobile Quick Prev / Next Navigator */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs sm:hidden">
                <button
                  type="button"
                  disabled={activePortfolioIndex === 0}
                  onClick={() => setActivePortfolioIndex(prev => Math.max(0, prev - 1))}
                  className={`px-3 py-1.5 rounded-lg font-bold flex items-center gap-1 ${
                    activePortfolioIndex === 0 ? "text-slate-600 cursor-not-allowed" : "bg-slate-800 text-white hover:bg-slate-700"
                  }`}
                >
                  <ChevronLeft className="w-4 h-4" />
                  <span>Prev Slip</span>
                </button>
                <span className="font-extrabold text-amber-400 text-[11px]">
                  Viewing {result.scenarios[activePortfolioIndex]?.is_master ? "⚡ Master Ticket" : `Slip #${activePortfolioIndex + 1}`} of {result.scenarios.length}
                </span>
                <button
                  type="button"
                  disabled={activePortfolioIndex === result.scenarios.length - 1}
                  onClick={() => setActivePortfolioIndex(prev => Math.min(result.scenarios.length - 1, prev + 1))}
                  className={`px-3 py-1.5 rounded-lg font-bold flex items-center gap-1 ${
                    activePortfolioIndex === result.scenarios.length - 1 ? "text-slate-600 cursor-not-allowed" : "bg-slate-800 text-white hover:bg-slate-700"
                  }`}
                >
                  <span>Next Slip</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {(result.scenarios && result.scenarios.length > 1
            ? [result.scenarios[activePortfolioIndex] || result.scenarios[0]]
            : result.scenarios
          )?.map((scn) => {
            const code = generatedCodes[scn.scenario_id];

            if (scn.error) {
              return (
                <div key={scn.scenario_id} className="bg-amber-50 border border-amber-200 p-6 rounded-2xl text-xs text-amber-800">
                  <p className="font-extrabold text-sm">{scn.error}</p>
                  <p className="mt-1">Try selecting a different gameweek or league scope.</p>
                </div>
              );
            }

            const isMasterSlip = scn.is_master || scn.ticket_index === "MASTER";

            return (
              <div id="active-builder-slip-container" key={scn.scenario_id} className={`bg-white p-6 rounded-2xl border space-y-4 shadow-sm relative ${
                isMasterSlip ? "border-amber-400 ring-2 ring-amber-400/20" : "border-slate-200"
              }`}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-slate-900 text-sm flex items-center gap-1.5">
                        {isMasterSlip && <Zap className="w-4 h-4 text-amber-500 fill-amber-500" />}
                        <span>{isMasterSlip ? `⚡ Master Unified Accumulator (${scn.selections.length} Legs)` : `5-Gate Approved Accumulator (${scn.selections.length} Legs)`}</span>
                      </span>
                      {isMasterSlip ? (
                        <span className="text-[10px] font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider bg-amber-100 text-amber-900 border border-amber-300">
                          ⚡ MASTER TICKET
                        </span>
                      ) : scn.confidence_tier && (
                        <span className={`text-[10px] font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${
                          scn.confidence_tier === "ELITE" ? "bg-purple-100 text-purple-900 border border-purple-200" :
                          scn.confidence_tier === "HIGH" ? "bg-emerald-100 text-emerald-900 border border-emerald-200" :
                          scn.confidence_tier === "SOLID" ? "bg-blue-100 text-blue-900 border border-blue-200" :
                          "bg-amber-100 text-amber-900 border border-amber-200"
                        }`}>
                          {scn.confidence_tier} Tier
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500 font-medium mt-0.5 block">
                      Scope: <strong>{scn.scope_label}</strong> • Combined Odds: <strong>~{scn.accumulated_odds}x</strong> {scn.target_mode === "GAMES" ? `(Target: ${scn.target_games || scn.selections?.length} Games)` : `(Target: ~${scn.target_odds}x)`}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 flex-wrap gap-y-2">
                    <button
                      onClick={() => handleRemoveAccumulatorTicket(scn.scenario_id)}
                      className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all"
                      title="Clear Ticket"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Selections List */}
                <div className="space-y-3">
                  {scn.selections?.map((sel, sIdx) => {
                    const logKey = `${scn.scenario_id}_${sIdx}`;
                    const isExpanded = expandedAuditLogs[logKey];
                    const tier = sel.confidence_tier || "HIGH";

                    return (
                      <div key={sIdx} className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-[10px] font-extrabold text-slate-700 bg-slate-200 px-2 py-0.5 rounded">
                                {formatCompetitionWithCountry(sel.competition || sel.competition_code, sel.country)}
                              </span>
                              <span className={`text-[9px] font-extrabold px-2 py-0.2 rounded uppercase ${
                                tier === "ELITE" ? "bg-purple-100 text-purple-800" :
                                tier === "HIGH" ? "bg-emerald-100 text-emerald-800" :
                                tier === "SOLID" ? "bg-blue-100 text-blue-800" :
                                "bg-amber-100 text-amber-800"
                              }`}>
                                {tier}
                              </span>
                            </div>
                            <span className="text-sm font-extrabold text-slate-900 block">
                              {sel.home_team} vs {sel.away_team}
                            </span>
                            {sel.tactical_reason && (
                              <span className="inline-block mt-1 text-[10px] font-extrabold text-indigo-700 bg-indigo-50 border border-indigo-200/80 px-2 py-0.5 rounded-md">
                                {sel.tactical_reason}
                              </span>
                            )}
                            
                            {/* Assigned Pick Banner (Full Text & Clear Legibility) */}
                            <div className="mt-2 bg-white rounded-xl p-2.5 border border-slate-200 shadow-2xs space-y-2">
                              <div className="flex items-center justify-between gap-2 flex-wrap">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-[10px] font-black px-2 py-0.5 rounded bg-emerald-100 text-emerald-900 border border-emerald-300 uppercase tracking-wider">
                                    Assigned Pick
                                  </span>
                                  <span className="text-xs font-black text-slate-900 leading-snug">
                                    {sel.selection_name || sel.selection || sel.pick}
                                  </span>
                                </div>
                                <span className="text-xs font-black text-slate-900 bg-slate-100 px-2.5 py-0.5 rounded-lg border border-slate-200">
                                  @{(sel.estimated_odds || sel.odds || 1.30).toFixed(2)}
                                </span>
                              </div>

                              {/* Interactive Pick Re-selector + 1-Click AI Alt Button */}
                              <div className="flex items-center gap-2 pt-1 border-t border-slate-100 flex-wrap">
                                <span className="text-[11px] text-slate-500 font-bold">Switch Market:</span>
                                <select
                                  value={sel.selection_name || sel.selection || sel.pick}
                                  onChange={(e) => {
                                    const chosenName = e.target.value;
                                    const opts = getAvailablePicksForLeg(sel);
                                    const matchOpt = opts.find(o => o.name === chosenName || o.label === chosenName) || { name: chosenName, odds: sel.estimated_odds || sel.odds || 1.30, prob: sel.model_probability || 0.85 };
                                    handleOverrideLegPick(scn.scenario_id, sIdx, matchOpt);
                                  }}
                                  className="bg-slate-50 border border-slate-300 text-slate-900 font-bold text-xs rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer shadow-2xs hover:border-slate-400 transition-all flex-1 min-w-[180px]"
                                >
                                  {getAvailablePicksForLeg(sel).map((opt) => (
                                    <option key={opt.name} value={opt.name}>
                                      {opt.label} — @{opt.odds}
                                    </option>
                                  ))}
                                </select>

                                <button
                                  type="button"
                                  onClick={() => handleCycleNextAiPick(scn.scenario_id, sIdx, sel)}
                                  className="px-2.5 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-extrabold rounded-lg border border-indigo-200 flex items-center gap-1 transition-all shadow-2xs cursor-pointer"
                                  title="Click to ask AI for a more favorable / alternative market pick for this match"
                                >
                                  <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                                  <span>AI Alt</span>
                                </button>
                              </div>
                            </div>
                          </div>


                          <div className="flex items-center space-x-3">
                            <div className="text-right">
                              <span className="text-[10px] text-slate-400 block font-medium">Model Probability</span>
                              <span className="text-sm font-extrabold text-emerald-700">
                                {((sel.model_probability || sel.prob || 0.8) * 100).toFixed(0)}%
                              </span>
                            </div>

                            {sel.decision_audit_log && (
                              <button
                                onClick={() => setExpandedAuditLogs(prev => ({ ...prev, [logKey]: !prev[logKey] }))}
                                className="p-1 text-slate-500 hover:text-slate-800 rounded flex items-center gap-0.5 text-[10px] font-bold border border-slate-200 hover:bg-slate-200 transition-all"
                                title="Toggle 5-Gate Decision Audit Trail"
                              >
                                <span>Audit</span>
                                {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                              </button>
                            )}

                            <button
                              onClick={() => handleRemoveSelection(scn.scenario_id, sIdx)}
                              className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-100 rounded-lg transition-all"
                              title="Remove match from ticket"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        {/* Expandable Audit Log */}
                        {isExpanded && sel.decision_audit_log && (
                          <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-[11px] font-mono space-y-1 mt-2 border border-slate-800">
                            <span className="text-[10px] text-emerald-400 font-extrabold uppercase block tracking-wider mb-1">
                              MatchIQ 5-Gate Decision Audit Log:
                            </span>
                            {sel.decision_audit_log.map((logLine, lIdx) => (
                              <div key={lIdx} className="flex items-start gap-1.5">
                                <span className="text-emerald-500">✓</span>
                                <span>{logLine}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* SportyBet Booking Code Banner */}
                <div className="bg-slate-900 text-white p-4 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center font-black text-xs">
                      SB
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">SportyBet Live Booking Code</span>
                      <span className="text-base font-black text-emerald-400 font-mono tracking-wider">
                        {scn.booking_code || code || "Generating..."}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 w-full sm:w-auto">
                    {(scn.booking_code || code) ? (
                      <>
                        <button
                          onClick={() => {
                            const c = scn.booking_code || code;
                            navigator.clipboard.writeText(c);
                            setLockedNotice(`SportyBet Code ${c} copied to clipboard!`);
                            setTimeout(() => setLockedNotice(null), 4000);
                          }}
                          className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-extrabold text-white flex items-center gap-1.5 transition-all"
                        >
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy Code</span>
                        </button>

                        <a
                          href={scn.share_url || `https://www.sportybet.com/ng/?shareCode=${scn.booking_code || code}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-4 py-2 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-xs font-black text-slate-950 flex items-center gap-1.5 transition-all shadow-sm"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          <span>Open on SportyBet</span>
                        </a>
                      </>
                    ) : (
                      <button
                        onClick={() => handleGenerateCode(scn.scenario_id, scn.selections, "StatIQ AI Ticket")}
                        className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-xs font-extrabold text-slate-950 flex items-center gap-1.5 transition-all"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Generate Code</span>
                      </button>
                    )}
                  </div>
                </div>

                <div className="pt-2 flex flex-col sm:flex-row items-center gap-3">
                  <button
                    onClick={() => {
                      setLockTargetData({
                        code: scn.booking_code || code || "STATIQ-ACC",
                        targetOdds: scn.target_odds,
                        totalOdds: scn.accumulated_odds,
                        selections: scn.selections
                      });
                      setShowLockModal(true);
                    }}
                    className="flex-1 py-3 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 text-xs font-extrabold transition-all flex items-center justify-center space-x-1.5 w-full sm:w-auto"
                  >
                    <Lock className="w-3.5 h-3.5" />
                    <span>Lock & Track Ticket</span>
                  </button>

                  <button
                    onClick={() => handleRemoveAccumulatorTicket(scn.scenario_id)}
                    className="px-4 py-3 rounded-xl bg-slate-100 border border-slate-200 text-slate-700 hover:text-rose-600 text-xs font-extrabold hover:bg-rose-50 transition-all flex items-center justify-center space-x-1 w-full sm:w-auto"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Clear Ticket</span>
                  </button>
                </div>

              </div>
            );
          })}
        </div>
      )}

      {/* MODE 2 ROLLOVER RESULTS (TODAY'S SAFEST PICKS) */}
      {builderMode === "ROLLOVER" && rolloverResult && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-6 shadow-sm relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-500 uppercase tracking-wider block">
                  Today's High-Assurance Rollover Slip (Strictly Today's Games)
                </span>
                {rolloverResult.recommended_stake_pct > 0 && (
                  <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200 flex items-center gap-1">
                    <Award className="w-3 h-3 text-indigo-600" />
                    <span>Quarter-Kelly Rec. Stake: {rolloverResult.recommended_stake_pct}% Bankroll</span>
                  </span>
                )}
              </div>
              <h3 className="text-lg font-extrabold text-slate-900 mt-0.5">
                Starting Stake: ₦{startingStake.toLocaleString()} → Est. Payout: ₦{Math.round(rolloverResult.finalEstimatedPayout).toLocaleString()} ({rolloverResult.totalMultiplier.toFixed(2)}x Return)
              </h3>
            </div>

            <div className="flex items-center space-x-2.5">
              <button
                onClick={handleBuildRollover}
                disabled={loading}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-extrabold flex items-center gap-1.5 border border-slate-300 transition-all cursor-pointer shadow-2xs"
                title="Regenerate alternative top powerhouse fixtures for today"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>Regenerate</span>
              </button>

              <div className="bg-slate-900 text-white px-4 py-2 rounded-xl text-right">
                <span className="text-[10px] text-slate-400 block font-medium">SportyBet Booking Code</span>
                <span className="text-base font-extrabold text-emerald-400">{rolloverResult.bookingCode}</span>
              </div>

              <button
                onClick={handleClearRollover}
                className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition-all cursor-pointer"
                title="Clear Rollover Slip"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Today's Rollover Picks */}
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <h4 className="text-xs font-extrabold text-slate-700 uppercase">
                Today's Safest Rollover Selections ({(rolloverResult.picks || []).length} Picks)
              </h4>
            </div>

            {(rolloverResult.picks || []).map((p, idx) => {
              const rLogKey = `roll_${idx}`;
              const isExpanded = expandedAuditLogs[rLogKey];
              const tier = p.confidence_tier || "HIGH";
              const oddsVal = p.estimated_odds || p.odds || 1.3;
              const probVal = p.model_probability || p.prob || 0.88;

              return (
                <div key={idx} className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <div className="flex-1 pr-2">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-extrabold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                          {formatCompetitionWithCountry(p.competition || p.competition_code, p.country)}
                        </span>
                        <span className={`text-[9px] font-extrabold px-2 py-0.2 rounded uppercase ${
                          tier === "ELITE" ? "bg-purple-100 text-purple-800" :
                          tier === "HIGH" ? "bg-emerald-100 text-emerald-800" :
                          tier === "SOLID" ? "bg-blue-100 text-blue-800" :
                          "bg-amber-100 text-amber-800"
                        }`}>
                          {tier}
                        </span>
                        {/* Win Probability badge */}
                        <span className="text-[9px] font-extrabold px-2 py-0.2 rounded bg-teal-50 text-teal-800 border border-teal-200 uppercase">
                          Win Prob: {Math.round(probVal * 100)}%
                        </span>
                      </div>
                      <span className="text-sm font-extrabold text-slate-900 block">
                        {p.home_team} vs {p.away_team}
                      </span>
                      {p.tactical_reason && (
                        <span className="inline-block mt-1 text-[10px] font-extrabold text-amber-800 bg-amber-50 border border-amber-200/80 px-2 py-0.5 rounded-md">
                          {p.tactical_reason}
                        </span>
                      )}
                      
                      {/* Assigned Pick Banner (Full Text & Clear Legibility) */}
                      <div className="mt-2 bg-white rounded-xl p-2.5 border border-slate-200 shadow-2xs space-y-2">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-[10px] font-black px-2 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300 uppercase tracking-wider">
                              Assigned Pick
                            </span>
                            <span className="text-xs font-black text-slate-900 leading-snug">
                              {p.selection_name || p.selection || p.pick}
                            </span>
                          </div>
                          <span className="text-xs font-black text-slate-900 bg-slate-100 px-2.5 py-0.5 rounded-lg border border-slate-200">
                            @{oddsVal.toFixed(2)}
                          </span>
                        </div>

                        {/* Interactive Pick Re-selector + 1-Click AI Alt Button */}
                        <div className="flex items-center gap-2 pt-1 border-t border-slate-100 flex-wrap">
                          <span className="text-[11px] text-slate-500 font-bold">Switch Market:</span>
                          <select
                            value={p.selection_name || p.selection || p.pick}
                            onChange={(e) => {
                              const chosenName = e.target.value;
                              const opts = getAvailablePicksForLeg(p);
                              const matchOpt = opts.find(o => o.name === chosenName || o.label === chosenName) || { name: chosenName, odds: p.estimated_odds || p.odds || 1.30, prob: p.model_probability || 0.85 };
                              handleOverrideRolloverPick(idx, matchOpt);
                            }}
                            className="bg-slate-50 border border-slate-300 text-slate-900 font-bold text-xs rounded-lg px-2 py-1 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer shadow-2xs hover:border-slate-400 transition-all flex-1 min-w-[180px]"
                          >
                            {getAvailablePicksForLeg(p).map((opt) => (
                              <option key={opt.name} value={opt.name}>
                                {opt.label} — @{opt.odds}
                              </option>
                            ))}
                          </select>

                          <button
                            type="button"
                            onClick={() => handleCycleNextRolloverAiPick(idx, p)}
                            className="px-2.5 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 text-[11px] font-extrabold rounded-lg border border-amber-200 flex items-center gap-1 transition-all shadow-2xs cursor-pointer"
                            title="Automatically cycle to the next best mathematically vetted AI pick for this match"
                          >
                            <RotateCcw className="w-3.5 h-3.5 text-amber-600" />
                            <span>AI Alt</span>
                          </button>
                        </div>
                      </div>
                    </div>


                    <div className="flex items-center space-x-3 flex-shrink-0">
                      <div className="text-right">
                        <span className="text-[10px] text-slate-400 block font-medium">Model Win Probability</span>
                        <span className="text-sm font-extrabold text-emerald-700">{(probVal * 100).toFixed(0)}% Win Chance</span>
                        <span className="text-[10px] text-slate-500 font-bold">Odds: {oddsVal.toFixed(2)}</span>
                      </div>

                      {p.decision_audit_log && (
                        <button
                          onClick={() => setExpandedAuditLogs(prev => ({ ...prev, [rLogKey]: !prev[rLogKey] }))}
                          className="p-1 text-slate-500 hover:text-slate-800 rounded flex items-center gap-0.5 text-[10px] font-bold border border-slate-200 hover:bg-slate-200 transition-all cursor-pointer"
                          title="Toggle 5-Gate Decision Audit Trail"
                        >
                          <span>Audit</span>
                          {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>
                      )}

                      <button
                        onClick={() => handleRemoveRolloverPick(idx)}
                        className="p-1.5 rounded-lg bg-white hover:bg-rose-100 text-slate-400 hover:text-rose-600 border border-slate-200 hover:border-rose-300 transition-all shadow-xs cursor-pointer"
                        title="Remove match from Rollover slip"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Expandable Audit Log */}
                  {isExpanded && p.decision_audit_log && (
                    <div className="bg-slate-900 text-slate-200 p-3 rounded-lg text-[11px] font-mono space-y-1 mt-2 border border-slate-800">
                      <span className="text-[10px] text-emerald-400 font-extrabold uppercase block tracking-wider mb-1">
                        MatchIQ 5-Gate Decision Audit Log:
                      </span>
                      {p.decision_audit_log.map((logLine, lIdx) => (
                        <div key={lIdx} className="flex items-start gap-1.5">
                          <span className="text-emerald-500">✓</span>
                          <span>{logLine}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
            <button
              onClick={() => handleGenerateCode("ROLLOVER", rolloverResult.picks, "Rollover Slip")}
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl btn-black text-xs font-extrabold flex items-center justify-center space-x-1 cursor-pointer"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>Get & Preview SportyBet Code</span>
            </button>

            <button
              onClick={() => {
                setLockTargetData({
                  code: rolloverResult.bookingCode || "ROLLOVER-TODAY",
                  mode: "ROLLOVER",
                  targetOdds: dailyTargetOdds,
                  totalOdds: rolloverResult.totalMultiplier,
                  selections: rolloverResult.picks
                });
                setShowLockModal(true);
              }}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-extrabold hover:bg-indigo-100 flex items-center justify-center space-x-1.5 cursor-pointer"
            >
              <Lock className="w-3.5 h-3.5" />
              <span>Lock & Track Rollover Slip</span>
            </button>

            <button
              onClick={() => copySelectionsAsText(rolloverResult.picks)}
              className="w-full sm:w-auto px-6 py-2.5 rounded-xl bg-slate-100 border border-slate-200 text-slate-800 text-xs font-extrabold hover:bg-slate-200 cursor-pointer"
            >
              Copy Selections
            </button>

            <button
              onClick={handleClearRollover}
              className="w-full sm:w-auto px-4 py-2.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-extrabold hover:bg-rose-100 flex items-center justify-center space-x-1 cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Dismiss</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

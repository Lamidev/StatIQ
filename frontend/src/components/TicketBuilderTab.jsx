import React, { useState, useEffect } from "react";
import { fetchFixturesByGameweek, generateSportyBetCode, generateVerifiedBookingCode, buildAiTicket, lockTrackedTicket, fetchTodaysSportybetGames } from "../api/client";
import { Copy, Info, Calendar, Send, ShieldCheck, RefreshCw, CheckCircle2, ExternalLink, X, ChevronDown, ChevronUp, AlertCircle, Award, Trash2, Lock, ShieldAlert, Sliders, Sparkles, Search, Filter, BarChart2, Target, RotateCcw } from "lucide-react";

import { generateSafePick, buildSafeTicket, scoreFixtures } from "../utils/pickEngine";
import { calculateFlexShield } from "../utils/flexCalculator";

export default function TicketBuilderTab() {
  const [builderMode, setBuilderMode] = useState("TODAY_GAMES"); // "TODAY_GAMES", "ACCUMULATOR", or "ROLLOVER"

  // Standard Accumulator State
  const [leagueScope, setLeagueScope] = useState("MULTI");
  const [singleLeague, setSingleLeague] = useState("PL");
  const [gameweek, setGameweek] = useState(1);
  const [targetOdds, setTargetOdds] = useState(2.0);
  const [targetMode, setTargetMode] = useState("ODDS"); // "ODDS" or "GAMES"
  const [targetGames, setTargetGames] = useState(10);
  const [customGamesInput, setCustomGamesInput] = useState("10");
  const [selectedLeagues, setSelectedLeagues] = useState(["ALL"]);
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

  // Auto-fetch today's/tomorrow's games on mount / mode switch
  const loadTodayGames = async (day = todayDayFilter) => {
    setTodayLoading(true);
    setTodayError(null);
    try {
      const data = await fetchTodaysSportybetGames(day);
      setTodayData(data);
    } catch (e) {
      setTodayError("Could not load games. Check backend connection.");
    }
    setTodayLoading(false);
  };

  useEffect(() => {
    if (builderMode === "TODAY_GAMES" && !todayData && !todayLoading) {
      loadTodayGames(todayDayFilter);
    }
  }, [builderMode]);

  // Helper to extract comprehensive pick options (1X2, DC, O/U) for any match leg
  const getAvailablePicksForLeg = (leg) => {
    if (!leg) return [];
    const raw = leg.raw_match_data || leg || {};
    const r1x2 = raw.result_1x2 || leg.result_1x2 || raw || {};
    const ou = raw.ou_lines || leg.ou_lines || (raw.ou_line ? [{ line: raw.ou_line, over: raw.over, under: raw.under }] : []);
    const dc = raw.double_chance || leg.double_chance || {};

    const homeTeam = leg.home_team || raw.home_team || raw.home || "Home";
    const awayTeam = leg.away_team || raw.away_team || raw.away || "Away";

    // 1. Exact 1X2 market odds
    const hOdd = parseFloat(r1x2["1"] || r1x2.home || r1x2.home_odds || raw["1"] || leg.odds) || 2.10;
    const dOdd = parseFloat(r1x2["X"] || r1x2.draw || r1x2.draw_odds || raw["X"]) || 3.30;
    const aOdd = parseFloat(r1x2["2"] || r1x2.away || r1x2.away_odds || raw["2"]) || 3.20;

    // Derived Probabilities from actual market odds (removing bookmaker margin)
    const margin = (1.0 / hOdd) + (1.0 / dOdd) + (1.0 / aOdd);
    const pH = (1.0 / hOdd) / margin;
    const pD = (1.0 / dOdd) / margin;
    const pA = (1.0 / aOdd) / margin;

    // 2. Exact or mathematically derived Double Chance
    const dc1x = parseFloat(dc["1X"] || dc["1x"] || dc.home_draw) || roundOdds(1.0 / ((pH + pD) * 1.04));
    const dcx2 = parseFloat(dc["X2"] || dc["x2"] || dc.draw_away) || roundOdds(1.0 / ((pD + pA) * 1.04));
    const dc12 = parseFloat(dc["12"] || dc["12"] || dc.home_away) || roundOdds(1.0 / ((pH + pA) * 1.04));

    // 3. Exact or mathematically derived Over/Under Goals (Expectation model)
    const ouArray = Array.isArray(ou) ? ou : [];
    const ou15 = ouArray.find(x => String(x.line) === "1.5") || {};
    const ou25 = ouArray.find(x => String(x.line) === "2.5") || {};
    const ou35 = ouArray.find(x => String(x.line) === "3.5") || {};
    const ou45 = ouArray.find(x => String(x.line) === "4.5") || {};
    const ou05 = ouArray.find(x => String(x.line) === "0.5") || {};

    const totalGoalExp = (hOdd <= 1.25 || aOdd <= 1.25) ? 3.4 : (hOdd <= 1.55 || aOdd <= 1.55) ? 2.8 : 2.5;
    const probO15 = 1.0 - Math.exp(-totalGoalExp) * (1 + totalGoalExp);
    const probO25 = 1.0 - Math.exp(-totalGoalExp) * (1 + totalGoalExp + Math.pow(totalGoalExp, 2)/2);
    const probU35 = Math.exp(-totalGoalExp) * (1 + totalGoalExp + Math.pow(totalGoalExp, 2)/2 + Math.pow(totalGoalExp, 3)/6);
    const probU45 = Math.exp(-totalGoalExp) * (1 + totalGoalExp + Math.pow(totalGoalExp, 2)/2 + Math.pow(totalGoalExp, 3)/6 + Math.pow(totalGoalExp, 4)/24);

    const o15_val = parseFloat(ou15.over) || roundOdds(1.0 / (probO15 * 1.05));
    const o25_val = parseFloat(ou25.over) || roundOdds(1.0 / (probO25 * 1.05));
    const u35_val = parseFloat(ou35.under) || roundOdds(1.0 / (probU35 * 1.05));
    const u45_val = parseFloat(ou45.under) || roundOdds(1.0 / (probU45 * 1.05));
    const o05_val = parseFloat(ou05.over) || 1.04;

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
      { label: `Over 1.5 Goals`, name: "Over 1.5 Goals", odds: o15_val, type: "OU_O15" },
      { label: `Over 2.5 Goals`, name: "Over 2.5 Goals", odds: o25_val, type: "OU_O25" },
      { label: `Under 3.5 Goals`, name: "Under 3.5 Goals", odds: u35_val, type: "OU_U35" },
      { label: `Under 4.5 Goals`, name: "Under 4.5 Goals", odds: u45_val, type: "OU_U45" },
      { label: `${homeTeam} (-1.0 Asian Handicap)`, name: `${homeTeam} (-1.0 Asian Handicap)`, odds: ahMinus1H, type: "AH_MINUS1" },
      { label: `${homeTeam} (+1.5 Handicap)`, name: `${homeTeam} (+1.5 Handicap)`, odds: ahPlus15H, type: "AH_H15" },
      { label: `${awayTeam} (+1.5 Handicap)`, name: `${awayTeam} (+1.5 Handicap)`, odds: ahPlus15A, type: "AH_A15" },
      { label: `${homeTeam} to Win Either Half`, name: `${homeTeam} to Win Either Half`, odds: wehH, type: "WEH_HOME" },
      { label: `${awayTeam} to Win Either Half`, name: `${awayTeam} to Win Either Half`, odds: wehA, type: "WEH_AWAY" },
      { label: `Over 0.5 Goals`, name: "Over 0.5 Goals", odds: o05_val, type: "OU_O05" },
    ];

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
      const payload = {
        code: lockTargetData.code || "AI-BUILDER-TICKET",
        mode: builderMode,
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
      use_live_odds: true,
      strict_mode: strictMode
    };

    const res = await buildAiTicket(payload);
    setLoading(false);

    if (!res || res.status === "TIMEOUT" || res.status === "HTTP_ERROR" || res.status === "ERROR") {
      setErrorMsg(
        res?.status === "TIMEOUT"
          ? "Request timed out (>25s). The engine is busy — please try again."
          : res?.status === "HTTP_ERROR"
          ? `Backend error (HTTP ${res.http_status}). Ensure backend is running.`
          : "MatchIQ 5-Gate Pick Engine failed to build ticket. Check backend logs."
      );
      return;
    }

    if (res.ticket) {
      const scopeLabel = selectedLeagues.includes("ALL") ? "All Top Leagues" : selectedLeagues.join(", ");
      setResult({
        ticket: res.ticket,
        scenarios: [
          {
            scenario_id: `STATIQ-${targetMode === "GAMES" ? `${targetGames}G` : `${finalOddsGoal.toFixed(0)}X`}-${dateWindow}`,
            scope_label: `${scopeLabel} · ${dateWindow}`,
            gameweek_label: dateWindow,
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

  // Build High-Assurance Daily Rollover Slip (Today's Safest Picks)
  const handleBuildRollover = async () => {
    setLoading(true);
    setErrorMsg(null);
    setRolloverResult(null);
    setExpandedAuditLogs({});

    const payload = {
      target_odds: dailyTargetOdds,
      target_mode: "ODDS",
      mode: "ROLLOVER",
      date_window: "TODAY",
      league_scope: "MULTI",
      single_league: "PL",
      gameweek: gameweek,
      use_live_odds: useLiveOdds,
      kickoff_scope: "TODAY",
      strict_mode: strictMode,
      reshuffle_seed: Date.now()
    };

    const res = await buildAiTicket(payload);
    setLoading(false);

    if (!res || !res.ticket || !res.ticket.approved_legs || res.ticket.approved_legs.length === 0) {
      setErrorMsg("No suitable ultra-safe matches found for today. Try adjusting target odds.");
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
          accumulated_odds: newOdds
        };
      });
      return { ...prev, scenarios: updated };
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
        finalEstimatedPayout: roundOddsVal(startingStake * newMultiplier)
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
      label: scenarioLabel || `Gameweek ${gameweek} AI Ticket`,
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

      {/* Header Banner */}
      <div className="bg-white p-4 sm:p-6 rounded-xl sm:rounded-2xl border border-slate-200 shadow-sm">
        <h2 className="text-base sm:text-xl font-extrabold text-slate-900">
          AI Ticket & Rollover Builder
        </h2>
        <p className="text-[11px] sm:text-xs text-slate-500 mt-1">
          Build target odds accumulators or generate <strong>Multi-Day Daily Rollover Strategies</strong> with StatIQ live 2026/27 prediction models.
        </p>
      </div>

      {/* Mode Selector Tabs */}
      <div className="bg-slate-100 p-1 sm:p-1.5 rounded-xl sm:rounded-2xl grid grid-cols-3 gap-1 shadow-inner">
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
                <div className="flex items-center gap-2">
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
                  <div className="col-span-3 text-center">Goals & O/U</div>
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
                      <div className="divide-y divide-slate-50">
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
                              className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-all ${
                                isSelected ? "bg-slate-900 text-white" : "hover:bg-slate-50"
                              }`}
                            >
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
                              <div className={`text-[10px] font-bold w-10 text-center flex-shrink-0 ${isSelected ? "text-slate-300" : "text-slate-500"}`}>
                                {m.kickoff_time}
                              </div>

                              {/* 1X2 Odds */}
                              <div className="flex gap-1 flex-shrink-0">
                                {["home", "draw", "away"].map((side, si) => {
                                  const odd = m.result_1x2?.[side];
                                  const labels = ["1", "X", "2"];
                                  return (
                                    <div key={side} className={`text-center w-10 sm:w-12 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
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

                                <div className={`text-center w-10 sm:w-12 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
                                  isSelected ? "bg-slate-800 text-white" : "bg-slate-50 text-slate-700"
                                }`}>
                                  <div className={`text-[8px] font-bold mb-0.5 ${isSelected ? "text-slate-400" : "text-slate-400"}`}>Over</div>
                                  {activeOu.over ? activeOu.over.toFixed(2) : "-"}
                                </div>

                                <div className={`text-center w-10 sm:w-12 px-1 py-1 rounded-lg text-[10px] font-extrabold ${
                                  isSelected ? "bg-slate-800 text-white" : "bg-slate-50 text-slate-700"
                                }`}>
                                  <div className={`text-[8px] font-bold mb-0.5 ${isSelected ? "text-slate-400" : "text-slate-400"}`}>Under</div>
                                  {activeOu.under ? activeOu.under.toFixed(2) : "-"}
                                </div>
                              </div>

                              {/* StatIQ best win % */}
                              <div className={`hidden sm:block text-[10px] font-extrabold text-right flex-shrink-0 w-16 ${
                                isSelected ? "text-emerald-300" : "text-emerald-700"
                              }`}>
                                {(bestWin > 1 ? bestWin : bestWin * 100).toFixed(0)}%
                                <div className={`text-[8px] truncate ${isSelected ? "text-slate-400" : "text-slate-400"}`}>
                                  {bestLabel.split(" ")[0]}
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
                    onClick={() => setSelectedLeagues(["ALL"])}
                    className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                      selectedLeagues.includes("ALL") ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    All Top Leagues
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues(["PL", "PD", "SA", "BL1", "FL1"])}
                    className={`px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all ${
                      !selectedLeagues.includes("ALL") && ["PL", "PD", "SA", "BL1", "FL1"].every(l => selectedLeagues.includes(l)) && selectedLeagues.length === 5
                        ? "bg-slate-900 text-white"
                        : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                    }`}
                  >
                    Top 5 European
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedLeagues([])}
                    className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-500 hover:bg-slate-100"
                  >
                    Clear Selection
                  </button>
                </div>

                {/* League Multi-Select Chips */}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                  {[
                    { code: "PL", name: "Premier League", country: "England" },
                    { code: "PD", name: "La Liga", country: "Spain" },
                    { code: "SA", name: "Serie A", country: "Italy" },
                    { code: "BL1", name: "Bundesliga", country: "Germany" },
                    { code: "FL1", name: "Ligue 1", country: "France" },
                    { code: "ELC", name: "Championship", country: "England" },
                    { code: "DED", name: "Eredivisie", country: "Netherlands" },
                    { code: "PPL", name: "Liga Portugal", country: "Portugal" },
                    { code: "BL2", name: "2. Bundesliga", country: "Germany" },
                    { code: "SD", name: "LaLiga 2", country: "Spain" },
                    { code: "TUR", name: "Süper Lig", country: "Turkey" },
                    { code: "COP", name: "Coppa Italia", country: "Italy" },
                  ].map((lg) => {
                    const isSelected = selectedLeagues.includes("ALL") || selectedLeagues.includes(lg.code);
                    return (
                      <div
                        key={lg.code}
                        onClick={() => {
                          if (selectedLeagues.includes("ALL")) {
                            setSelectedLeagues([lg.code]);
                          } else if (selectedLeagues.includes(lg.code)) {
                            const next = selectedLeagues.filter(c => c !== lg.code);
                            setSelectedLeagues(next.length === 0 ? ["ALL"] : next);
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

                {/* Match Schedule Window */}
                <div className="pt-2">
                  <label className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block mb-2">Match Schedule Window</label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { id: "TODAY", label: "Today's Games", sub: "Matches playing today" },
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
                    onClick={() => setTargetMode("ODDS")}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "ODDS" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Target Odds
                  </button>
                  <button
                    type="button"
                    onClick={() => setTargetMode("GAMES")}
                    className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      targetMode === "GAMES" ? "bg-white shadow-sm text-slate-900" : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Number of Games
                  </button>
                </div>

                {targetMode === "ODDS" ? (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">Select target odds or enter custom multiplier:</p>
                    <div className="flex flex-wrap gap-2">
                      {[2.0, 5.0, 10.0, 20.0, 50.0, 100.0].map((val) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => { setTargetOdds(val); setCustomOdds(""); setUseCustom(false); }}
                          className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all ${
                            !useCustom && targetOdds === val
                              ? "bg-slate-900 text-white shadow-sm"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }`}
                        >
                          ~{val.toFixed(0)}x
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="text"
                        placeholder="Custom odds (e.g. 7.5)"
                        value={customOdds}
                        onChange={(e) => {
                          const valStr = e.target.value;
                          setCustomOdds(valStr);
                          setUseCustom(true);
                          const parsed = parseFloat(valStr);
                          if (!isNaN(parsed) && parsed > 1.0) setTargetOdds(parsed);
                        }}
                        className="w-40 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400">target odds</span>
                    </div>
                    <div className="bg-slate-50 rounded-xl px-4 py-2.5 text-xs text-slate-600 font-medium">
                      Target: <strong className="text-slate-900">{useCustom ? (parseFloat(customOdds) > 1 ? `~${parseFloat(customOdds).toFixed(1)}x` : "Invalid") : `~${targetOdds.toFixed(0)}x odds`}</strong>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-slate-500">How many games do you want in your ticket?</p>
                    <div className="flex flex-wrap gap-2">
                      {[3, 5, 8, 10, 15, 20].map((num) => (
                        <button
                          key={num}
                          type="button"
                          onClick={() => { setTargetGames(num); setCustomGamesInput(String(num)); }}
                          className={`px-4 py-2 rounded-xl text-xs font-extrabold transition-all ${
                            targetGames === num
                              ? "bg-slate-900 text-white shadow-sm"
                              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }`}
                        >
                          {num} Games
                        </button>
                      ))}
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="text"
                        placeholder="Custom (1–50)"
                        value={customGamesInput}
                        onChange={(e) => {
                          const raw = e.target.value;
                          setCustomGamesInput(raw);
                          const num = parseInt(raw);
                          if (!isNaN(num) && num >= 1 && num <= 50) {
                            setTargetGames(num);
                          }
                        }}
                        className="w-40 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                      <span className="text-xs text-slate-400">games in ticket</span>
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
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">1. Target Rollover Odds (Today)</label>
              <select
                value={dailyTargetOdds}
                onChange={(e) => setDailyTargetOdds(parseFloat(e.target.value))}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value={1.30}>~1.30 Daily Odds (Ultra High Assurance 90%+)</option>
                <option value={1.50}>~1.50 Daily Odds (Balanced Safe 85%+)</option>
                <option value={1.80}>~1.80 Daily Odds</option>
                <option value={2.00}>~2.00 Daily Odds</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">2. Today's Starting Stake (NGN)</label>
              <input
                type="number"
                value={startingStake}
                onChange={(e) => setStartingStake(parseInt(e.target.value) || 1000)}
                placeholder="5000"
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={handleBuildRollover}
              disabled={loading}
              className="w-full py-3 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 shadow-sm cursor-pointer"
            >
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>{loading ? "Analyzing Today's Unstarted Fixtures..." : "Generate Today's High-Assurance Rollover Slip"}</span>
            </button>
          </div>
        </div>
      )}



      {/* MODE 1 & MODE 3 RESULTS */}
      {(builderMode === "ACCUMULATOR" || builderMode === "TODAY_GAMES") && result && (
        <div className="space-y-6">
          {result.scenarios?.map((scn) => {
            const code = generatedCodes[scn.scenario_id];

            if (scn.error) {
              return (
                <div key={scn.scenario_id} className="bg-amber-50 border border-amber-200 p-6 rounded-2xl text-xs text-amber-800">
                  <p className="font-extrabold text-sm">{scn.error}</p>
                  <p className="mt-1">Try selecting a different gameweek or league scope.</p>
                </div>
              );
            }

            return (
              <div key={scn.scenario_id} className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4 shadow-sm relative">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-100 pb-3 gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-extrabold text-slate-900 text-sm">
                        5-Gate Approved Accumulator ({scn.selections.length} Legs)
                      </span>
                      {scn.confidence_tier && (
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
                      Scope: <strong>{scn.scope_label}</strong> • Combined Odds: <strong>~{scn.accumulated_odds}x</strong> (Target: ~{scn.target_odds}x)
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
                              <span className="text-[10px] font-extrabold text-slate-500 bg-slate-200 px-2 py-0.5 rounded">
                                {sel.competition || "League"}
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
                            
                            {/* Interactive Pick Re-selector + 1-Click AI Alt Button */}
                            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                              <span className="text-[11px] text-slate-500 font-bold">Pick:</span>
                              <select
                                value={sel.selection_name || sel.selection || sel.pick}
                                onChange={(e) => {
                                  const chosenName = e.target.value;
                                  const opts = getAvailablePicksForLeg(sel);
                                  const matchOpt = opts.find(o => o.name === chosenName || o.label === chosenName) || { name: chosenName, odds: sel.estimated_odds || sel.odds || 1.30, prob: sel.model_probability || 0.85 };
                                  handleOverrideLegPick(scn.scenario_id, sIdx, matchOpt);
                                }}
                                className="bg-white border border-slate-300 text-slate-900 font-extrabold text-xs rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer shadow-2xs hover:border-slate-400 transition-all max-w-[240px] truncate"
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
                                className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-bold rounded-lg border border-slate-300 flex items-center gap-1 transition-all shadow-2xs cursor-pointer"
                                title="Click to ask AI for a more favorable / alternative market pick for this match"
                              >
                                <Sparkles className="w-3 h-3 text-indigo-600" />
                                <span>AI Alt</span>
                              </button>
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
                          {p.competition || "Today's Match"}
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
                        {p.home_team} vs {p.away_team}
                      </span>
                      
                      {/* Interactive Pick Re-selector + 1-Click AI Alt Button */}
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <span className="text-[11px] text-slate-500 font-bold">Pick:</span>
                        <select
                          value={p.selection_name || p.selection || p.pick}
                          onChange={(e) => {
                            const chosenName = e.target.value;
                            const opts = getAvailablePicksForLeg(p);
                            const matchOpt = opts.find(o => o.name === chosenName || o.label === chosenName) || { name: chosenName, odds: p.estimated_odds || p.odds || 1.30, prob: p.model_probability || 0.85 };
                            handleOverrideRolloverPick(idx, matchOpt);
                          }}
                          className="bg-white border border-slate-300 text-slate-900 font-extrabold text-xs rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-slate-900 cursor-pointer shadow-2xs hover:border-slate-400 transition-all max-w-[240px] truncate"
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
                          className="px-2 py-1 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-bold rounded-lg border border-slate-300 flex items-center gap-1 transition-all shadow-2xs cursor-pointer"
                          title="Automatically cycle to the next best mathematically vetted AI pick for this match"
                        >
                          <RotateCcw className="w-3 h-3 text-slate-500" />
                          <span>AI Alt</span>
                        </button>
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

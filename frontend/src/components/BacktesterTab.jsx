import React, { useState } from "react";
import { Play, Lock, CheckCircle2, XCircle, Trash2, RefreshCw, AlertCircle, X, History, Sliders, Search, ShieldCheck, ShieldAlert, Sparkles } from "lucide-react";
import { decodeBookingCode, fetchFixturesByGameweek, fetchMatchStats } from "../api/client";
import { generateSafePick, evaluatePickResult, buildSafeTicket, fixtureSeed } from "../utils/pickEngine";
import { calculateFlexShield } from "../utils/flexCalculator";

export default function BacktesterTab() {
  const [testMode, setTestMode] = useState("ODDS"); // "ODDS", "EXPIRED_CODE", or "GAMEWEEK"
  const [season, setSeason] = useState(2025); // Historical Seasons: 2025 (2025/26), 2024 (2024/25), 2023 (2023/24), 2022 (2022/23), 2021 (2021/22)
  const [league, setLeague] = useState("ALL");
  const [gameweek, setGameweek] = useState(1);
  const [targetOdds, setTargetOdds] = useState(5.0);
  const [expiredCodeInput, setExpiredCodeInput] = useState("");
  const [codeTargetOdds, setCodeTargetOdds] = useState("ALL"); // Sub-feature target odds filter for expired codes ("ALL", "2.0", "3.0", "5.0", "10.0", "20.0")
  const [selectedFlexCut, setSelectedFlexCut] = useState("AUTO"); // Flex Cut Selector ("AUTO", "OFF", "1".."7")

  // Dynamic state for audit sessions
  const [auditing, setAuditing] = useState(false);
  const [unblinded, setUnblinded] = useState(false);
  const [auditRecord, setAuditRecord] = useState(null);

  // Modal UI state for clean delete confirmation
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  // ─── Pick Engine imported from ../utils/pickEngine.js ────────────────────
  // generateSafePick(fixture, usedTypeCounts) → { pick, prob, odds, marketType, tier }
  // evaluatePickResult(pick, hScore, aScore, homeTeam, awayTeam) → boolean
  // buildSafeTicket(fixtures, targetOdds) → { legs, cumulativeOdds }

  // Run Backtest Audit with Live API Integration for Real Finished Seasons
  const handleRunAudit = async () => {
    setAuditing(true);
    setUnblinded(false);

    if (testMode === "EXPIRED_CODE") {
      // Decode expired booking code via backend
      const decoded = await decodeBookingCode(expiredCodeInput);

      if (!decoded.selections || decoded.selections.length === 0) {
        // No selections returned — the code was not found, expired, or the API rejected it
        const reason = decoded.status === "TIMEOUT"
          ? `Request timed out. The booking provider may be slow or unreachable. Try again.`
          : decoded.status === "HTTP_ERROR"
            ? `Server returned an error (HTTP ${decoded.http_status}). The code may have expired or been removed.`
            : `Booking code "${expiredCodeInput.toUpperCase()}" was not found. Please double-check the code and try again.`;

        setAuditRecord({
          mode: "EXPIRED_CODE",
          code: expiredCodeInput.toUpperCase(),
          error: reason,
          matches: [],
          combinedOdds: 0,
          wonCount: 0,
          totalCount: 0,
          allWon: false,
        });
        setTimeout(() => { setUnblinded(true); setAuditing(false); }, 400);
        return;
      }

      // Parse finished scores for all valid selections
      const rawFixturesFromCode = decoded.selections.map((s, idx) => {
        let hScore = null, aScore = null;
        if (s.score && s.score.includes(":")) {
          const parts = s.score.split(":");
          hScore = parseInt(parts[0]);
          aScore = parseInt(parts[1]);
        } else if (s.score && s.score.includes("-")) {
          const parts = s.score.split("-");
          hScore = parseInt(parts[0]);
          aScore = parseInt(parts[1]);
        }

        if (hScore === null || isNaN(hScore) || aScore === null || isNaN(aScore)) {
          return null;
        }

        const origPickStr = s.selection_name ? `${s.selection_name} (${s.market_name || "Market"})` : (s.market_name || "Original Selection");
        return {
          id: idx + 1000,
          home_team: s.home_team || "Home Team",
          away_team: s.away_team || "Away Team",
          competition_code: s.league || "Domestic League",
          home_score: hScore,
          away_score: aScore,
          originalPick: origPickStr,
          odds: s.odds || 1.30,
        };
      }).filter(Boolean);

      if (rawFixturesFromCode.length === 0) {
        setAuditRecord({
          mode: "EXPIRED_CODE",
          code: expiredCodeInput.toUpperCase(),
          error: `No finished match scores found for code "${expiredCodeInput.toUpperCase()}". Matches may be upcoming or nulled.`,
          matches: [], combinedOdds: 0, wonCount: 0, totalCount: 0, allWon: false
        });
        setTimeout(() => { setUnblinded(true); setAuditing(false); }, 400);
        return;
      }

      let selectionsToAudit = [];

      // ─── Step 1: Generate all picks ───────────────────────────────────────
      let rawPickList = [];
      if (codeTargetOdds === "ALL") {
        const usedTypeCounts = {};
        rawPickList = rawFixturesFromCode.map((f) => {
          const matchIQPick = generateSafePick(f, usedTypeCounts, true);
          usedTypeCounts[matchIQPick.marketType] = (usedTypeCounts[matchIQPick.marketType] || 0) + 1;
          return { fixture: f, pick: matchIQPick };
        });
      } else {
        const targetVal = parseFloat(codeTargetOdds);
        const offsetMap = { 2.0: 0, 3.0: 2, 5.0: 4, 10.0: 7, 20.0: 11, 50.0: 15 };
        const partOffset = offsetMap[targetVal] ?? Math.round(targetVal);
        const maxLegsForTarget = targetVal >= 50 ? 20 : targetVal >= 20 ? 16 : targetVal >= 10 ? 12 : 10;
        const { legs } = buildSafeTicket(rawFixturesFromCode, targetVal, {
          maxLegs: maxLegsForTarget,
          isBacktest: true,
          partitionOffset: partOffset
        });
        rawPickList = legs.map((leg) => ({ fixture: null, leg, pick: { pick: leg.prediction, odds: leg.odds, prob: leg.prob } }));
      }

      // ─── Step 2: Batch-fetch real stats for stat-dependent picks ──────────
      // Only fetches for corners, 1st half over, win either half — conserves API budget
      const statQueryMatches = rawPickList.map((item, i) => {
        const f = item.fixture;
        const leg = item.leg;
        return {
          home_team: f ? f.home_team : (leg?.home || ""),
          away_team: f ? f.away_team : (leg?.away || ""),
          pick: item.pick.pick,
          match_date: null, // SportyBet codes don't expose date; API-Football will search by team name
        };
      });
      const statsResponse = await fetchMatchStats(statQueryMatches);
      const realStatsMap = statsResponse?.stats || {};

      // ─── Step 3: Evaluate picks with real stats injected ──────────────────
      if (codeTargetOdds === "ALL") {
        selectionsToAudit = rawPickList.map((item, idx) => {
          const f = item.fixture;
          const matchIQPick = item.pick;
          const realStats = realStatsMap[String(idx)] || null;
          const evalRes = evaluatePickResult(matchIQPick.pick, f.home_score, f.away_score, f.home_team, f.away_team, realStats);
          const isUnverified = evalRes === "UNVERIFIED";
          const isVoid = evalRes === "VOID";
          const isWin = isUnverified ? false : isVoid ? true : evalRes;
          return {
            id: f.id,
            leagueName: f.competition_code,
            home: f.home_team,
            away: f.away_team,
            prediction: matchIQPick.pick,
            originalPick: f.originalPick,
            odds: isVoid ? 1.00 : (matchIQPick.odds || f.odds),
            origOdds: matchIQPick.odds || f.odds,
            prob: matchIQPick.prob || 78,
            actualHome: f.home_score,
            actualAway: f.away_score,
            isWin,
            isVoid,
            isUnverified,
            realStats,
            reason: isUnverified
              ? `StatIQ Brain Audit: StatIQ predicted [${matchIQPick.pick}]. Score: ${f.home_team} ${f.home_score} - ${f.away_score} ${f.away_team}. ⚠️ UNVERIFIED — this pick requires real match statistics (corners/halftime) not available from score data alone.`
              : isVoid
              ? `StatIQ Brain Audit: StatIQ predicted [${matchIQPick.pick}]. Actual final score: ${f.home_team} ${f.home_score} - ${f.away_score} ${f.away_team} → 🔄 VOID / PUSH (Stake returned @ 1.00x odds).`
              : `StatIQ Brain Audit: StatIQ predicted [${matchIQPick.pick}]. Actual final score: ${f.home_team} ${f.home_score} - ${f.away_score} ${f.away_team} → ${isWin ? "STATIQ PICK WON" : "STATIQ PICK LOST"}. (Original Code Pick: ${f.originalPick}).`
          };
        });
      } else {
        selectionsToAudit = rawPickList.map((item, idx) => {
          const leg = item.leg;
          const hScore = leg.actualHome;
          const aScore = leg.actualAway;
          const realStats = realStatsMap[String(idx)] || null;
          const evalRes = evaluatePickResult(leg.prediction, hScore, aScore, leg.home, leg.away, realStats);
          const isUnverified = evalRes === "UNVERIFIED";
          const isVoid = evalRes === "VOID";
          const isWin = isUnverified ? false : isVoid ? true : evalRes;
          return {
            id: leg.id,
            leagueName: leg.leagueName,
            home: leg.home,
            away: leg.away,
            prediction: leg.prediction,
            originalPick: leg.originalPick,
            odds: isVoid ? 1.00 : leg.odds,
            origOdds: leg.odds,
            prob: leg.prob,
            actualHome: hScore,
            actualAway: aScore,
            isWin,
            isVoid,
            isUnverified,
            realStats,
            reason: isUnverified
              ? `StatIQ Brain Audit: StatIQ predicted [${leg.prediction}]. Score: ${leg.home} ${hScore} - ${aScore} ${leg.away}. ⚠️ UNVERIFIED — requires corners/halftime stats.`
              : isVoid
              ? `StatIQ Brain Audit: StatIQ predicted [${leg.prediction}]. Actual final score: ${leg.home} ${hScore} - ${aScore} ${leg.away} → 🔄 VOID / PUSH (Stake returned @ 1.00x odds).`
              : `StatIQ Brain Audit: StatIQ predicted [${leg.prediction}]. Actual final score: ${leg.home} ${hScore} - ${aScore} ${leg.away} → ${isWin ? "STATIQ PICK WON" : "STATIQ PICK LOST"}. (Original Code Pick: ${leg.originalPick || "N/A"}).`
          };
        });
      }

      // Win rate = verified picks only (exclude UNVERIFIED from denominator)
      const verifiedSelections = selectionsToAudit.filter(m => !m.isUnverified);
      const totalOdds = selectionsToAudit.reduce((acc, m) => acc * m.odds, 1.0);
      const wonCount = verifiedSelections.filter(m => m.isWin).length;
      const verifiedTotal = verifiedSelections.length;
      const unverifiedCount = selectionsToAudit.filter(m => m.isUnverified).length;
      const allWon = wonCount === verifiedTotal && verifiedTotal > 0;

      setAuditRecord({
        mode: "EXPIRED_CODE",
        code: expiredCodeInput.toUpperCase(),
        targetOddsGoal: codeTargetOdds !== "ALL" ? parseFloat(codeTargetOdds) : null,
        matches: selectionsToAudit,
        combinedOdds: totalOdds,
        wonCount,
        totalCount: verifiedTotal,
        unverifiedCount,
        allWon
      });

    } else if (testMode === "GAMEWEEK") {
      // Fetch REAL historical finished matches for selected Season & Gameweek across all leagues if requested
      let historicalMatches = [];
      const leaguesToFetch = league === "ALL" ? ["PL", "PD", "SA", "BL1", "FL1"] : [league];

      for (const lg of leaguesToFetch) {
        try {
          const res = await fetchFixturesByGameweek(lg, gameweek, season);
          if (res.fixtures && res.fixtures.length > 0) {
            historicalMatches = historicalMatches.concat(res.fixtures);
          }
        } catch (e) {}
      }

      // Shuffle fixtures if Multi-League scope is selected
      if (league === "ALL" && historicalMatches.length > 0) {
        historicalMatches = historicalMatches.sort(() => 0.5 - Math.random());
      }

      // Gate 3+4+5: Use shared pick engine — diverse markets, sorted by safety
      let selectionsToAudit = [];
      if (historicalMatches.length > 0) {
        const usedTypeCounts = {};
        selectionsToAudit = historicalMatches.map((f, idx) => {
          const pd = generateSafePick(f, usedTypeCounts, true);
          usedTypeCounts[pd.marketType] = (usedTypeCounts[pd.marketType] || 0) + 1;
          const hasRealScore = f.home_score !== null && f.home_score !== undefined && f.away_score !== null && f.away_score !== undefined;
          if (!hasRealScore) return null; // skip fixtures with no real score
          const hScore = f.home_score;
          const aScore = f.away_score;
          const isWin = evaluatePickResult(pd.pick, hScore, aScore, f.home_team, f.away_team);

          return {
            id: f.fixture_id || idx + 2000,
            leagueName: f.competition_code || "PL",
            home: f.home_team,
            away: f.away_team,
            prediction: pd.pick,
            odds: pd.odds,
            prob: pd.prob,
            tier: pd.tier,
            actualHome: hScore,
            actualAway: aScore,
            isWin: isWin,
            reason: `Season ${season}/${season + 1} GW${gameweek}: ${f.home_team} ${hScore} - ${aScore} ${f.away_team}. [${pd.tier}]`
          };
        }).filter(Boolean);
      }

      if (selectionsToAudit.length === 0) {
        setAuditRecord({
          mode: "GAMEWEEK",
          error: `No finished fixtures found for GW${gameweek} of the ${season}/${season + 1} season${league !== "ALL" ? ` in the selected league` : ""}. Try a different gameweek or league.`,
          matches: [], combinedOdds: 0, wonCount: 0, totalCount: 0, allWon: false
        });
        setTimeout(() => { setUnblinded(true); setAuditing(false); }, 400);
        return;
      }

      const totalOdds = selectionsToAudit.reduce((acc, m) => acc * m.odds, 1.0);
      const wonCount = selectionsToAudit.filter(m => m.isWin).length;

      setAuditRecord({
        mode: "GAMEWEEK",
        season,
        gameweek,
        matches: selectionsToAudit,
        combinedOdds: totalOdds,
        wonCount,
        totalCount: selectionsToAudit.length,
        allWon: wonCount === selectionsToAudit.length
      });
    } else {
      // TARGET ODDS Mode: Fetch REAL finished matches targeting user odds goal with random multi-league selection
      let historicalMatches = [];
      const leaguesToFetch = league === "ALL" ? ["PL", "PD", "SA", "BL1", "FL1"] : [league];

      // Offset matchday search based on target odds so ~2x, ~5x, ~10x, ~20x evaluation pools start from fresh matchday sequences!
      const targetOffset = targetOdds >= 50 ? 5 : targetOdds >= 20 ? 3 : targetOdds >= 10 ? 2 : targetOdds >= 5 ? 1 : 0;
      const isHighOddsTarget = targetOdds >= 10;
      const fixturePoolTarget = isHighOddsTarget ? 40 : 16;
      const searchCount = isHighOddsTarget ? 15 : 6;

      const gameweekTries = [];
      for (let i = 0; i < searchCount; i++) {
        const gwCandidate = ((gameweek - 1 + targetOffset + i) % 38) + 1;
        gameweekTries.push(gwCandidate);
      }

      for (const gwTry of gameweekTries) {
        if (gwTry < 1 || gwTry > 38) continue;
        if (historicalMatches.length >= fixturePoolTarget) break;
        for (const lg of leaguesToFetch) {
          try {
            const res = await fetchFixturesByGameweek(lg, gwTry, season);
            if (res.fixtures && res.fixtures.length > 0) {
              const finishedOnly = res.fixtures.filter(f => f.home_score !== null && f.home_score !== undefined);
              const toAdd = finishedOnly.length > 0 ? finishedOnly : res.fixtures;
              // Deduplicate by fixture_id
              const existingIds = new Set(historicalMatches.map(m => m.fixture_id));
              historicalMatches = historicalMatches.concat(toAdd.filter(f => !existingIds.has(f.fixture_id)));
            }
          } catch (e) {}
        }
      }

      // Rotate pool deterministically based on target odds seed so each target odds tier evaluates fresh candidate matches
      const targetSeed = Math.round(targetOdds * 100);
      if (historicalMatches.length > 0) {
        historicalMatches = historicalMatches.sort((a, b) => {
          const hA = fixtureSeed(a.home_team || a.home || "", a.away_team || a.away || "") ^ targetSeed;
          const hB = fixtureSeed(b.home_team || b.home || "", b.away_team || b.away || "") ^ targetSeed;
          return (hA % 1000) - (hB % 1000);
        });
      }

      // Gate 3+4+5: buildSafeTicket handles scoring, diversity, and sorted accumulation
      const maxLegsForTarget = targetOdds >= 50 ? 20 : targetOdds >= 20 ? 16 : targetOdds >= 10 ? 12 : 10;
      let selectionsToAudit = [];
      if (historicalMatches.length >= 2) {
        const { legs } = buildSafeTicket(historicalMatches, targetOdds, { maxLegs: maxLegsForTarget, isBacktest: true });
        selectionsToAudit = legs
          .filter(leg => leg.actualHome !== null && leg.actualHome !== undefined &&
                         leg.actualAway !== null && leg.actualAway !== undefined)
          .map((leg) => {
            const hScore = leg.actualHome;
            const aScore = leg.actualAway;
            const isWin = evaluatePickResult(leg.prediction, hScore, aScore, leg.home, leg.away);
            return {
              id: leg.id,
              leagueName: leg.leagueName,
              home: leg.home,
              away: leg.away,
              prediction: leg.prediction,
              odds: leg.odds,
              prob: leg.prob,
              tier: leg.tier,
              actualHome: hScore,
              actualAway: aScore,
              isWin: isWin,
              reason: `Season ${season}/${season + 1} backtest: ${leg.home} ${hScore} - ${aScore} ${leg.away}. [${leg.tier}]`
            };
          });
      }

      if (selectionsToAudit.length === 0) {
        setAuditRecord({
          mode: "ODDS",
          error: `No finished fixtures found for the ${season}/${season + 1} season${league !== "ALL" ? ` in the selected league` : ""}. Try a different season, gameweek, or league scope.`,
          matches: [], combinedOdds: 0, wonCount: 0, totalCount: 0, allWon: false
        });
        setTimeout(() => { setUnblinded(true); setAuditing(false); }, 400);
        return;
      }

      const totalOdds = selectionsToAudit.reduce((acc, m) => acc * m.odds, 1.0);
      const wonCount = selectionsToAudit.filter(m => m.isWin).length;

      // Detect odds shortfall — when achieved odds is < 60% of target
      const oddsShortfall = targetOdds > 5 && totalOdds < targetOdds * 0.60
        ? { target: targetOdds, achieved: totalOdds, legs: selectionsToAudit.length, scope: league }
        : null;

      setAuditRecord({
        mode: "ODDS",
        season,
        gameweek,
        targetOddsGoal: targetOdds,
        matches: selectionsToAudit,
        combinedOdds: totalOdds,
        wonCount,
        totalCount: selectionsToAudit.length,
        allWon: wonCount === selectionsToAudit.length,
        oddsShortfall
      });
    }

    setTimeout(() => {
      setUnblinded(true);
      setAuditing(false);
    }, 600);
  };

  // Confirm delete handler called from modal
  const confirmDeleteAudit = () => {
    setUnblinded(false);
    setAuditRecord(null);
    setShowDeleteModal(false);
  };

  const handleModeSwitch = (newMode) => {
    setTestMode(newMode);
    setUnblinded(false);
    setAuditRecord(null);
  };

  return (
    <div className="space-y-6 relative">
      {/* Sleek Delete Confirmation Modal Popup */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full border border-slate-200 shadow-2xl space-y-5 relative">
            <button
              onClick={() => setShowDeleteModal(false)}
              className="absolute right-4 top-4 text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 transition-all"
            >
              <X className="w-4 h-4" />
            </button>

            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 flex-shrink-0">
                <Trash2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-extrabold text-slate-900">
                  Delete Backtest Audit Record?
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Are you sure you want to clear this audit session?
                </p>
              </div>
            </div>

            <p className="text-xs text-slate-600 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
              This will clear the current unblinded audit results and reset the simulator back to locked state.
            </p>

            <div className="flex items-center space-x-3 pt-1">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="flex-1 py-2.5 rounded-xl bg-slate-100 text-slate-700 hover:bg-slate-200 text-xs font-extrabold transition-all"
              >
                Cancel
              </button>
              <button
                onClick={confirmDeleteAudit}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-extrabold transition-all shadow-sm"
              >
                Yes, Delete Audit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Title Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900">
            Historical Backtest Simulator & Audit Record
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Backtest StatIQ's prediction logic on <strong>real concluded past seasons (2021 to 2026)</strong> across Target Odds, Expired Booking Codes, or Gameweeks.
          </p>
        </div>

        {/* Delete Audit Button */}
        {unblinded && (
          <button
            onClick={() => setShowDeleteModal(true)}
            className="px-4 py-2.5 rounded-xl bg-rose-600 text-white text-xs font-extrabold hover:bg-rose-700 flex items-center space-x-1.5 self-start sm:self-auto transition-all shadow-sm cursor-pointer"
          >
            <Trash2 className="w-4 h-4" />
            <span>Delete / Clear Audit Record</span>
          </button>
        )}
      </div>

      {/* Control Panel */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-4">
        {/* Mode Switcher */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 pb-4">
          <button
            onClick={() => handleModeSwitch("ODDS")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              testMode === "ODDS"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            🎯 Target Odds Goal (2x to 1000x)
          </button>

          <button
            onClick={() => handleModeSwitch("EXPIRED_CODE")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              testMode === "EXPIRED_CODE"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            📜 Expired Booking Code Audit
          </button>

          <button
            onClick={() => handleModeSwitch("GAMEWEEK")}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              testMode === "GAMEWEEK"
                ? "bg-slate-900 text-white shadow-sm"
                : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            📅 Gameweek Audit
          </button>
        </div>

        {/* MODE 1: TARGET ODDS GOAL FILTERS */}
        {testMode === "ODDS" && (
          <div className="grid grid-cols-1 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-6 gap-3 items-end">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Historical Season
              </label>
              <select
                value={season}
                onChange={(e) => {
                  setSeason(parseInt(e.target.value));
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value={2025}>2025/26 Season (Finished)</option>
                <option value={2024}>2024/25 Season (Finished)</option>
                <option value={2023}>2023/24 Season (Finished)</option>
                <option value={2022}>2022/23 Season (Finished)</option>
                <option value={2021}>2021/22 Season (Finished)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                League Scope
              </label>
              <select
                value={league}
                onChange={(e) => {
                  setLeague(e.target.value);
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="ALL">All Leagues (Multi-League Ticket)</option>
                <option value="PL">Premier League (England)</option>
                <option value="PD">La Liga (Spain)</option>
                <option value="SA">Serie A (Italy)</option>
                <option value="BL1">Bundesliga (Germany)</option>
                <option value="FL1">Ligue 1 (France)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Target Gameweek
              </label>
              <select
                value={gameweek}
                onChange={(e) => {
                  setGameweek(parseInt(e.target.value));
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                {Array.from({ length: 38 }, (_, i) => i + 1).map((gw) => (
                  <option key={gw} value={gw}>Gameweek {gw}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Target Combined Odds
              </label>
              <select
                value={targetOdds}
                onChange={(e) => {
                  setTargetOdds(parseFloat(e.target.value));
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value={2.0}>~2.00 Odds (Safest 2 Legs)</option>
                <option value={3.0}>~3.00 Odds (2-3 Legs)</option>
                <option value={5.0}>~5.00 Odds (4-5 Legs)</option>
                <option value={10.0}>~10.00 Odds (8-9 Legs)</option>
                <option value={20.0}>~20.00 Odds (12-13 Legs)</option>
                <option value={50.0}>~50.00 Odds (16-18 Legs)</option>
                <option value={100.0}>~100.00 Odds (18-20 Legs)</option>
                <option value={500.0}>~500.00 Odds (Multi-League Slip)</option>
                <option value={1000.0}>~1000.00+ Odds (Mega Ticket)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                SportyBet Flex Cut
              </label>
              <select
                value={selectedFlexCut}
                onChange={(e) => setSelectedFlexCut(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="AUTO">✨ Auto (Recommended Cut)</option>
                <option value="OFF">🚫 Flex Off (Straight Acca)</option>
                <option value="1">Flex Cut-1 (1 Loss Allowed)</option>
                <option value="2">Flex Cut-2 (2 Losses Allowed)</option>
                <option value="3">Flex Cut-3 (3 Losses Allowed)</option>
                <option value="4">Flex Cut-4 (4 Losses Allowed)</option>
                <option value="5">Flex Cut-5 (5 Losses Allowed)</option>
                <option value="6">Flex Cut-6 (6 Losses Allowed)</option>
                <option value="7">Flex Cut-7 (7 Losses Allowed)</option>
              </select>
            </div>

            <button
              onClick={handleRunAudit}
              disabled={auditing}
              className="w-full py-2.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {auditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-white" />}
              <span>{auditing ? "Fetching Results..." : unblinded ? "Re-Run Audit" : "Run Backtest Audit"}</span>
            </button>
          </div>
        )}

        {/* MODE 2: EXPIRED BOOKING CODE AUDIT FILTERS */}
        {testMode === "EXPIRED_CODE" && (
          <div className="flex flex-col sm:flex-row items-end gap-3">
            <div className="flex-1">
              <label className="text-xs font-semibold text-slate-700 block mb-1 uppercase tracking-wider">
                Enter Expired / Completed Booking Code
              </label>
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
                <input
                  type="text"
                  value={expiredCodeInput}
                  onChange={(e) => {
                    setExpiredCodeInput(e.target.value);
                    setUnblinded(false);
                  }}
                  placeholder="e.g. BC7F49A or LYTXQL"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-2 text-xs font-bold text-slate-900 uppercase tracking-wider focus:outline-none focus:ring-1 focus:ring-slate-900"
                />
              </div>
            </div>

            <div className="w-full sm:w-56">
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Target Odds Sub-Ticket
              </label>
              <select
                value={codeTargetOdds}
                onChange={(e) => {
                  setCodeTargetOdds(e.target.value);
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="ALL">Audit All Code Picks ({expiredCodeInput || "Code"})</option>
                <option value="2.0">Build ~2.00x Target Ticket from Code</option>
                <option value="3.0">Build ~3.00x Target Ticket from Code</option>
                <option value="5.0">Build ~5.00x Target Ticket from Code</option>
                <option value="10.0">Build ~10.00x Target Ticket from Code</option>
                <option value="20.0">Build ~20.00x Target Ticket from Code</option>
              </select>
            </div>

            <div className="w-full sm:w-52">
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                SportyBet Flex Cut Strategy
              </label>
              <select
                value={selectedFlexCut}
                onChange={(e) => {
                  setSelectedFlexCut(e.target.value);
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="AUTO">🤖 Auto (StatIQ Model Cut)</option>
                <option value="OFF">🚫 Flex Off (Straight Acca)</option>
                <option value="1">Flex Cut-1 (1 Loss Allowed)</option>
                <option value="2">Flex Cut-2 (2 Losses Allowed)</option>
                <option value="3">Flex Cut-3 (3 Losses Allowed)</option>
                <option value="4">Flex Cut-4 (4 Losses Allowed)</option>
                <option value="5">Flex Cut-5 (5 Losses Allowed)</option>
                <option value="6">Flex Cut-6 (6 Losses Allowed)</option>
                <option value="7">Flex Cut-7 (7 Losses Allowed)</option>
              </select>
            </div>

            <button
              onClick={handleRunAudit}
              disabled={auditing}
              className="px-6 py-2.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 whitespace-nowrap w-full sm:w-auto"
            >
              {auditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-white" />}
              <span>{auditing ? "Auditing Code..." : "Load & Audit Code Results"}</span>
            </button>
          </div>
        )}

        {/* MODE 3: GAMEWEEK AUDIT FILTERS */}
        {testMode === "GAMEWEEK" && (
          <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Historical Season
              </label>
              <select
                value={season}
                onChange={(e) => {
                  setSeason(parseInt(e.target.value));
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value={2025}>2025/26 Season (Finished)</option>
                <option value={2024}>2024/25 Season (Finished)</option>
                <option value={2023}>2023/24 Season (Finished)</option>
                <option value={2022}>2022/23 Season (Finished)</option>
                <option value={2021}>2021/22 Season (Finished)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                League Scope
              </label>
              <select
                value={league}
                onChange={(e) => {
                  setLeague(e.target.value);
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="ALL">All Leagues (Multi-League Matchday)</option>
                <option value="PL">Premier League (England)</option>
                <option value="PD">La Liga (Spain)</option>
                <option value="SA">Serie A (Italy)</option>
                <option value="BL1">Bundesliga (Germany)</option>
                <option value="FL1">Ligue 1 (France)</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Target Gameweek
              </label>
              <select
                value={gameweek}
                onChange={(e) => {
                  setGameweek(parseInt(e.target.value));
                  setUnblinded(false);
                }}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                {Array.from({ length: 38 }, (_, i) => i + 1).map((gw) => (
                  <option key={gw} value={gw}>Gameweek {gw}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                SportyBet Flex Cut
              </label>
              <select
                value={selectedFlexCut}
                onChange={(e) => setSelectedFlexCut(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-900 rounded-xl px-3 py-2"
              >
                <option value="AUTO">✨ Auto (Recommended Cut)</option>
                <option value="OFF">🚫 Flex Off (Straight Acca)</option>
                <option value="1">Flex Cut-1 (1 Loss Allowed)</option>
                <option value="2">Flex Cut-2 (2 Losses Allowed)</option>
                <option value="3">Flex Cut-3 (3 Losses Allowed)</option>
                <option value="4">Flex Cut-4 (4 Losses Allowed)</option>
                <option value="5">Flex Cut-5 (5 Losses Allowed)</option>
                <option value="6">Flex Cut-6 (6 Losses Allowed)</option>
                <option value="7">Flex Cut-7 (7 Losses Allowed)</option>
              </select>
            </div>

            <button
              onClick={handleRunAudit}
              disabled={auditing}
              className="w-full py-2.5 rounded-xl btn-black text-xs font-extrabold uppercase tracking-wider flex items-center justify-center space-x-2 disabled:opacity-50"
            >
              {auditing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-white" />}
              <span>{auditing ? "Auditing Gameweek..." : unblinded ? "Re-Run Gameweek Audit" : "Run Gameweek Audit"}</span>
            </button>
          </div>
        )}
      </div>

      {/* Code Not Found / API Error Banner */}
      {unblinded && auditRecord?.error && (
        <div className="p-6 rounded-2xl border border-amber-200 bg-amber-50 flex items-start space-x-4 shadow-sm">
          <div className="w-10 h-10 rounded-xl bg-amber-100 border border-amber-300 flex items-center justify-center flex-shrink-0">
            <AlertCircle className="w-5 h-5 text-amber-600" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-extrabold text-amber-900">Booking Code Not Found</p>
            <p className="text-xs text-amber-700 mt-1">{auditRecord.error}</p>
            <p className="text-xs text-amber-600 mt-2 font-semibold">
              Entered code: <span className="font-mono bg-amber-100 px-1.5 py-0.5 rounded">{auditRecord.code}</span> — please verify the code and try again.
            </p>
          </div>
          <button
            onClick={() => { setUnblinded(false); setAuditRecord(null); }}
            className="text-amber-400 hover:text-amber-600 p-1.5 rounded-full hover:bg-amber-100 transition-all flex-shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Audit Summary Banner */}
      {unblinded && auditRecord && !auditRecord.error && (
        <div className={`p-6 rounded-2xl border flex flex-col sm:flex-row items-center justify-between gap-4 shadow-sm ${
          auditRecord.allWon ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"
        }`}>
          <div className="flex items-center space-x-4">
            <div className={`w-12 h-12 rounded-2xl text-white flex items-center justify-center font-extrabold text-lg shadow-sm ${
              auditRecord.allWon ? "bg-emerald-600" : "bg-rose-600"
            }`}>
              {auditRecord.allWon ? "WON" : "LOST"}
            </div>
            <div>
              <span className={`text-xs font-bold uppercase tracking-wider block ${
                auditRecord.allWon ? "text-emerald-800" : "text-rose-800"
              }`}>
                Historical Backtest Result • {
                  auditRecord.mode === "EXPIRED_CODE"
                    ? `Expired Booking Code [${auditRecord.code}] Audit`
                    : auditRecord.mode === "ODDS"
                    ? `Season ${auditRecord.season}/${auditRecord.season + 1} • GW${auditRecord.gameweek} • Target ~${auditRecord.targetOddsGoal} Odds`
                    : `Season ${auditRecord.season}/${auditRecord.season + 1} • Gameweek ${auditRecord.gameweek}`
                }
              </span>
              <h3 className="text-base font-extrabold text-slate-900">
                MatchIQ Won {auditRecord.wonCount} out of {auditRecord.totalCount} Verified Selections ({auditRecord.totalCount > 0 ? ((auditRecord.wonCount / auditRecord.totalCount) * 100).toFixed(0) : 0}% Win Rate)
                {auditRecord.unverifiedCount > 0 && (
                  <span className="text-xs font-bold text-amber-700 bg-amber-100 border border-amber-300 px-2 py-0.5 rounded-md ml-2">
                    ⚠️ {auditRecord.unverifiedCount} Unverified Leg{auditRecord.unverifiedCount > 1 ? "s" : ""}
                  </span>
                )}
              </h3>
              <span className="text-xs text-slate-600 mt-0.5 block">
                Total Combined Odds: <strong>{auditRecord.combinedOdds.toFixed(2)}x</strong>
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-2 self-start sm:self-auto">
            <button
              onClick={() => setShowDeleteModal(true)}
              className="px-4 py-2 rounded-xl bg-rose-600 text-white text-xs font-extrabold hover:bg-rose-700 flex items-center space-x-1 shadow-sm cursor-pointer"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete Audit</span>
            </button>
            <button
              onClick={() => setUnblinded(false)}
              className="px-3.5 py-2 rounded-xl bg-white border border-slate-300 text-slate-800 text-xs font-bold hover:bg-slate-50 transition-all"
            >
              Lock Results Again
            </button>
          </div>
        </div>
      )}

      {/* 🛡️ SportyBet Flex-Shield Recommendation Card */}
      {unblinded && auditRecord && !auditRecord.error && auditRecord.totalCount >= 2 && (() => {
        const flex = calculateFlexShield(auditRecord.totalCount, auditRecord.wonCount, auditRecord.combinedOdds, selectedFlexCut);
        if (!flex.eligible) return null;
        return (
          <div className={`p-5 rounded-2xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-sm transition-all ${
            flex.isFlexSettledWon
              ? "bg-slate-900 border-emerald-500/40 text-white"
              : "bg-slate-900 border-amber-500/40 text-white"
          }`}>
            <div className="flex items-start space-x-3.5">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 ${
                flex.isFlexSettledWon ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
              }`}>
                {flex.isFlexSettledWon ? <ShieldCheck className="w-5 h-5" /> : <ShieldAlert className="w-5 h-5" />}
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2 mt-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="text-[11px] font-bold text-slate-300">
                      Flex Cut Setting:
                    </span>
                    <select
                      value={selectedFlexCut}
                      onChange={(e) => setSelectedFlexCut(e.target.value)}
                      className="bg-slate-800 border border-slate-700 text-emerald-400 text-xs font-extrabold rounded-xl px-3 py-1 focus:outline-none focus:border-emerald-500 cursor-pointer"
                    >
                      <option value="AUTO">✨ Auto-Recommend (Cut-{flex.recommendedCut})</option>
                      <option value="OFF">🚫 Flex Off (No Flex Protection)</option>
                      {Array.from({ length: Math.min(7, flex.maxAllowedCut || 7) }, (_, i) => i + 1).map((c) => (
                        <option key={c} value={String(c)}>
                          Cut-{c} (Covers up to {c} failing leg{c > 1 ? "s" : ""})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <h4 className="text-sm font-extrabold text-white mt-2">
                  {flex.statusText}
                </h4>
                <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                  {flex.description}
                </p>
              </div>
            </div>

            <div className="flex flex-col items-end flex-shrink-0 self-stretch sm:self-auto justify-center bg-slate-800/80 border border-slate-700/60 p-3 rounded-xl min-w-[140px]">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Flex Coverage</span>
              <span className="text-sm font-black text-emerald-400 mt-0.5">
                Up to {flex.recommendedCut} Losses Paid
              </span>
              <span className="text-[10px] text-slate-400 mt-0.5">
                Actual Losses: {flex.lossCount}
              </span>
            </div>
          </div>
        );
      })()}

      {/* ⚠️ Odds Shortfall Warning Banner */}
      {unblinded && auditRecord?.oddsShortfall && (
        <div className="p-4 rounded-2xl border border-amber-300 bg-amber-50 flex items-start space-x-3 shadow-sm">
          <div className="w-8 h-8 rounded-xl bg-amber-500 flex items-center justify-center flex-shrink-0 mt-0.5">
            <AlertCircle className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-extrabold text-amber-900 uppercase tracking-wider">
              ⚠️ Odds Target Not Fully Reached — Safe Picks Mathematical Ceiling
            </p>
            <p className="text-xs text-amber-800 mt-1 leading-relaxed">
              Target was <strong>~{auditRecord.oddsShortfall.target}x</strong> combined odds but MatchIQ only
              reached <strong>{auditRecord.oddsShortfall.achieved.toFixed(2)}x</strong> using{" "}
              <strong>{auditRecord.oddsShortfall.legs} safe legs</strong>
              {auditRecord.oddsShortfall.scope !== "ALL" && (
                <> with a <strong>single-league scope ({auditRecord.oddsShortfall.scope})</strong></>
              )}.
            </p>
            <p className="text-[11px] text-amber-700 mt-1.5 leading-relaxed">
              <strong>Why:</strong> MatchIQ's 5-Gate engine only issues safe markets (1.15x–1.35x per leg). At 20 legs max,
              the highest achievable combined odds is approximately <strong>~12x–18x</strong> while maintaining a
              {">"}80% win rate. Targets above <strong>~20x</strong> require individual leg odds of 1.50x+ which
              carry significantly higher loss risk and fall outside the safe zone.
            </p>
            <div className="flex flex-wrap gap-2 mt-2">
              {auditRecord.oddsShortfall.scope !== "ALL" && (
                <span className="text-[10px] font-bold text-amber-800 bg-amber-100 border border-amber-200 px-2 py-1 rounded-lg">
                  💡 Switch to All Leagues for more fixtures
                </span>
              )}
              <span className="text-[10px] font-bold text-amber-800 bg-amber-100 border border-amber-200 px-2 py-1 rounded-lg">
                💡 For 50x+ odds, use Target Odds ~10x–20x and reinvest winnings (rollover strategy)
              </span>
              <span className="text-[10px] font-bold text-amber-800 bg-amber-100 border border-amber-200 px-2 py-1 rounded-lg">
                💡 The {auditRecord.oddsShortfall.legs} picks shown are still the highest-confidence selections available
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Matches Cards List */}

      <div className="space-y-3">
        <div className="flex items-center justify-between px-1 text-xs text-slate-500 font-semibold">
          <span>
            {testMode === "EXPIRED_CODE"
              ? `Expired Code [${expiredCodeInput.toUpperCase()}] Selections`
              : testMode === "ODDS"
              ? `Season ${season}/${season + 1} Gameweek ${gameweek} Finished Matches (~${targetOdds} Total Odds)`
              : `Season ${season}/${season + 1} Gameweek ${gameweek} Finished Matches`}
          </span>
          <span>{unblinded ? "Actual Finished Score vs Pre-Kickoff AI Prediction" : "Locked AI Predictions (Pre-Kickoff)"}</span>
        </div>

        {auditRecord && auditRecord.matches?.map((m, idx) => (
          <div
            key={m.id || idx}
            className={`bg-white p-4 rounded-xl border ${
              unblinded
                ? m.isUnverified
                  ? "border-amber-300 bg-amber-50/30"
                  : m.isWin
                  ? "border-emerald-200 bg-emerald-50/20"
                  : "border-rose-200 bg-rose-50/20"
                : "border-slate-200"
            } space-y-3 text-xs shadow-sm`}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex-1">
                <div className="flex items-center space-x-2 mb-1">
                  <span className="text-[10px] font-extrabold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                    {m.leagueName}
                  </span>
                  <span className="text-[10px] text-slate-400 font-medium">Odds: {m.odds ? m.odds.toFixed(2) : "1.75"}</span>
                </div>
                <span className="text-sm font-extrabold text-slate-900">
                  {m.home} vs {m.away}
                </span>
              </div>

              <div className="bg-slate-50 px-4 py-2 rounded-xl border border-slate-200 text-center min-w-44">
                <span className="text-[10px] text-slate-400 block font-medium">
                  Locked AI Prediction
                </span>
                <span className="font-extrabold text-slate-900">
                  {m.prediction}
                </span>
                <span className="text-[10px] font-bold text-indigo-600 block">
                  {m.prob}% AI Win Chance
                </span>
                {m.originalPick && (
                  <span className="text-[9px] text-slate-500 font-medium block mt-0.5 border-t border-slate-200/60 pt-0.5">
                    Original Slip Pick: {m.originalPick}
                  </span>
                )}
              </div>

              <div className="min-w-44 text-right">
                {unblinded ? (
                  <div className="flex items-center justify-end space-x-3">
                    <div>
                      <span className="text-[10px] text-slate-400 block font-medium">
                        Actual Score
                      </span>
                      <span className="text-sm font-extrabold text-slate-900">
                        {m.actualHome} - {m.actualAway}
                      </span>
                    </div>

                    {m.isUnverified ? (
                      <span className="bg-amber-100 text-amber-800 border border-amber-300 px-2.5 py-1 rounded-lg font-extrabold flex items-center space-x-1">
                        <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
                        <span>UNVERIFIED</span>
                      </span>
                    ) : m.isVoid ? (
                      <span className="bg-slate-100 text-slate-700 border border-slate-300 px-2.5 py-1 rounded-lg font-extrabold flex items-center space-x-1">
                        <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
                        <span>VOID (1.00x)</span>
                      </span>
                    ) : m.isWin ? (
                      <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 px-2.5 py-1 rounded-lg font-extrabold flex items-center space-x-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>WIN</span>
                      </span>
                    ) : (
                      <span className="bg-rose-100 text-rose-800 border border-rose-300 px-2.5 py-1 rounded-lg font-extrabold flex items-center space-x-1">
                        <XCircle className="w-3.5 h-3.5 text-rose-600" />
                        <span>LOSS</span>
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center justify-end space-x-1 text-slate-400 py-1">
                    <Lock className="w-4 h-4 text-slate-400" />
                    <span className="font-semibold text-xs">Result Locked</span>
                  </div>
                )}
              </div>
            </div>

            {unblinded && (
              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200 text-[11px] text-slate-600">
                <strong>AI Brain Performance Analysis:</strong> {m.reason}
                {m.realStats && m.realStats.found && (
                  <span className="block mt-1 text-[10px] text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">
                    ⚡ Verified via API-Football: {m.realStats.ht_home !== null ? `HT Score: ${m.realStats.ht_home}-${m.realStats.ht_away} | ` : ""}{m.realStats.home_corners !== null ? `Total Corners: ${m.realStats.home_corners + m.realStats.away_corners} (${m.realStats.home_corners} - ${m.realStats.away_corners})` : ""}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

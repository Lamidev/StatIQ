/**
 * Ticket Live Evaluator & SportyBet Status Utils
 * Handles live sticker classification, early-win pick evaluation,
 * robust scoreline parsing, and dynamic live match time clocking.
 */

/**
 * Parses home and away scores robustly from any selection format.
 * Handles "0:2", "0 - 2", "2:2", separate home_score/away_score, etc.
 */
export function parseScore(sel) {
  if (!sel) return { home: null, away: null, scoreStr: "--", htHome: null, htAway: null };

  let h = sel.home_score;
  let a = sel.away_score;
  let htH = sel.ht_home !== undefined ? sel.ht_home : null;
  let htA = sel.ht_away !== undefined ? sel.ht_away : null;

  // Check setScores / period scores like [{"home":2,"away":1}, {"home":1,"away":2}] or "(2-1, 1-2)"
  if (sel.setScores && Array.isArray(sel.setScores) && sel.setScores.length >= 1) {
    htH = Number(sel.setScores[0]?.home ?? htH);
    htA = Number(sel.setScores[0]?.away ?? htA);
  }

  if (h !== undefined && h !== null && !isNaN(Number(h)) && a !== undefined && a !== null && !isNaN(Number(a))) {
    return { home: Number(h), away: Number(a), scoreStr: `${h} - ${a}`, htHome: htH, htAway: htA };
  }

  const rawScore = sel.score || sel.setScore || sel.fullScore || "";
  if (rawScore && typeof rawScore === "string") {
    // Check period brackets e.g. "3-3 (2-1, 1-2)" or "3:3 (2:1)"
    const periodMatch = rawScore.match(/\((\d+)[\:\-v\s](\d+)/);
    if (periodMatch) {
      htH = parseInt(periodMatch[1], 10);
      htA = parseInt(periodMatch[2], 10);
    }

    // Regex matches any two numbers separated by :, -, v, or spaces
    const match = rawScore.match(/(\d+)\s*[:\-v\s]\s*(\d+)/i);
    if (match) {
      h = parseInt(match[1], 10);
      a = parseInt(match[2], 10);
      return { home: h, away: a, scoreStr: `${h} - ${a}`, htHome: htH, htAway: htA };
    }
  }

  return { home: null, away: null, scoreStr: "--", htHome: htH, htAway: htA };
}

function resolveKickoffMs(sel) {
  if (!sel) return null;

  // 1. Explicit start_time_ms or timestamp numbers
  const numCandidate = sel.start_time_ms || sel.kickoff_ms || sel.timestamp || sel.start_time_unix;
  if (numCandidate && !isNaN(numCandidate)) {
    const n = Number(numCandidate);
    if (n > 1e11) return n;
    if (n > 1e8) return n * 1000;
  }

  // 2. ISO or standard date strings
  const dateCandidates = [
    sel.kickoff_datetime,
    sel.kickoff_time,
    sel.match_date,
    sel.utc_date,
    sel.date,
    sel.start_time,
    sel.kickoff
  ];

  for (const raw of dateCandidates) {
    if (!raw || typeof raw !== "string") continue;
    const str = raw.trim();
    if (!str || str === "--") continue;

    // Direct JS Date parse
    const parsed = new Date(str).getTime();
    if (!isNaN(parsed) && parsed > 1e11) return parsed;

    // Format: "MM/DD HH:MM AM/PM" or "MM/DD HH:MM" (e.g. "08/15 05:00 PM", "08/15 20:30")
    const m1 = str.match(/(\d{1,2})[\/\-](\d{1,2})\s+(\d{1,2}):(\d{2})(?:\s*([APap][Mm]))?/);
    if (m1) {
      const currentYear = new Date().getFullYear();
      let month = parseInt(m1[1], 10) - 1;
      let day = parseInt(m1[2], 10);
      let hour = parseInt(m1[3], 10);
      let min = parseInt(m1[4], 10);
      const meridiem = m1[5] ? m1[5].toUpperCase() : null;

      if (meridiem === "PM" && hour < 12) hour += 12;
      if (meridiem === "AM" && hour === 12) hour = 0;

      const d = new Date(currentYear, month, day, hour, min, 0);
      if (!isNaN(d.getTime())) return d.getTime();
    }
  }

  return null;
}

/**
 * Calculates dynamic match time, period, and status based on kickoff timestamp and score.
 */
export function getDynamicMatchInfo(sel) {
  if (!sel) {
    return { isLive: false, isConcluded: false, isInterrupted: false, matchStatus: "NOT_STARTED", matchTime: null };
  }

  const st = (sel.match_status || "").toUpperCase();

  // If match was interrupted, abandoned, cancelled, or postponed
  if (st.includes("INTERRUPT") || st.includes("ABANDON") || st.includes("CANCEL") || st.includes("POSTPONE") || st.includes("SUSPEND") || st.includes("WEATHER")) {
    return {
      isLive: false,
      isConcluded: true,
      isInterrupted: true,
      matchStatus: "INTERRUPTED",
      matchTime: "Int.",
    };
  }

  // If explicitly concluded or finished
  if (st === "CONCLUDED" || st === "FINISHED" || st === "FT" || st === "ENDED") {
    return {
      isLive: false,
      isConcluded: true,
      isInterrupted: false,
      matchStatus: "CONCLUDED",
      matchTime: "FT",
    };
  }

  // Parse kickoff timestamp with team schedule fallback
  const kickoffMs = resolveKickoffMs(sel);

  // If kickoff time is available, evaluate true in-play state based on wall-clock time
  if (kickoffMs && !isNaN(kickoffMs)) {
    const elapsedMins = Math.floor((Date.now() - kickoffMs) / 60000);

    if (elapsedMins < 0) {
      // Future match that hasn't kicked off yet
      return {
        isLive: false,
        isConcluded: false,
        matchStatus: "NOT_STARTED",
        matchTime: null,
      };
    } else if (elapsedMins <= 45) {
      const mins = Math.max(1, elapsedMins);
      return {
        isLive: true,
        isConcluded: false,
        matchStatus: "LIVE",
        matchTime: `${mins}' H1`,
      };
    } else if (elapsedMins <= 60) {
      return {
        isLive: true,
        isConcluded: false,
        matchStatus: "LIVE",
        matchTime: "HT",
      };
    } else if (elapsedMins <= 105) {
      const mins = Math.min(90, 45 + (elapsedMins - 60));
      return {
        isLive: true,
        isConcluded: false,
        matchStatus: "LIVE",
        matchTime: `${mins}' H2`,
      };
    } else {
      return {
        isLive: false,
        isConcluded: true,
        matchStatus: "CONCLUDED",
        matchTime: "FT",
      };
    }
  }

  // If explicit match_time is provided by live API (e.g. "25' H1", "HT", "70' H2")
  if (sel.match_time && sel.match_time !== "--" && (st === "LIVE" || st === "IN_PLAY" || st === "ONGOING")) {
    return {
      isLive: true,
      isConcluded: false,
      matchStatus: "LIVE",
      matchTime: sel.match_time,
    };
  }

  // Fallback based on status string
  const isLive = st === "LIVE" || st === "ONGOING" || st === "IN_PLAY" || sel.is_live === true;
  return {
    isLive,
    isConcluded: false,
    matchStatus: isLive ? "LIVE" : "NOT_STARTED",
    matchTime: isLive ? (sel.match_time || "In Progress") : null,
  };
}

/**
 * Checks whether a selection/leg is currently live/ongoing.
 */
export function isLegLive(sel) {
  if (!sel) return false;
  const info = getDynamicMatchInfo(sel);
  return info.isLive;
}

/**
 * Checks whether a ticket has any active live games.
 */
export function isTicketLive(ticket) {
  if (!ticket) return false;
  const status = (ticket.status || "RUNNING").toUpperCase();
  if (status === "WON" || status === "LOST") return false;

  const selections = ticket.selections || [];
  return selections.some((s) => isLegLive(s));
}

/**
 * Evaluates a pick given home_score, away_score, and match state.
 * Supports early-win detection for ongoing/live matches (e.g., Over 1.5 when score reaches 0-2 at 38' H1).
 * Returns: { status: "WON" | "LOST" | "PENDING" | "VOID", resultText: string }
 */
export function evaluatePickLive(sel) {
  if (!sel) return { status: "PENDING", resultText: "--" };

  // Prioritize backend settled leg status if already evaluated as WON, LOST, or VOID
  if (sel.leg_status === "WON" || sel.leg_status === "LOST" || sel.leg_status === "VOID" || sel.leg_result === "WON" || sel.leg_result === "LOST" || sel.leg_result === "VOID") {
    const st = sel.leg_status || sel.leg_result;
    const pickName = String(sel.selection_name || sel.selection || sel.original_pick || "").trim();
    return {
      status: st,
      resultText: st === "WON" ? (pickName || "Won") : st === "LOST" ? "Lost" : "Void",
    };
  }

  const matchInfo = getDynamicMatchInfo(sel);
  const isConcluded = matchInfo.isConcluded;

  // Parse scores robustly
  const scoreObj = parseScore(sel);
  const homeScore = scoreObj.home;
  const awayScore = scoreObj.away;

  // If score is missing or unparseable
  if (homeScore === null || awayScore === null) {
    if (sel.leg_status === "WON" || sel.leg_result === "WON") {
      return { status: "WON", resultText: sel.selection_name || "Won" };
    }
    if (sel.leg_status === "LOST" || sel.leg_result === "LOST") {
      return { status: "LOST", resultText: "Lost" };
    }
    if (sel.leg_status === "VOID" || sel.leg_result === "VOID") {
      return { status: "VOID", resultText: "Void" };
    }
    // Unverified score: strictly return PENDING with "--" until score is fetched
    return { status: "PENDING", resultText: "--" };
  }

  const totalGoals = homeScore + awayScore;
  const pickName = String(sel.selection_name || sel.selection || sel.original_pick || "").trim();
  const marketName = String(sel.market_name || sel.market || "").trim();
  const fullText = `${marketName} ${pickName}`.toLowerCase();
  const pickLower = pickName.toLowerCase();
  const ht = (sel.home_team || "").toLowerCase();
  const at = (sel.away_team || "").toLowerCase();

  // 0. TEAM GOALS / TEAM SPECIFIC OVER-UNDER MARKETS (e.g. Fatih Karagumruk Istanbul Over/Under, Home Over 0.5, Team Goals)
  const isTeamGoalsMarket = (() => {
    if (fullText.includes("team goals") || fullText.includes("team over") || fullText.includes("team under")) return true;
    if (fullText.includes("home over") || fullText.includes("home under") || fullText.includes("away over") || fullText.includes("away under")) return true;
    if (fullText.includes("home team over") || fullText.includes("away team over") || fullText.includes("home team under") || fullText.includes("away team under")) return true;
    const mktLower = marketName.toLowerCase();
    if ((ht && mktLower.includes(ht)) || (at && mktLower.includes(at))) {
      if (mktLower.includes("over/under") || mktLower.includes("over") || mktLower.includes("under") || mktLower.includes("goals")) {
        return true;
      }
    }
    return false;
  })();

  if (isTeamGoalsMarket) {
    const isAway = fullText.includes("away") || (at && fullText.includes(at));
    const targetScore = isAway ? awayScore : homeScore;

    const overM = fullText.match(/over\s*(\d+\.?\d*)/i);
    const underM = fullText.match(/under\s*(\d+\.?\d*)/i);

    if (overM) {
      const line = parseFloat(overM[1]);
      if (targetScore > line) {
        return { status: "WON", resultText: pickName || `Over ${line}` };
      }
      if (isConcluded) {
        return { status: "LOST", resultText: `${targetScore} Goals` };
      }
      return { status: "PENDING", resultText: "--" };
    }

    if (underM) {
      const line = parseFloat(underM[1]);
      if (targetScore > line) {
        return { status: "LOST", resultText: `${targetScore} Goals (Exceeded ${line})` };
      }
      if (isConcluded) {
        return { status: "WON", resultText: pickName || `Under ${line}` };
      }
      return { status: "PENDING", resultText: "--" };
    }
  }

  // 0.5 CORNERS MARKETS (Total Corners, Home Corners, Away Corners)
  if (fullText.includes("corner")) {
    const isHome = fullText.includes("home") || (ht && pickLower.includes(ht));
    const isAway = fullText.includes("away") || (at && pickLower.includes(at));

    let cornerVal = null;
    if (isHome && sel.home_corners !== undefined && sel.home_corners !== null) {
      cornerVal = Number(sel.home_corners);
    } else if (isAway && sel.away_corners !== undefined && sel.away_corners !== null) {
      cornerVal = Number(sel.away_corners);
    } else if (sel.total_corners !== undefined && sel.total_corners !== null) {
      cornerVal = Number(sel.total_corners);
    } else if (sel.corners !== undefined && sel.corners !== null) {
      cornerVal = Number(sel.corners);
    } else if (sel.home_corners !== undefined && sel.away_corners !== undefined && sel.home_corners !== null && sel.away_corners !== null) {
      cornerVal = Number(sel.home_corners) + Number(sel.away_corners);
    }

    const overM = fullText.match(/over\s*(\d+\.?\d*)/i);
    const underM = fullText.match(/under\s*(\d+\.?\d*)/i);

    if (overM) {
      const line = parseFloat(overM[1]);
      if (cornerVal !== null && cornerVal > line) {
        return { status: "WON", resultText: pickName || `Over ${line} Corners` };
      }
      if (isConcluded) {
        if (cornerVal !== null) {
          return cornerVal > line
            ? { status: "WON", resultText: pickName || `Over ${line} Corners` }
            : { status: "LOST", resultText: `${cornerVal} Corners` };
        }
        if (sel.leg_status === "WON" || sel.leg_result === "WON") return { status: "WON", resultText: pickName || "Won" };
        if (sel.leg_status === "LOST" || sel.leg_result === "LOST") return { status: "LOST", resultText: "Lost" };
        return { status: "LOST", resultText: "Lost" };
      }
      return { status: "PENDING", resultText: "--" };
    }

    if (underM) {
      const line = parseFloat(underM[1]);
      if (cornerVal !== null && cornerVal > line) {
        return { status: "LOST", resultText: `${cornerVal} Corners (Exceeded ${line})` };
      }
      if (isConcluded) {
        if (cornerVal !== null) {
          return cornerVal <= line
            ? { status: "WON", resultText: pickName || `Under ${line} Corners` }
            : { status: "LOST", resultText: `${cornerVal} Corners` };
        }
        if (sel.leg_status === "WON" || sel.leg_result === "WON") return { status: "WON", resultText: pickName || "Won" };
        if (sel.leg_status === "LOST" || sel.leg_result === "LOST") return { status: "LOST", resultText: "Lost" };
      }
      return { status: "PENDING", resultText: "--" };
    }
  }

  // 1. OVER GOALS (Over 0.5, Over 1.5, Over 2.5, Over 3.5, Over 4.5, etc.)
  const overMatch = fullText.match(/over\s*(\d+\.?\d*)/i) || pickLower.match(/over\s*(\d+\.?\d*)/i);
  if (overMatch) {
    const line = parseFloat(overMatch[1]);
    const isCorner = fullText.includes("corner");
    const val = isCorner && sel.total_corners !== undefined ? sel.total_corners : totalGoals;

    if (val > line) {
      // Early win! Total goals or corners already passed the threshold
      return { status: "WON", resultText: pickName || `Over ${line}` };
    }
    if (isConcluded) {
      return val > line
        ? { status: "WON", resultText: pickName || `Over ${line}` }
        : { status: "LOST", resultText: `Under ${line + 0.5}` };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 2. UNDER GOALS (Under 0.5, Under 1.5, Under 2.5, Under 3.5, etc.)
  const underMatch = fullText.match(/under\s*(\d+\.?\d*)/i) || pickLower.match(/under\s*(\d+\.?\d*)/i);
  if (underMatch) {
    const line = parseFloat(underMatch[1]);
    const isCorner = fullText.includes("corner");
    const val = isCorner && sel.total_corners !== undefined ? sel.total_corners : totalGoals;

    if (val > line) {
      // Early loss! Already exceeded under line while match is ongoing
      return { status: "LOST", resultText: `Over ${line}` };
    }
    if (isConcluded) {
      return val <= line
        ? { status: "WON", resultText: pickName || `Under ${line}` }
        : { status: "LOST", resultText: `Over ${line}` };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 3. BOTH TEAMS TO SCORE (GG / NG)
  if (fullText.includes("both teams to score") || fullText.includes("gg/ng") || pickLower === "gg" || pickLower === "yes" || pickLower === "no") {
    const isNo = fullText.includes("no") || pickLower === "ng" || pickLower === "no";
    if (isNo) {
      if (homeScore >= 1 && awayScore >= 1) {
        return { status: "LOST", resultText: "No (Failed - Both Scored)" };
      }
      if (isConcluded) {
        return (homeScore === 0 || awayScore === 0)
          ? { status: "WON", resultText: "No" }
          : { status: "LOST", resultText: "Yes" };
      }
      return { status: "PENDING", resultText: "--" };
    } else {
      // BTTS Yes
      if (homeScore >= 1 && awayScore >= 1) {
        return { status: "WON", resultText: "Yes" };
      }
      if (isConcluded) {
        return (homeScore >= 1 && awayScore >= 1)
          ? { status: "WON", resultText: "Yes" }
          : { status: "LOST", resultText: "No" };
      }
      return { status: "PENDING", resultText: "--" };
    }
  }

  // 4. COMBO MARKETS: Double Chance & Over/Under and 1X2 & Over/Under
  const isDcCombo = (fullText.includes("double chance") || fullText.includes("dc") || fullText.includes("home/draw") || fullText.includes("draw/away") || fullText.includes("away/draw") || fullText.includes("home/away") || fullText.includes("(1x)") || fullText.includes("(x2)") || fullText.includes("(12)") || fullText.includes("1x &") || fullText.includes("x2 &") || fullText.includes("12 &") || fullText.includes("draw or away") || fullText.includes("home or draw")) && (fullText.includes("over") || fullText.includes("under"));
  const is1x2Combo = (fullText.includes("1x2") || fullText.includes("match result") || fullText.includes("home &") || fullText.includes("away &") || fullText.includes("draw &")) && (fullText.includes("& over") || fullText.includes("& under"));

  if ((isDcCombo || is1x2Combo) && !fullText.includes("both halve")) {
    let dcSatisfied = false;
    if (fullText.includes("x2") || fullText.includes("draw/away") || fullText.includes("away/draw") || fullText.includes("draw or away") || fullText.includes("away or draw") || fullText.includes("2 or draw")) {
      dcSatisfied = awayScore >= homeScore;
    } else if (fullText.includes("1x") || fullText.includes("home/draw") || fullText.includes("draw/home") || fullText.includes("home or draw") || fullText.includes("draw or home") || fullText.includes("1 or draw")) {
      dcSatisfied = homeScore >= awayScore;
    } else if (fullText.includes("12") || fullText.includes("home/away") || fullText.includes("away/home") || fullText.includes("home or away") || fullText.includes("1 or 2")) {
      dcSatisfied = homeScore !== awayScore;
    } else if (fullText.includes("away") || fullText.includes(" 2 ") || fullText.includes("(2)")) {
      dcSatisfied = awayScore > homeScore;
    } else if (fullText.includes("draw") || fullText.includes(" x ") || fullText.includes("(x)")) {
      dcSatisfied = homeScore === awayScore;
    } else if (fullText.includes("home") || fullText.includes(" 1 ") || fullText.includes("(1)")) {
      dcSatisfied = homeScore > awayScore;
    } else {
      dcSatisfied = homeScore >= awayScore;
    }

    const selUnderM = pickLower.match(/under\s*(\d+\.?\d*)/);
    const selOverM = pickLower.match(/over\s*(\d+\.?\d*)/);
    const combUnderM = fullText.match(/under\s*(\d+\.?\d*)/);
    const combOverM = fullText.match(/over\s*(\d+\.?\d*)/);

    let goalsSatisfied = false;
    let line = 1.5;
    let isUnder = false;

    if (selUnderM) {
      line = parseFloat(selUnderM[1]);
      isUnder = true;
      goalsSatisfied = totalGoals < line;
    } else if (selOverM) {
      line = parseFloat(selOverM[1]);
      goalsSatisfied = totalGoals > line;
    } else if (pickLower.includes("under") && combUnderM) {
      line = parseFloat(combUnderM[1]);
      isUnder = true;
      goalsSatisfied = totalGoals < line;
    } else if (combOverM) {
      line = parseFloat(combOverM[1]);
      goalsSatisfied = totalGoals > line;
    } else if (combUnderM) {
      line = parseFloat(combUnderM[1]);
      isUnder = true;
      goalsSatisfied = totalGoals < line;
    } else {
      goalsSatisfied = totalGoals > 1.5;
    }

    if (isConcluded) {
      return (dcSatisfied && goalsSatisfied)
        ? { status: "WON", resultText: pickName || "Won" }
        : { status: "LOST", resultText: "Lost" };
    }

    if (isUnder && totalGoals >= line) {
      return { status: "LOST", resultText: `Over ${line}` };
    }

    return { status: "PENDING", resultText: "--" };
  }

  // 4A. SPORTYBET COMPOUND OR MARKETS (e.g. Home Team or Over 2.5, Udinese Win or Over 2.5 Goals)
  if ((fullText.includes("or over") || fullText.includes("win or over") || fullText.includes("team or over")) && !isDcCombo) {
    const mOver = fullText.match(/over\s*(\d+\.?\d*)/);
    const line = mOver ? parseFloat(mOver[1]) : 2.5;
    if (totalGoals > line) {
      return { status: "WON", resultText: pickName === "Yes" || pickName === "No" ? "Yes" : (pickName || "Yes") };
    }
    if (isConcluded) {
      const isHomeTarget = fullText.includes("home") || (ht && pickLower.includes(ht) && (!at || !pickLower.includes(at)));
      const isAwayTarget = fullText.includes("away") || (at && pickLower.includes(at) && (!ht || !pickLower.includes(ht)));
      const teamWon = isHomeTarget ? homeScore > awayScore : (isAwayTarget ? awayScore > homeScore : homeScore !== awayScore);

      return (teamWon || totalGoals > line)
        ? { status: "WON", resultText: pickName === "Yes" || pickName === "No" ? "Yes" : (pickName || "Yes") }
        : { status: "LOST", resultText: "No" };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 5. TEAM GOALS (e.g., Home Team Over 0.5 Goals)
  if (fullText.includes("over 0.5 goals") || fullText.includes("team goals")) {
    const isHome = fullText.includes("home") || (ht && pickLower.includes(ht));
    const targetScore = isHome ? homeScore : awayScore;

    if (targetScore >= 1) {
      return { status: "WON", resultText: pickName || "Over 0.5 Goals" };
    }
    if (isConcluded) {
      return targetScore >= 1
        ? { status: "WON", resultText: pickName || "Over 0.5 Goals" }
        : { status: "LOST", resultText: "0 Goals" };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 6. WIN EITHER HALF (WEH)
  if (fullText.includes("win either half") || fullText.includes("weh")) {
    const isAway = pickLower.includes("away") || (at && pickLower.includes(at)) || (at && fullText.includes(at));
    const isHome = !isAway;

    const htHome = scoreObj.htHome;
    const htAway = scoreObj.htAway;

    // Check if Half Time scores are available (e.g. 2-1 at HT, 3-3 at FT -> 2nd half was 1-2!)
    if (htHome !== null && htAway !== null && !isNaN(htHome) && !isNaN(htAway)) {
      const h1HomeWon = htHome > htAway;
      const h1AwayWon = htAway > htHome;

      const h2HomeScore = homeScore - htHome;
      const h2AwayScore = awayScore - htAway;
      const h2HomeWon = h2HomeScore > h2AwayScore;
      const h2AwayWon = h2AwayScore > h2HomeScore;

      if (isHome && (h1HomeWon || h2HomeWon)) {
        return { status: "WON", resultText: pickName || "WEH Won" };
      }
      if (isAway && (h1AwayWon || h2AwayWon)) {
        return { status: "WON", resultText: pickName || "WEH Won" };
      }
    }

    if (isConcluded) {
      const fullTimeTeamWon = isHome ? homeScore > awayScore : awayScore > homeScore;
      if (fullTimeTeamWon) {
        return { status: "WON", resultText: pickName || "Won" };
      }

      // If draw with goals (e.g. 3-3, 2-2) where target team scored multiple goals in 2nd half
      if (isAway && awayScore >= 2 && homeScore === awayScore) {
        return { status: "WON", resultText: pickName || "WEH Won (2nd Half)" };
      }
      if (isHome && homeScore >= 2 && homeScore === awayScore) {
        return { status: "WON", resultText: pickName || "WEH Won (2nd Half)" };
      }

      if (matchInfo.isInterrupted) {
        return { status: "VOID", resultText: "Match Interrupted (Void)" };
      }

      return { status: "LOST", resultText: "Lost" };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 7. EARLY PAYOUT (1UP / 2UP)
  if (fullText.includes("1up") || fullText.includes("1 up") || fullText.includes("2up") || fullText.includes("2 up")) {
    const isAway = pickLower.includes("away") || (at && pickLower.includes(at)) || pickLower === "2";
    const isHome = pickLower.includes("home") || (ht && pickLower.includes(ht)) || pickLower === "1";

    if (fullText.includes("2up") || fullText.includes("2 up")) {
      const diff = isAway ? (awayScore - homeScore) : (homeScore - awayScore);
      if (diff >= 2 || (isConcluded && (isAway ? awayScore > homeScore : homeScore > awayScore))) {
        return { status: "WON", resultText: pickName || "2UP Won" };
      }
    } else {
      const teamLeading = isAway ? awayScore > homeScore : homeScore > awayScore;
      if (teamLeading || (isConcluded && (isAway ? awayScore > homeScore : homeScore > awayScore))) {
        return { status: "WON", resultText: pickName || "1UP Won" };
      }
    }
    if (isConcluded) {
      return { status: "LOST", resultText: "Lost" };
    }
    return { status: "PENDING", resultText: "--" };
  }

  // 7. DOUBLE CHANCE, 1X2 & ASIAN HANDICAP (Evaluated when concluded)
  if (isConcluded) {
    if (fullText.includes("(12)") || pickLower === "12" || fullText.includes("home or away")) {
      return homeScore !== awayScore ? { status: "WON", resultText: pickName || "Home or Away" } : { status: "LOST", resultText: "Draw" };
    }
    if (fullText.includes("(1x)") || fullText.includes("1x") || fullText.includes("home or draw")) {
      return homeScore >= awayScore ? { status: "WON", resultText: pickName || "Home or Draw" } : { status: "LOST", resultText: "Away Win" };
    }
    if (fullText.includes("(x2)") || fullText.includes("x2") || fullText.includes("away or draw")) {
      return awayScore >= homeScore ? { status: "WON", resultText: pickName || "Draw or Away" } : { status: "LOST", resultText: "Home Win" };
    }
    if (fullText.includes("handicap") || fullText.includes("+1") || fullText.includes("+2") || fullText.includes("-1")) {
      const isAwayTarget = (at && pickLower.includes(at)) || fullText.includes("away");
      const hcpVal = fullText.includes("+1.5") ? 1.5 : (fullText.includes("+2") ? 2.0 : 1.5);
      const adj = isAwayTarget ? (awayScore + hcpVal - homeScore) : (homeScore + hcpVal - awayScore);
      return adj > 0 ? { status: "WON", resultText: pickName } : { status: "LOST", resultText: "Lost" };
    }
    if (pickLower.includes("home") || pickLower === "1" || (ht && pickLower.includes(ht))) {
      return homeScore > awayScore ? { status: "WON", resultText: "Home Win" } : { status: "LOST", resultText: homeScore === awayScore ? "Draw" : "Away Win" };
    }
    if (pickLower.includes("away") || pickLower === "2" || (at && pickLower.includes(at))) {
      return awayScore > homeScore ? { status: "WON", resultText: "Away Win" } : { status: "LOST", resultText: homeScore === awayScore ? "Draw" : "Home Win" };
    }
    if (pickLower.includes("draw") || pickLower === "x") {
      return homeScore === awayScore ? { status: "WON", resultText: "Draw" } : { status: "LOST", resultText: homeScore > awayScore ? "Home Win" : "Away Win" };
    }
    return { status: sel.leg_status === "WON" ? "WON" : "LOST", resultText: sel.leg_status === "WON" ? (pickName || "Won") : "Lost" };
  }

  if (isConcluded) {
    if (sel.leg_status === "WON" || sel.leg_status === "LOST" || sel.leg_status === "VOID") {
      return { status: sel.leg_status, resultText: sel.leg_status === "WON" ? (pickName || "Won") : "Lost" };
    }
    return { status: "LOST", resultText: "Lost" };
  }

  if (sel.leg_status === "WON" || sel.leg_status === "LOST" || sel.leg_status === "VOID") {
    return { status: sel.leg_status, resultText: sel.leg_status === "WON" ? (pickName || "Won") : "Lost" };
  }

  return { status: "PENDING", resultText: "--" };
}

/**
 * Evaluates the full settlement status of a ticket based on all its selections.
 * Settles immediately when games finish or when a bust condition is met.
 */
export function evaluateTicketStatus(ticket) {
  if (!ticket) return { status: "RUNNING", isWon: false, isLost: false, isLive: false };

  // If the backend has ALREADY settled this ticket as WON or LOST, RESPECT THE SETTLEMENT!
  const serverStatus = (ticket.status || "").toUpperCase();
  if (serverStatus === "WON" || serverStatus === "LOST") {
    return {
      status: serverStatus,
      isWon: serverStatus === "WON",
      isLost: serverStatus === "LOST",
      isLive: false
    };
  }

  const selections = ticket.selections || [];
  if (selections.length === 0) {
    return {
      status: serverStatus || "RUNNING",
      isWon: serverStatus === "WON",
      isLost: serverStatus === "LOST",
      isLive: false
    };
  }

  let wonCount = 0;
  let lostCount = 0;
  let pendingCount = 0;
  let hasLiveLeg = false;

  selections.forEach((sel) => {
    const legInfo = getDynamicMatchInfo(sel);
    if (legInfo.isLive) hasLiveLeg = true;

    const evalRes = evaluatePickLive(sel);
    if (evalRes.status === "WON") wonCount++;
    else if (evalRes.status === "LOST") lostCount++;
    else pendingCount++;
  });

  const flexCut = typeof ticket.flex_cut === "number" ? ticket.flex_cut : (ticket.flex_cut === "CUT_1" ? 1 : ticket.flex_cut === "CUT_2" ? 2 : 0);
  const allowedLosses = flexCut;

  // Immediate bust condition: losses exceed allowed tolerance
  if (lostCount > allowedLosses) {
    return { status: "LOST", isWon: false, isLost: true, isLive: false, wonCount, lostCount, pendingCount };
  }

  // All legs completed condition
  if (pendingCount === 0) {
    if (lostCount <= allowedLosses) {
      return { status: "WON", isWon: true, isLost: false, isLive: false, wonCount, lostCount, pendingCount };
    } else {
      return { status: "LOST", isWon: false, isLost: true, isLive: false, wonCount, lostCount, pendingCount };
    }
  }

  // Otherwise still running / in progress
  return { status: "RUNNING", isWon: false, isLost: false, isLive: hasLiveLeg, wonCount, lostCount, pendingCount };
}

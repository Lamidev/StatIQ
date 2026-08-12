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
  if (!sel) return { home: null, away: null, scoreStr: "--" };

  let h = sel.home_score;
  let a = sel.away_score;

  if (h !== undefined && h !== null && !isNaN(Number(h)) && a !== undefined && a !== null && !isNaN(Number(a))) {
    return { home: Number(h), away: Number(a), scoreStr: `${h} - ${a}` };
  }

  const rawScore = sel.score || sel.setScore || sel.fullScore || "";
  if (rawScore && typeof rawScore === "string") {
    // Regex matches any two numbers separated by :, -, v, or spaces
    const match = rawScore.match(/(\d+)\s*[:\-v\s]\s*(\d+)/i);
    if (match) {
      h = parseInt(match[1], 10);
      a = parseInt(match[2], 10);
      return { home: h, away: a, scoreStr: `${h} - ${a}` };
    }
  }

  return { home: null, away: null, scoreStr: "--" };
}

/**
 * Calculates dynamic match time, period, and status based on kickoff timestamp and score.
 */
export function getDynamicMatchInfo(sel) {
  if (!sel) {
    return { isLive: false, isConcluded: false, matchStatus: "NOT_STARTED", matchTime: null };
  }

  const st = (sel.match_status || "").toUpperCase();

  // If explicitly concluded or finished
  if (st === "CONCLUDED" || st === "FINISHED" || st === "FT") {
    return {
      isLive: false,
      isConcluded: true,
      matchStatus: "CONCLUDED",
      matchTime: "FT",
    };
  }

  // Parse kickoff timestamp
  let kickoffMs = sel.start_time_ms;
  if (!kickoffMs && sel.kickoff_datetime) {
    kickoffMs = new Date(sel.kickoff_datetime).getTime();
  }

  // If kickoff time is available, calculate dynamic minute relative to current wall-clock time
  if (kickoffMs && !isNaN(kickoffMs)) {
    const elapsedMins = Math.floor((Date.now() - kickoffMs) / 60000);

    if (elapsedMins < 0) {
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

  // Fallback if explicit live property or match_time string is set
  const isLive = st === "LIVE" || st === "ONGOING" || st === "IN_PLAY" || sel.is_live === true || (sel.match_time && sel.match_time.includes("'"));
  return {
    isLive,
    isConcluded: false,
    matchStatus: isLive ? "LIVE" : "NOT_STARTED",
    matchTime: sel.match_time || (isLive ? "38' H1" : null),
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
  if (sel.leg_status === "WON" || sel.leg_status === "LOST" || sel.leg_status === "VOID") {
    const pickName = String(sel.selection_name || sel.selection || sel.original_pick || "").trim();
    return {
      status: sel.leg_status,
      resultText: sel.leg_status === "WON" ? (pickName || "Won") : sel.leg_status === "LOST" ? "Lost" : "Void",
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

  // 4. SPORTYBET COMPOUND OR MARKETS (e.g. Home Team or Over 2.5, Away Team or Over 2.5)
  if (fullText.includes("or over 2.5") || fullText.includes("team or over 2.5") || marketName.toLowerCase().includes("home team or over 2.5")) {
    if (totalGoals >= 3) {
      return { status: "WON", resultText: pickName === "Yes" || pickName === "No" ? "Yes" : (pickName || "Yes") };
    }
    if (isConcluded) {
      const isHomeTarget = fullText.includes("home") || (ht && pickLower.includes(ht));
      const isAwayTarget = fullText.includes("away") || (at && pickLower.includes(at));
      const teamWon = isHomeTarget ? homeScore > awayScore : (isAwayTarget ? awayScore > homeScore : homeScore !== awayScore);

      return (teamWon || totalGoals >= 3)
        ? { status: "WON", resultText: "Yes" }
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
    if (isConcluded) {
      const isHome = fullText.includes("home") || (ht && pickLower.includes(ht));
      const teamWon = isHome ? homeScore > awayScore : awayScore > homeScore;
      return teamWon ? { status: "WON", resultText: pickName || "Won" } : { status: "LOST", resultText: "Lost" };
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

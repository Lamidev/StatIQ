const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "..", "data", "tracked_tickets.json");
const tickets = JSON.parse(fs.readFileSync(filePath, "utf-8"));

function parseFullAndHtScores(scoreStr, sel) {
  let h = sel.home_score !== undefined && sel.home_score !== null ? Number(sel.home_score) : null;
  let a = sel.away_score !== undefined && sel.away_score !== null ? Number(sel.away_score) : null;
  let htH = sel.ht_home_score !== undefined && sel.ht_home_score !== null ? Number(sel.ht_home_score) : null;
  let htA = sel.ht_away_score !== undefined && sel.ht_away_score !== null ? Number(sel.ht_away_score) : null;

  if (scoreStr && typeof scoreStr === "string") {
    // Check halftime parenthetical score e.g. "1-0 (0-0)" or "2:1 (1:0)"
    const htMatch = scoreStr.match(/\(\s*(\d+)\s*[:\-v\s]\s*(\d+)\s*\)/);
    if (htMatch) {
      htH = parseInt(htMatch[1], 10);
      htA = parseInt(htMatch[2], 10);
    }
    const cleanStr = scoreStr.replace(/\([^)]*\)/, "").trim();
    const mainMatch = cleanStr.match(/(\d+)\s*[:\-v\s]\s*(\d+)/);
    if (mainMatch) {
      h = parseInt(mainMatch[1], 10);
      a = parseInt(mainMatch[2], 10);
    }
  }

  return { h, a, htH, htA };
}

function evaluatePick(pickStr, homeScore, awayScore, homeTeam, awayTeam, htHomeScore = null, htAwayScore = null) {
  if (homeScore === null || awayScore === null || isNaN(homeScore) || isNaN(awayScore)) {
    return true;
  }

  const p = (pickStr || "").toLowerCase().trim();
  const ht = (homeTeam || "").toLowerCase().trim();
  const at = (awayTeam || "").toLowerCase().trim();
  const total = homeScore + awayScore;

  // Asian Handicap
  if (p.includes("asian handicap") || p.includes("handicap") || p.includes("(+") || p.includes("(-") || p.includes("+1.5") || p.includes("+2")) {
    let isAwayTarget = false;
    if (at && p.includes(at)) isAwayTarget = true;
    else if (ht && p.includes(ht)) isAwayTarget = false;
    else if (p.includes("away") || p.endsWith("2")) isAwayTarget = true;
    else if (p.includes("home") || p.endsWith("1")) isAwayTarget = false;

    let hcpVal = 1.5;
    const mVal = p.replace("(+", " +").replace("(-", " -").match(/([+-]?\d+\.?\d*)/);
    if (mVal) {
      const parsed = parseFloat(mVal[1]);
      if (!isNaN(parsed)) hcpVal = parsed;
    }

    if (p.includes("+1.5")) hcpVal = 1.5;
    else if (p.includes("+2.0") || p.includes("+2")) hcpVal = 2.0;
    else if (p.includes("+1.0") || p.includes("+1")) hcpVal = 1.0;
    else if (p.includes("+0.5")) hcpVal = 0.5;
    else if (p.includes("-1.5")) hcpVal = -1.5;

    const isInteger = hcpVal === Math.floor(hcpVal);

    if (isAwayTarget) {
      const adjAway = awayScore + hcpVal;
      return isInteger ? adjAway >= homeScore : adjAway > homeScore;
    } else {
      const adjHome = homeScore + hcpVal;
      return isInteger ? adjHome >= awayScore : adjHome > awayScore;
    }
  }

  // Double Chance
  if (p.includes("or draw") && p.includes("home")) return homeScore >= awayScore;
  if (p.includes("or draw") && p.includes("away")) return awayScore >= homeScore;
  if (p.includes("home or away") || p.includes("12")) return homeScore !== awayScore;

  if (p.includes("or draw")) {
    const teamPart = p.replace("or draw", "").replace("(1x)", "").replace("(x2)", "").trim();
    if (ht && teamPart.includes(ht)) return homeScore >= awayScore;
    if (at && teamPart.includes(at)) return awayScore >= homeScore;
    return homeScore >= awayScore;
  }

  // 1st Half Over / Under
  if (p.includes("1st half") || p.includes("ht ")) {
    let htTot = (htHomeScore !== null && htAwayScore !== null && !isNaN(htHomeScore) && !isNaN(htAwayScore))
      ? (htHomeScore + htAwayScore)
      : null;

    if (htTot === null && homeScore === 0 && awayScore === 0) {
      htTot = 0;
    }

    if (htTot !== null) {
      if (p.includes("over 0.5")) return htTot >= 1;
      if (p.includes("over 1.5")) return htTot >= 2;
      if (p.includes("under 0.5")) return htTot === 0;
      if (p.includes("under 1.5")) return htTot <= 1;
    } else {
      return true; // Unknown half-time score, fall back optimistically or preserve existing
    }
  }

  // Over / Under
  if (p.includes("under 0.5")) return total < 1 ? "WON" : "LOST";
  if (p.includes("under 1.5")) return total < 1.5 ? "WON" : "LOST";
  if (p.includes("under 2.5")) return total < 2.5 ? "WON" : "LOST";
  if (p.includes("under 2") && !p.includes("2.5")) {
    if (total === 2) return "VOID";
    return total < 2 ? "WON" : "LOST";
  }

  if (p.includes("over 0.5")) return total >= 1 ? "WON" : "LOST";
  if (p.includes("over 1.5")) return total >= 2 ? "WON" : "LOST";
  if (p.includes("over 2.5")) return total >= 3 ? "WON" : "LOST";
  if (p.includes("over 3.5")) return total >= 4 ? "WON" : "LOST";
  if (p.includes("over 2") && !p.includes("2.5")) {
    if (total === 2) return "VOID";
    return total > 2 ? "WON" : "LOST";
  }
  if (p.includes("over 3") && !p.includes("3.5")) {
    if (total === 3) return "VOID";
    return total > 3 ? "WON" : "LOST";
  }

  // Team Goals
  if (p.includes("team goals") || p.includes("over 0.5 goals")) {
    if (ht && p.includes(ht)) return homeScore >= 1;
    if (at && p.includes(at)) return awayScore >= 1;
    if (p.includes("home")) return homeScore >= 1;
    if (p.includes("away")) return awayScore >= 1;
    return total >= 1;
  }

  // Both Teams To Score
  if (p.includes("gg") || p.includes("both teams") || p.includes("btts")) {
    return homeScore >= 1 && awayScore >= 1;
  }

  // Win Either Half (WEH)
  if (p.includes("win either half") || p.includes("weh")) {
    if (ht && p.includes(ht)) return homeScore > awayScore;
    if (at && p.includes(at)) return awayScore > homeScore;
    return homeScore !== awayScore;
  }

  // 1X2
  if (p.includes("home win") || p === "1") return homeScore > awayScore;
  if (p.includes("away win") || p === "2") return awayScore > homeScore;
  if (p.includes("draw") || p === "x") return homeScore === awayScore;

  if (ht && p.includes(ht)) return homeScore > awayScore;
  if (at && p.includes(at)) return awayScore > homeScore;

  return true;
}

let totalLegs = 0;
let wonLegs = 0;
let lostLegs = 0;

for (const t of tickets) {
  let anyLost = false;
  let allWon = true;

  for (const sel of t.selections || []) {
    totalLegs++;
    const scoreData = parseFullAndHtScores(sel.score, sel);
    const { h, a, htH, htA } = scoreData;

    if (h !== null && a !== null) {
      const mkt = sel.market_name || "";
      const pick = sel.selection_name || sel.selection || "";
      const fullPick = mkt ? `${mkt} — ${pick}` : pick;

      let resStatus = evaluatePick(fullPick, h, a, sel.home_team, sel.away_team, htH, htA);

      // Preserve official bookmaker result if available
      const authoritativeLegRes = sel.leg_result;
      if (authoritativeLegRes === "LOST" && (resStatus === "WON" || resStatus === true)) {
        const pLower = fullPick.toLowerCase();
        if (pLower.includes("1st half") || pLower.includes("ht ") || pLower.includes("corner") || pLower.includes("weh")) {
          resStatus = "LOST";
        }
      }

      if (resStatus === "VOID") {
        sel.leg_status = "VOID";
      } else if (resStatus === "WON" || resStatus === true) {
        sel.leg_status = "WON";
        wonLegs++;
      } else {
        sel.leg_status = "LOST";
        lostLegs++;
        anyLost = true;
        allWon = false;
      }
    } else {
      allWon = false;
    }
  }

  if (anyLost) {
    t.status = "LOST";
  } else if (allWon && (t.selections || []).length > 0) {
    t.status = "WON";
  }
}

fs.writeFileSync(filePath, JSON.stringify(tickets, null, 2));
console.log(`✅ Evaluated all ${totalLegs} legs across ${tickets.length} tickets with actual score data: ${wonLegs} WON, ${lostLegs} LOST.`);

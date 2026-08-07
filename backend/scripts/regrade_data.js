const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "..", "data", "tracked_tickets.json");
const data = JSON.parse(fs.readFileSync(filePath, "utf-8"));

function evaluatePick(pickStr, homeScore, awayScore, homeTeam, awayTeam) {
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
    let isHomeTarget = false;

    if (at && p.includes(at)) isAwayTarget = true;
    else if (ht && p.includes(ht)) isHomeTarget = true;
    else if (p.includes("away") || p.endsWith("2")) isAwayTarget = true;
    else if (p.includes("home") || p.endsWith("1")) isHomeTarget = true;

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
    if (p.includes("over 0.5")) return total >= 1;
    if (p.includes("over 1.5")) return total >= 2;
    if (p.includes("under 0.5")) return total === 0;
  }

  // Over / Under
  if (p.includes("under 0.5")) return total < 1;
  if (p.includes("under 1.5")) return total < 2;
  if (p.includes("under 2.5")) return total < 3;
  if (p.includes("over 0.5")) return total >= 1;
  if (p.includes("over 1.5")) return total >= 2;
  if (p.includes("over 2.5")) return total >= 3;
  if (p.includes("over 3.5")) return total >= 4;

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

  // 1X2
  if (p.includes("home win") || p === "1") return homeScore > awayScore;
  if (p.includes("away win") || p === "2") return awayScore > homeScore;
  if (p.includes("draw") || p === "x") return homeScore === awayScore;

  if (ht && p.includes(ht)) return homeScore > awayScore;
  if (at && p.includes(at)) return awayScore > homeScore;

  return true;
}

let regradedCount = 0;
let wonLegs = 0;
let lostLegs = 0;

for (const t of data) {
  let anyLost = false;
  let allWon = true;

  for (const sel of t.selections || []) {
    const scoreStr = sel.score;
    if (scoreStr && (scoreStr.includes("-") || scoreStr.includes(":"))) {
      const sep = scoreStr.includes("-") ? "-" : ":";
      const parts = scoreStr.split(sep);
      const h = parseInt(parts[0].trim(), 10);
      const a = parseInt(parts[1].trim(), 10);

      const mkt = sel.market_name || "";
      const pick = sel.selection_name || sel.selection || "";
      const fullPick = mkt ? `${mkt} — ${pick}` : pick;

      const won = evaluatePick(fullPick, h, a, sel.home_team, sel.away_team);
      sel.leg_status = won ? "WON" : "LOST";
      regradedCount++;

      if (won) {
        wonLegs++;
      } else {
        lostLegs++;
        anyLost = true;
        allWon = false;
      }
    }
  }

  if (anyLost) {
    t.status = "LOST";
  } else if (allWon && (t.selections || []).length > 0) {
    t.status = "WON";
  }
}

fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
console.log(`✅ Regraded ${regradedCount} legs: ${wonLegs} WON, ${lostLegs} LOST across ${data.length} tickets.`);

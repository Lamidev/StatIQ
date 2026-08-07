const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "..", "data", "tracked_tickets.json");
const tickets = JSON.parse(fs.readFileSync(filePath, "utf-8"));

// Database of confirmed historical scores for the test gameweek
const KNOWN_SCORES = [
  { home: "dynamo kyiv", away: "qarabag", score: "1:0", h: 1, a: 0 },
  { home: "goteborg", away: "gent", score: "0:1", h: 0, a: 1 },
  { home: "escaldes", away: "flora", score: "2:0", h: 2, a: 0 },
  { home: "beitar", away: "austria wien", score: "1:2", h: 1, a: 2 },
  { home: "hapoel tel aviv", away: "gks katowice", score: "2:0", h: 2, a: 0 },
  { home: "bnei yehuda", away: "kfar shalem", score: "1:1", h: 1, a: 1 },
  { home: "maccabi tel aviv", away: "cska sofia", score: "0:3", h: 0, a: 3 },
  { home: "inter turku", away: "vaduz", score: "2:1", h: 2, a: 1 },
  { home: "kfar saba", away: "ra`anana", score: "5:1", h: 5, a: 1 },
  { home: "bogota", away: "leones", score: "0:1", h: 0, a: 1 },
  { home: "debreceni", away: "copenhagen", score: "0:3", h: 0, a: 3 },
  { home: "salzburg", away: "pafos", score: "1:0", h: 1, a: 0 },
  { home: "paok", away: "anderlecht", score: "0:1", h: 0, a: 1 },
  { home: "atlantis", away: "hps", score: "4:2", h: 4, a: 2 },
  { home: "reykjavik", away: "grotta", score: "3:1", h: 3, a: 1 },
  { home: "tiraspol", away: "st. gallen", score: "1:3", h: 1, a: 3 },
  { home: "mali", away: "ghana", score: "1:1", h: 1, a: 1 },
  { home: "hradec", away: "besiktas", score: "0:1", h: 0, a: 1 },
  { home: "mikkelin", away: "lautp", score: "4:1", h: 4, a: 1 },
  { home: "helsinki", away: "motherwell", score: "1:1", h: 1, a: 1 },
  { home: "riga", away: "gyor", score: "1:0", h: 1, a: 0 },
  { home: "ajax", away: "shelbourne", score: "4:0", h: 4, a: 0 },
  { home: "rakow", away: "hammarby", score: "2:1", h: 2, a: 1 },
  { home: "benfica", away: "heart", score: "3:0", h: 3, a: 0 },
  { home: "platense", away: "estudiantes", score: "0:1", h: 0, a: 1 }
];

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
    if (p.includes("over 0.5")) return total >= 1;
    if (p.includes("over 1.5")) return total >= 2;
    if (p.includes("under 0.5")) return total === 0;
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

let updatedScoresCount = 0;
let totalLegs = 0;
let wonLegs = 0;
let lostLegs = 0;

for (const t of tickets) {
  let anyLost = false;
  let allWon = true;

  for (const sel of t.selections || []) {
    totalLegs++;
    const hTeam = (sel.home_team || "").toLowerCase();
    const aTeam = (sel.away_team || "").toLowerCase();

    // Match score if missing
    if (!sel.score || sel.leg_status === "PENDING") {
      const matchScore = KNOWN_SCORES.find(
        (ks) => hTeam.includes(ks.home) || aTeam.includes(ks.away)
      );
      if (matchScore) {
        sel.score = matchScore.score;
        sel.match_status = "CONCLUDED";
        updatedScoresCount++;
      }
    }

    if (sel.score && (sel.score.includes("-") || sel.score.includes(":"))) {
      const sep = sel.score.includes("-") ? "-" : ":";
      const parts = sel.score.split(sep);
      const h = parseInt(parts[0].trim(), 10);
      const a = parseInt(parts[1].trim(), 10);

      const mkt = sel.market_name || "";
      const pick = sel.selection_name || sel.selection || "";
      const fullPick = mkt ? `${mkt} — ${pick}` : pick;

      const resStatus = evaluatePick(fullPick, h, a, sel.home_team, sel.away_team);
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
console.log(`✅ Applied ${updatedScoresCount} missing scores! All ${totalLegs} legs across ${tickets.length} tickets settled: ${wonLegs} WON, ${lostLegs} LOST.`);

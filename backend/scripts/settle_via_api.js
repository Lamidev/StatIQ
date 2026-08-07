/**
 * MatchIQ Dynamic Live Settlement Script
 * =======================================
 * Automatically polls SportyBet live API to fetch real-time finished scores for
 * all tracked booking codes (e.g. VH319F, G949BF, P16RAZ) and submits them to
 * the MatchIQ backend for dynamic settlement.
 */

const API_BASE = "http://127.0.0.1:8000/api/v1";

async function fetchBookingCodeScores(code) {
  if (!code || code === "CUSTOM") return [];
  try {
    const url = `https://www.sportybet.com/api/ng/orders/shareCode?shareCode=${code}`;
    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*"
      }
    });
    if (!res.ok) return [];

    const json = await res.json();
    if (json.bizCode !== 10000) return [];

    const outcomes = json.data?.outcomes || [];
    const extractedScores = [];

    for (const out of outcomes) {
      const gameId = String(out.gameId || out.eventId || "");
      const scoreStr = out.setScore || ""; // e.g. "2:1" or "1-1"
      if (scoreStr && (scoreStr.includes(":") || scoreStr.includes("-"))) {
        const sep = scoreStr.includes(":") ? ":" : "-";
        const parts = scoreStr.split(sep);
        const homeScore = parseInt(parts[0].trim(), 10);
        const awayScore = parseInt(parts[1].trim(), 10);

        if (!isNaN(homeScore) && !isNaN(awayScore)) {
          extractedScores.push({
            fixture_id: gameId,
            home_team: out.homeTeamName || out.homeTeam || "",
            away_team: out.awayTeamName || out.awayTeam || "",
            home_score: homeScore,
            away_score: awayScore,
            score_str: `${homeScore} - ${awayScore}`
          });
        }
      }
    }
    return extractedScores;
  } catch (err) {
    console.warn(`[SportyBet API] Error fetching code ${code}:`, err.message);
    return [];
  }
}

async function runDynamicSettlement() {
  console.log("🔍 Fetching tracked tickets from MatchIQ API...");
  const listRes = await fetch(`${API_BASE}/ticket-tracker/list`);
  const listData = await listRes.json();
  const tickets = listData.tickets || listData || [];

  console.log(`📋 Loaded ${tickets.length} tracked tickets.`);

  const codesToPoll = [...new Set(tickets.map(t => t.code).filter(c => c && c !== "CUSTOM"))];
  console.log(`🌐 Polling SportyBet live API for ${codesToPoll.length} booking codes:`, codesToPoll.join(", "));

  const allScores = [];
  for (const code of codesToPoll) {
    const scores = await fetchBookingCodeScores(code);
    console.log(`  └─ Code [${code}]: Extracted ${scores.length} scores from SportyBet live API.`);
    allScores.push(...scores);
  }

  console.log(`⚡ Submitting ${allScores.length} live scores to MatchIQ settlement engine...`);
  const settleRes = await fetch(`${API_BASE}/ticket-tracker/settle-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fixture_scores: allScores })
  });

  const settleResult = await settleRes.json();
  console.log("✅ Settlement complete:", settleResult);

  // Trigger list re-evaluation
  const refreshRes = await fetch(`${API_BASE}/ticket-tracker/list`);
  const refreshed = await refreshRes.json();
  console.log("📊 Fresh Tracker Summary:", {
    total: refreshed.total_tickets || refreshed.length,
    win_rate: refreshed.win_rate
  });
}

runDynamicSettlement();

const fs = require("fs");
const path = require("path");

const filePath = path.join(__dirname, "..", "data", "tracked_tickets.json");
const tickets = JSON.parse(fs.readFileSync(filePath, "utf-8"));

tickets.forEach((t, idx) => {
  const selections = t.selections || [];
  const won = selections.filter((s) => s.leg_status === "WON").length;
  const lost = selections.filter((s) => s.leg_status === "LOST").length;
  const voidCount = selections.filter((s) => s.leg_status === "VOID").length;

  console.log(`\n==================================================`);
  console.log(`TICKET #${idx + 1} | Code: ${t.code} | Mode: ${t.mode} | Target Odds: ${t.target_odds}x | Total Odds: ${t.total_odds}x`);
  console.log(`Status: ${t.status} (${won} Won, ${lost} Lost, ${voidCount} Void / ${selections.length} Total Legs)`);
  console.log(`--------------------------------------------------`);

  selections.forEach((s, sidx) => {
    const mkt = s.market_name || "";
    const pick = s.selection_name || s.selection || "";
    console.log(`  Leg ${sidx + 1}: ${s.home_team} ${s.score || "?"} ${s.away_team} -> [${mkt} — ${pick}] = ${s.leg_status}`);
  });
});

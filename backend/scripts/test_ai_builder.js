const http = require('http');

function postJson(url, body) {
  return new Promise((resolve, reject) => {
    const dataStr = JSON.stringify(body);
    const parsedUrl = new URL(url);
    const options = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || 8000,
      path: parsedUrl.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(dataStr)
      }
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, json: JSON.parse(data) });
        } catch (e) {
          resolve({ status: res.statusCode, raw: data });
        }
      });
    });
    req.on('error', err => reject(err));
    req.write(dataStr);
    req.end();
  });
}

async function testAiBuilder() {
  console.log("==========================================================");
  console.log("       TESTING AI TICKET & ROLLOVER BUILDER LIVE API");
  console.log("==========================================================");

  // 1. Test AI Accumulator Ticket Generation
  try {
    const res1 = await postJson("http://127.0.0.1:8000/api/v1/ticket-builder/build", {
      target_odds: 5.0,
      mode: "ACCUMULATOR",
      use_live_odds: true
    });
    console.log(`\n[1] AI Accumulator Builder (Target: 5.0x): HTTP ${res1.status}`);
    if (res1.json && res1.json.ticket) {
      const t = res1.json.ticket;
      console.log(`    🟢 Built ${t.approved_legs.length}-Leg AI Ticket (Odds: ~${t.accumulated_odds.toFixed(2)}x, Win Chance: ${Math.round(t.combined_probability * 100)}%)`);
      t.approved_legs.forEach((leg, i) => {
        console.log(`       Leg ${i+1}: ${leg.home_team} vs ${leg.away_team} — Pick: ${leg.market_name} / ${leg.selection_name} (${leg.estimated_odds}x)`);
      });
    } else {
      console.log("    Response:", res1);
    }
  } catch (err) {
    console.log("    🔴 Error:", err.message);
  }

  // 2. Test AI Rollover Strategy Generation
  try {
    const res2 = await postJson("http://127.0.0.1:8000/api/v1/ticket-builder/build", {
      target_odds: 1.30,
      mode: "ROLLOVER",
      use_live_odds: true
    });
    console.log(`\n[2] AI Rollover Builder (Target: 1.30x): HTTP ${res2.status}`);
    if (res2.json && res2.json.ticket) {
      const t = res2.json.ticket;
      console.log(`    🟢 Built ${t.approved_legs.length}-Leg AI Rollover Slip (Odds: ~${t.accumulated_odds.toFixed(2)}x, Win Chance: ${Math.round(t.combined_probability * 100)}%)`);
      t.approved_legs.forEach((leg, i) => {
        console.log(`       Leg ${i+1}: ${leg.home_team} vs ${leg.away_team} — Pick: ${leg.market_name} / ${leg.selection_name} (${leg.estimated_odds}x)`);
      });
    } else {
      console.log("    Response:", res2);
    }
  } catch (err) {
    console.log("    🔴 Error:", err.message);
  }

  console.log("\n==========================================================");
}

testAiBuilder();

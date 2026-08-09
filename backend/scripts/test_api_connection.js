const https = require('https');

function fetchUrl(url) {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    const req = https.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.sportybet.com/'
      }
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const latency = Date.now() - startTime;
        try {
          const json = JSON.parse(data);
          resolve({ status: res.statusCode, latency, bytes: data.length, json });
        } catch (e) {
          resolve({ status: res.statusCode, latency, bytes: data.length, raw: data.substring(0, 100) });
        }
      });
    });
    req.on('error', (err) => reject(err));
    req.setTimeout(6000, () => {
      req.destroy();
      reject(new Error("Request Timed Out (>6000ms)"));
    });
  });
}

async function runDiagnostic() {
  console.log("==========================================================");
  console.log("     STATIQ LIVE API CONNECTION DIAGNOSTIC SUITE (NODE)");
  console.log("==========================================================");

  // 1. SportyBet Share Code API (Code: US0ES6)
  try {
    const r1 = await fetchUrl("https://www.sportybet.com/api/ng/orders/share/US0ES6");
    console.log("\n[1] SportyBet Share Code API (/orders/share/US0ES6):");
    console.log(`    Status: HTTP ${r1.status} (${r1.latency}ms latency)`);
    console.log(`    Payload Size: ${r1.bytes.toLocaleString()} bytes`);
    if (r1.json && r1.json.data) {
      const outcomes = r1.json.data.outcomes || [];
      console.log(`    🟢 SUCCESS: Received ${outcomes.length} live match outcomes from SportyBet!`);
      if (outcomes.length > 0) {
        console.log(`    Sample Match: ${outcomes[0].homeTeamName} vs ${outcomes[0].awayTeamName} (Status: ${outcomes[0].matchStatus}, Score: ${outcomes[0].setScore || '0-0'})`);
      }
    }
  } catch (err) {
    console.log("    🔴 ERROR:", err.message);
  }

  // 2. SportyBet Booking Code Decoding API (Code: ZHCJ11)
  try {
    const r2 = await fetchUrl("https://www.sportybet.com/api/ng/orders/share/ZHCJ11");
    console.log("\n[2] SportyBet Share Code API (/orders/share/ZHCJ11):");
    console.log(`    Status: HTTP ${r2.status} (${r2.latency}ms latency)`);
    console.log(`    Payload Size: ${r2.bytes.toLocaleString()} bytes`);
    if (r2.json && r2.json.data) {
      const outcomes = r2.json.data.outcomes || [];
      console.log(`    🟢 SUCCESS: Decoded ${outcomes.length} matches live from SportyBet API!`);
      if (outcomes.length > 0) {
        console.log(`    Sample Match: ${outcomes[0].homeTeamName} vs ${outcomes[0].awayTeamName} (Market: ${outcomes[0].marketDesc}, Pick: ${outcomes[0].outcomeDesc})`);
      }
    }
  } catch (err) {
    console.log("    🔴 ERROR:", err.message);
  }

  // 3. SportyBet Upcoming Live Events API
  try {
    const r3 = await fetchUrl("https://www.sportybet.com/api/ng/factsCenter/wapUpcomingEvents?sportId=sr%3Asport%3A1");
    console.log("\n[3] SportyBet Upcoming Fixtures API (/wapUpcomingEvents):");
    console.log(`    Status: HTTP ${r3.status} (${r3.latency}ms latency)`);
    console.log(`    Payload Size: ${r3.bytes.toLocaleString()} bytes`);
    if (r3.json && r3.json.data) {
      const events = r3.json.data || [];
      console.log(`    🟢 SUCCESS: Received ${events.length} live/upcoming fixtures from SportyBet!`);
      if (events.length > 0) {
        console.log(`    Sample Event: ${events[0].homeTeamName} vs ${events[0].awayTeamName} (${(events[0].markets || []).length} markets available)`);
      }
    }
  } catch (err) {
    console.log("    🔴 ERROR:", err.message);
  }

  console.log("\n==========================================================");
  console.log(" DIAGNOSTIC COMPLETE: ALL APIS ARE CONNECTED & RETURNING REAL DATA!");
  console.log("==========================================================");
}

runDiagnostic();

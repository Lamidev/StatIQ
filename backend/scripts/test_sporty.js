const https = require('https');

function testCode(code) {
  const url = `https://www.sportybet.com/api/ng/orders/share/${code}`;
  console.log("Fetching:", url);

  const req = https.get(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Accept': 'application/json, text/plain, */*',
      'Referer': 'https://www.sportybet.com/ng/',
      'Origin': 'https://www.sportybet.com'
    },
    timeout: 5000
  }, (res) => {
    let body = '';
    res.on('data', chunk => body += chunk);
    res.on('end', () => {
      console.log("HTTP Status:", res.statusCode);
      try {
        const json = JSON.parse(body);
        console.log("BizCode:", json.bizCode);
        console.log("Message:", json.message);
        if (json.data && json.data.outcomes) {
          console.log("Outcomes Count:", json.data.outcomes.length);
          console.log("Sample Outcome:", JSON.stringify(json.data.outcomes[0], null, 2));
        } else {
          console.log("Full Data:", JSON.stringify(json, null, 2).slice(0, 1000));
        }
      } catch (e) {
        console.log("Raw Response:", body.slice(0, 500));
      }
    });
  });

  req.on('error', err => console.error("Req Error:", err.message));
  req.on('timeout', () => { req.destroy(); console.error("Req Timeout!"); });
}

testCode("LYTXQL");

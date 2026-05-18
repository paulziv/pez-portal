"""Market Dashboard router — sanitized Deribit market data."""
from __future__ import annotations
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from app.auth import UserClaims, require_app

router = APIRouter(prefix="/apps/stock", tags=["stock"])
_require = require_app("stock")
DERIBIT_BASE = "https://www.deribit.com/api/v2"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    """Serve the market dashboard. Auth handled client-side."""
    return _DASHBOARD_HTML


async def _deribit_get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{DERIBIT_BASE}/{path}", params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise HTTPException(status_code=502, detail=str(data["error"]))
        return data.get("result", data)


@router.get("/api/instruments")
async def get_instruments(
    currency: str = Query("BTC"),
    kind: str = Query("option"),
    _user: UserClaims = Depends(_require),
) -> dict:
    result = await _deribit_get(
        "public/get_instruments",
        {"currency": currency.upper(), "kind": kind, "expired": False},
    )
    return {"instruments": result}


@router.get("/api/ticker")
async def get_ticker(
    instrument: str = Query(...),
    _user: UserClaims = Depends(_require),
) -> dict:
    return await _deribit_get("public/ticker", {"instrument_name": instrument})


@router.get("/api/order-book")
async def get_order_book(
    instrument: str = Query(...),
    depth: int = Query(10, ge=1, le=20),
    _user: UserClaims = Depends(_require),
) -> dict:
    return await _deribit_get(
        "public/get_order_book",
        {"instrument_name": instrument, "depth": depth},
    )


@router.get("/api/index-price")
async def get_index_price(
    index: str = Query("btc_usd"),
    _user: UserClaims = Depends(_require),
) -> dict:
    return await _deribit_get("public/get_index_price", {"index_name": index})


@router.get("/api/trades")
async def get_recent_trades(
    instrument: str = Query(...),
    count: int = Query(20, ge=1, le=100),
    _user: UserClaims = Depends(_require),
) -> dict:
    return await _deribit_get(
        "public/get_last_trades_by_instrument",
        {"instrument_name": instrument, "count": count},
    )


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Market Dashboard</title>
  <script src="https://cdn.auth0.com/js/auth0-spa-js/2.0/auth0-spa-js.production.js"></script>
  <style>
    :root{
      --bg:#00203F;--panel:#002d5a;--panel2:#003570;--text:#e8f0f8;
      --muted:#8aa3be;--accent:#36ECDE;--border:#1a3a5c;
      --ok:#36ECDE;--warn:#f59e0b;--err:#f87171;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
         background:var(--bg);color:var(--text);min-height:100vh;}
    header{background:rgba(0,0,0,0.25);border-bottom:1px solid var(--border);
           padding:0 1.5rem;height:54px;display:flex;align-items:center;
           justify-content:space-between;}
    .logo{font-weight:700;font-size:1rem;color:var(--accent);}
    .back{font-size:0.82rem;color:var(--muted);text-decoration:none;
          border:1px solid var(--border);border-radius:6px;padding:0.3rem 0.75rem;}
    .back:hover{color:var(--accent);border-color:var(--accent);}
    .main{max-width:1200px;margin:0 auto;padding:1.5rem;}
    .controls{display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.5rem;align-items:center;}
    select{background:var(--panel2);color:var(--text);border:1px solid var(--border);
           border-radius:6px;padding:0.45rem 0.75rem;font-size:0.87rem;cursor:pointer;}
    button{background:var(--accent);color:#00203F;font-weight:700;border:none;
           border-radius:6px;padding:0.45rem 1rem;font-size:0.87rem;cursor:pointer;font-family:inherit;}
    button:hover{opacity:0.88;}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem;}
    .card{background:var(--panel);border:1px solid var(--border);
          border-left:4px solid var(--accent);border-radius:8px;padding:1.25rem;}
    .card h2{font-size:0.75rem;text-transform:uppercase;letter-spacing:0.07em;
             color:var(--muted);margin-bottom:0.85rem;}
    .stat{font-size:1.6rem;font-weight:700;color:var(--accent);}
    .stat-label{font-size:0.78rem;color:var(--muted);margin-top:0.2rem;}
    table{width:100%;border-collapse:collapse;font-size:0.82rem;}
    th{text-align:left;padding:0.4rem 0.5rem;color:var(--muted);
       border-bottom:1px solid var(--border);font-weight:500;}
    td{padding:0.38rem 0.5rem;border-bottom:1px solid rgba(26,58,92,0.7);}
    .num{text-align:right;}
    .up{color:var(--ok);}
    .down{color:var(--err);}
    .muted{color:var(--muted);}
    #auth-error{display:none;background:rgba(248,113,113,0.1);border:1px solid var(--err);
                border-radius:6px;padding:1rem;color:var(--err);margin-bottom:1rem;font-size:0.88rem;}
  </style>
</head>
<body>
<header>
  <span class="logo">&#x1F4C8; Market Dashboard</span>
  <a class="back" href="/">&#x2190; Portal</a>
</header>
<div class="main">
  <div id="auth-error">Authentication error &mdash; <a href="/" style="color:inherit;">return to portal</a></div>
  <div class="controls">
    <select id="currency"><option value="BTC">BTC</option><option value="ETH">ETH</option></select>
    <select id="instrument"><option value="BTC-PERPETUAL">BTC-PERPETUAL</option></select>
    <button id="btn-refresh">Refresh</button>
    <span id="last-updated" class="muted" style="font-size:0.78rem;"></span>
  </div>
  <div class="grid">
    <div class="card">
      <h2>Index Price</h2>
      <div class="stat" id="index-price">&mdash;</div>
      <div class="stat-label" id="index-label">BTC/USD</div>
    </div>
    <div class="card">
      <h2>Best Bid / Ask</h2>
      <div style="display:flex;gap:1.5rem;margin-top:0.25rem;">
        <div><div class="stat up" id="best-bid">&mdash;</div><div class="stat-label">Bid</div></div>
        <div><div class="stat down" id="best-ask">&mdash;</div><div class="stat-label">Ask</div></div>
      </div>
    </div>
    <div class="card"><h2>24h Stats</h2><div id="stats-24h" class="muted">Loading&hellip;</div></div>
  </div>
  <div class="card" style="margin-top:1rem;">
    <h2>Order Book (top 10)</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;">
      <div><table><thead><tr><th>Bid Price</th><th class="num">Size</th></tr></thead><tbody id="bids-body"></tbody></table></div>
      <div><table><thead><tr><th>Ask Price</th><th class="num">Size</th></tr></thead><tbody id="asks-body"></tbody></table></div>
    </div>
  </div>
  <div class="card" style="margin-top:1rem;">
    <h2>Recent Trades</h2>
    <table><thead><tr><th>Price</th><th class="num">Amount</th><th>Direction</th><th>Time</th></tr></thead>
    <tbody id="trades-body"></tbody></table>
  </div>
</div>
<script>
  const fmt = (n) => n == null ? "\u2014" : Number(n).toLocaleString("en-US",{maximumFractionDigits:2});
  const fmtTime = (ts) => new Date(ts).toLocaleTimeString();
  let _token = null;

  async function authFetch(url) {
    const r = await fetch(url, {headers:{Authorization:`Bearer ${_token}`}});
    if (r.status===401||r.status===403){window.location.href="/";return null;}
    return r.json();
  }

  async function loadInstruments() {
    const currency = document.getElementById("currency").value;
    const data = await authFetch(`/apps/stock/api/instruments?currency=${currency}&kind=future`);
    if (!data) return;
    const sel = document.getElementById("instrument");
    const prev = sel.value;
    sel.innerHTML = (data.instruments||[])
      .map(i=>`<option value="${i.instrument_name}"${i.instrument_name===prev?" selected":""}>${i.instrument_name}</option>`)
      .join("");
    if (!sel.value&&data.instruments?.length) sel.value=data.instruments[0].instrument_name;
  }

  async function refresh() {
    const instrument = document.getElementById("instrument").value;
    const currency = document.getElementById("currency").value.toLowerCase();
    const [ticker,book,trades,index] = await Promise.all([
      authFetch(`/apps/stock/api/ticker?instrument=${instrument}`),
      authFetch(`/apps/stock/api/order-book?instrument=${instrument}&depth=10`),
      authFetch(`/apps/stock/api/trades?instrument=${instrument}&count=20`),
      authFetch(`/apps/stock/api/index-price?index=${currency}_usd`),
    ]);
    if(!ticker) return;
    document.getElementById("index-price").textContent = "$"+fmt(index.index_price);
    document.getElementById("index-label").textContent = currency.toUpperCase()+"/USD index";
    document.getElementById("best-bid").textContent = "$"+fmt(ticker.best_bid_price);
    document.getElementById("best-ask").textContent = "$"+fmt(ticker.best_ask_price);
    const s=ticker.stats||{};
    document.getElementById("stats-24h").innerHTML=`
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;font-size:0.83rem;">
        <div><span class="muted">High</span> $${fmt(s.high)}</div>
        <div><span class="muted">Low</span> $${fmt(s.low)}</div>
        <div><span class="muted">Vol</span> ${fmt(s.volume)} ${currency.toUpperCase()}</div>
        <div><span class="muted">OI</span> ${fmt(ticker.open_interest)}</div>
      </div>`;
    document.getElementById("bids-body").innerHTML=(book.bids||[])
      .map(([p,sz])=>`<tr><td class="up">$${fmt(p)}</td><td class="num">${fmt(sz)}</td></tr>`).join("");
    document.getElementById("asks-body").innerHTML=(book.asks||[])
      .map(([p,sz])=>`<tr><td class="down">$${fmt(p)}</td><td class="num">${fmt(sz)}</td></tr>`).join("");
    document.getElementById("trades-body").innerHTML=(trades.trades||[])
      .map(t=>`<tr><td class="${t.direction==="buy"?"up":"down"}">$${fmt(t.price)}</td>
        <td class="num">${fmt(t.amount)}</td>
        <td class="${t.direction==="buy"?"up":"down"}">${t.direction}</td>
        <td class="muted">${fmtTime(t.timestamp)}</td></tr>`).join("");
    document.getElementById("last-updated").textContent="Updated "+new Date().toLocaleTimeString();
  }

  document.getElementById("currency").addEventListener("change",async()=>{await loadInstruments();await refresh();});
  document.getElementById("instrument").addEventListener("change",refresh);
  document.getElementById("btn-refresh").addEventListener("click",refresh);

  (async()=>{
    try{
      const client=await auth0.createAuth0Client({
        domain:"pezdev.us.auth0.com",clientId:"4X6INHXnVCqb4M1KqUTVK9vDBhzT0q5d",
        authorizationParams:{redirect_uri:window.location.origin,scope:"openid profile email"},
        cacheLocation:"localstorage",
      });
      if(!(await client.isAuthenticated())){window.location.href="/";return;}
      const claims=await client.getIdTokenClaims();
      if(!claims){window.location.href="/";return;}
      _token=claims.__raw;
      await loadInstruments();
      await refresh();
      setInterval(refresh,30000);
    }catch(e){document.getElementById("auth-error").style.display="";}
  })();
</script>
</body>
</html>"""

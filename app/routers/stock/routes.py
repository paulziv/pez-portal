"""Market Dashboard router — sanitized Deribit market data.

Shows public Deribit data only (instruments, tickers, order book,
recent trades). No account connections, no personal positions.
Personal trading data stays on zivnas behind VPN.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.auth import UserClaims, require_app

router = APIRouter(prefix="/apps/stock", tags=["stock"])

_require = require_app("stock")

DERIBIT_BASE = "https://www.deribit.com/api/v2"


# ── UI ────────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def ui(_user: UserClaims = Depends(_require)) -> str:
    """Serve the market dashboard single-page UI."""
    return _DASHBOARD_HTML


# ── Public Deribit proxy endpoints ────────────────────────────────────────────
# These are all public Deribit endpoints — no credentials required.
# The proxy lives here so we can add caching, rate limiting, or
# response shaping without touching the frontend.

async def _deribit_get(path: str, params: dict | None = None) -> dict:
    """Call a Deribit public endpoint and return the result payload."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{DERIBIT_BASE}/{path}", params=params or {})
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise HTTPException(status_code=502, detail=str(data["error"]))
        return data.get("result", data)


@router.get("/api/instruments")
async def get_instruments(
    currency: str = Query("BTC", description="BTC or ETH"),
    kind: str = Query("option", description="option, future, spot"),
    _user: UserClaims = Depends(_require),
) -> dict:
    """List active Deribit instruments for a currency/kind pair."""
    result = await _deribit_get(
        "public/get_instruments",
        {"currency": currency.upper(), "kind": kind, "expired": False},
    )
    return {"instruments": result}


@router.get("/api/ticker")
async def get_ticker(
    instrument: str = Query(..., description="e.g. BTC-PERPETUAL"),
    _user: UserClaims = Depends(_require),
) -> dict:
    """Get the latest ticker for an instrument."""
    return await _deribit_get("public/ticker", {"instrument_name": instrument})


@router.get("/api/order-book")
async def get_order_book(
    instrument: str = Query(..., description="e.g. BTC-PERPETUAL"),
    depth: int = Query(10, ge=1, le=20),
    _user: UserClaims = Depends(_require),
) -> dict:
    """Get order book depth for an instrument."""
    return await _deribit_get(
        "public/get_order_book",
        {"instrument_name": instrument, "depth": depth},
    )


@router.get("/api/index-price")
async def get_index_price(
    index: str = Query("btc_usd", description="e.g. btc_usd, eth_usd"),
    _user: UserClaims = Depends(_require),
) -> dict:
    """Get the current index price."""
    return await _deribit_get("public/get_index_price", {"index_name": index})


@router.get("/api/trades")
async def get_recent_trades(
    instrument: str = Query(..., description="e.g. BTC-PERPETUAL"),
    count: int = Query(20, ge=1, le=100),
    _user: UserClaims = Depends(_require),
) -> dict:
    """Get recent public trades for an instrument."""
    return await _deribit_get(
        "public/get_last_trades_by_instrument",
        {"instrument_name": instrument, "count": count},
    )


# ── Dashboard HTML ────────────────────────────────────────────────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Market Dashboard</title>
  <style>
    :root{--bg:#0f172a;--panel:#1e293b;--panel2:#273449;--text:#e2e8f0;
          --muted:#94a3b8;--accent:#38bdf8;--border:#334155;
          --ok:#34d399;--warn:#fbbf24;--err:#f87171;}
    *{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg);color:var(--text);min-height:100vh;}
    header{background:var(--panel);border-bottom:1px solid var(--border);
           padding:0.85rem 1.5rem;display:flex;align-items:center;
           justify-content:space-between;}
    header .logo{font-weight:700;font-size:1.1rem;color:var(--accent);}
    header .back{font-size:0.82rem;color:var(--muted);text-decoration:none;}
    header .back:hover{color:var(--accent);}
    .main{max-width:1200px;margin:0 auto;padding:1.5rem;}
    .controls{display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.5rem;align-items:center;}
    select,button{background:var(--panel2);color:var(--text);
                  border:1px solid var(--border);border-radius:6px;
                  padding:0.45rem 0.75rem;font-size:0.87rem;cursor:pointer;}
    button{background:var(--accent);color:#0f172a;font-weight:600;border-color:var(--accent);}
    button:hover{opacity:0.88;}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem;}
    .card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:1.25rem;}
    .card h2{font-size:0.78rem;text-transform:uppercase;letter-spacing:0.06em;
             color:var(--muted);margin-bottom:0.85rem;}
    .stat{font-size:1.6rem;font-weight:700;color:var(--accent);}
    .stat-label{font-size:0.78rem;color:var(--muted);margin-top:0.2rem;}
    table{width:100%;border-collapse:collapse;font-size:0.82rem;}
    th{text-align:left;padding:0.4rem 0.5rem;color:var(--muted);
       border-bottom:1px solid var(--border);font-weight:500;}
    td{padding:0.38rem 0.5rem;border-bottom:1px solid rgba(51,65,85,0.5);}
    .num{text-align:right;}
    .up{color:var(--ok);}
    .down{color:var(--err);}
    .spinner{display:inline-block;width:1rem;height:1rem;
             border:2px solid var(--border);border-top-color:var(--accent);
             border-radius:50%;animation:spin 0.8s linear infinite;}
    @keyframes spin{to{transform:rotate(360deg);}}
    .muted{color:var(--muted);}
  </style>
</head>
<body>
<header>
  <span class="logo">📈 Market Dashboard</span>
  <a class="back" href="/">← Portal</a>
</header>
<div class="main">
  <div class="controls">
    <select id="currency">
      <option value="BTC">BTC</option>
      <option value="ETH">ETH</option>
    </select>
    <select id="instrument">
      <option value="BTC-PERPETUAL">BTC-PERPETUAL</option>
    </select>
    <button id="btn-refresh">Refresh</button>
    <span id="last-updated" class="muted" style="font-size:0.78rem;"></span>
  </div>

  <div class="grid">
    <!-- Index price -->
    <div class="card">
      <h2>Index Price</h2>
      <div class="stat" id="index-price">—</div>
      <div class="stat-label" id="index-label">BTC/USD</div>
    </div>
    <!-- Best bid/ask -->
    <div class="card">
      <h2>Best Bid / Ask</h2>
      <div style="display:flex;gap:1.5rem;margin-top:0.25rem;">
        <div>
          <div class="stat up" id="best-bid">—</div>
          <div class="stat-label">Bid</div>
        </div>
        <div>
          <div class="stat down" id="best-ask">—</div>
          <div class="stat-label">Ask</div>
        </div>
      </div>
    </div>
    <!-- 24h stats -->
    <div class="card">
      <h2>24h Stats</h2>
      <div id="stats-24h" class="muted">Loading…</div>
    </div>
  </div>

  <!-- Order book -->
  <div class="card" style="margin-top:1rem;">
    <h2>Order Book (top 10)</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;">
      <div>
        <table>
          <thead><tr><th>Bid Price</th><th class="num">Size</th></tr></thead>
          <tbody id="bids-body"></tbody>
        </table>
      </div>
      <div>
        <table>
          <thead><tr><th>Ask Price</th><th class="num">Size</th></tr></thead>
          <tbody id="asks-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Recent trades -->
  <div class="card" style="margin-top:1rem;">
    <h2>Recent Trades</h2>
    <table>
      <thead><tr><th>Price</th><th class="num">Amount</th><th>Direction</th><th>Time</th></tr></thead>
      <tbody id="trades-body"></tbody>
    </table>
  </div>
</div>

<script>
  const fmt = (n) => n == null ? "—" : Number(n).toLocaleString("en-US", {maximumFractionDigits: 2});
  const fmtTime = (ts) => new Date(ts).toLocaleTimeString();

  async function loadInstruments() {
    const currency = document.getElementById("currency").value;
    const r = await fetch(`/apps/stock/api/instruments?currency=${currency}&kind=future`);
    const data = await r.json();
    const sel = document.getElementById("instrument");
    const prev = sel.value;
    sel.innerHTML = (data.instruments || [])
      .map(i => `<option value="${i.instrument_name}"${i.instrument_name===prev?" selected":""}>${i.instrument_name}</option>`)
      .join("");
    if (!sel.value && data.instruments?.length) sel.value = data.instruments[0].instrument_name;
  }

  async function refresh() {
    const instrument = document.getElementById("instrument").value;
    const currency = document.getElementById("currency").value.toLowerCase();

    const [tickerResp, bookResp, tradesResp, indexResp] = await Promise.all([
      fetch(`/apps/stock/api/ticker?instrument=${instrument}`).then(r=>r.json()),
      fetch(`/apps/stock/api/order-book?instrument=${instrument}&depth=10`).then(r=>r.json()),
      fetch(`/apps/stock/api/trades?instrument=${instrument}&count=20`).then(r=>r.json()),
      fetch(`/apps/stock/api/index-price?index=${currency}_usd`).then(r=>r.json()),
    ]);

    // Index price
    document.getElementById("index-price").textContent = "$" + fmt(indexResp.index_price);
    document.getElementById("index-label").textContent = currency.toUpperCase() + "/USD index";

    // Bid/ask
    document.getElementById("best-bid").textContent = "$" + fmt(tickerResp.best_bid_price);
    document.getElementById("best-ask").textContent = "$" + fmt(tickerResp.best_ask_price);

    // 24h stats
    const s = tickerResp.stats || {};
    document.getElementById("stats-24h").innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;font-size:0.83rem;">
        <div><span class="muted">High</span> $${fmt(s.high)}</div>
        <div><span class="muted">Low</span>  $${fmt(s.low)}</div>
        <div><span class="muted">Vol</span>  ${fmt(s.volume)} ${currency.toUpperCase()}</div>
        <div><span class="muted">OI</span>   ${fmt(tickerResp.open_interest)}</div>
      </div>`;

    // Order book
    const bids = bookResp.bids || [];
    const asks = bookResp.asks || [];
    document.getElementById("bids-body").innerHTML =
      bids.map(([p,s]) => `<tr><td class="up">$${fmt(p)}</td><td class="num">${fmt(s)}</td></tr>`).join("");
    document.getElementById("asks-body").innerHTML =
      asks.map(([p,s]) => `<tr><td class="down">$${fmt(p)}</td><td class="num">${fmt(s)}</td></tr>`).join("");

    // Trades
    const trades = (tradesResp.trades || []);
    document.getElementById("trades-body").innerHTML =
      trades.map(t => `<tr>
        <td class="${t.direction==="buy"?"up":"down"}">$${fmt(t.price)}</td>
        <td class="num">${fmt(t.amount)}</td>
        <td class="${t.direction==="buy"?"up":"down"}">${t.direction}</td>
        <td class="muted">${fmtTime(t.timestamp)}</td>
      </tr>`).join("");

    document.getElementById("last-updated").textContent =
      "Updated " + new Date().toLocaleTimeString();
  }

  document.getElementById("currency").addEventListener("change", async () => {
    await loadInstruments();
    await refresh();
  });
  document.getElementById("instrument").addEventListener("change", refresh);
  document.getElementById("btn-refresh").addEventListener("click", refresh);

  // Boot
  loadInstruments().then(refresh);
  setInterval(refresh, 30000);
</script>
</body>
</html>"""

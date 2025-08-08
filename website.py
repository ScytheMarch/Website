from __future__ import annotations

import os
import time
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Dict, List, Tuple

import requests
from flask import Flask, request, render_template_string


app = Flask(__name__)


# Cryptos to display by default (must be symbols used by Coinbase rates API)
SUPPORTED_CRYPTOS: List[str] = [
    "BTC",
    "ETH",
    "SOL",
    "USDC",
    "USDT",
    "XRP",
    "ADA",
    "DOGE",
    "LTC",
]


# Simple in-memory cache to reduce API calls/rate limits
_rates_cache: Dict[str, object] = {"timestamp": 0.0, "rates": {}}
_CACHE_TTL_SECONDS = 60


def fetch_usd_exchange_rates() -> Dict[str, Decimal]:
    """Fetch 1 USD -> crypto rates from Coinbase public API.

    Returns a mapping like {"BTC": Decimal("0.0000..."), ...}
    """
    now = time.time()
    if (now - float(_rates_cache.get("timestamp", 0))) < _CACHE_TTL_SECONDS:
        return _rates_cache["rates"]  # type: ignore[return-value]

    url = "https://api.coinbase.com/v2/exchange-rates?currency=USD"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    raw_rates: Dict[str, str] = data.get("data", {}).get("rates", {})

    rates: Dict[str, Decimal] = {}
    for symbol, value in raw_rates.items():
        try:
            rates[symbol.upper()] = Decimal(value)
        except (InvalidOperation, TypeError):
            # Skip unparsable values
            continue

    _rates_cache["timestamp"] = now
    _rates_cache["rates"] = rates
    return rates


def format_crypto_amount(symbol: str, amount: Decimal) -> str:
    """Format crypto amount with reasonable decimals per asset."""
    symbol = symbol.upper()
    # Default precision
    precision = 8
    if symbol in {"USDC", "USDT"}:
        precision = 2
    elif symbol in {"XRP", "ADA", "DOGE", "SOL", "LTC"}:
        precision = 4

    quant = Decimal(10) ** -precision
    return f"{amount.quantize(quant, rounding=ROUND_DOWN):f}"


TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>USD ↔ Crypto Price Comparator</title>
    <style>
      :root {
        --bg: #0f172a;
        --panel: #111827;
        --text: #e5e7eb;
        --muted: #9ca3af;
        --accent: #22c55e;
        --border: #1f2937;
      }
      html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text); font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Noto Sans, Ubuntu, Cantarell, Helvetica Neue, Arial, "Apple Color Emoji", "Segoe UI Emoji"; }
      .container { max-width: 960px; margin: 0 auto; padding: 32px 16px; }
      .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.25); }
      h1 { margin: 0 0 16px 0; font-size: 24px; }
      p.muted { color: var(--muted); margin-top: 4px; }
      form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
      .full { grid-column: 1 / -1; }
      label { display: block; font-weight: 600; margin-bottom: 6px; }
      input[type="text"], input[type="number"], select { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); background: #0b1220; color: var(--text); }
      button { background: var(--accent); color: #052e16; font-weight: 700; padding: 12px 16px; border: 0; border-radius: 10px; cursor: pointer; }
      button:hover { filter: brightness(1.05); }
      table { width: 100%; border-collapse: collapse; margin-top: 18px; }
      th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); }
      th { color: var(--muted); font-weight: 600; }
      .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: #0b1220; border: 1px solid var(--border); font-size: 12px; color: var(--muted); }
      .footer { color: var(--muted); font-size: 12px; margin-top: 18px; }
      .error { color: #fda4af; }
      .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
      .chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 999px; background: #0b1220; border: 1px solid var(--border); }
    </style>
  </head>
  <body>
    <div class="container">
      <div class="card">
        <h1>USD ↔ Crypto Price Comparator</h1>
        <p class="muted">Enter an item and a USD price. We'll show what that price equals in popular cryptocurrencies using live exchange rates.</p>

        {% if error %}
          <p class="error">{{ error }}</p>
        {% endif %}

        <form method="post">
          <div>
            <label for="item">Item name</label>
            <input id="item" name="item" type="text" placeholder="e.g., Headphones" value="{{ item or '' }}" required />
          </div>
          <div>
            <label for="price">USD price</label>
            <input id="price" name="price" type="number" step="0.01" min="0" placeholder="e.g., 129.99" value="{{ price or '' }}" required />
          </div>
          <div class="full">
            <label for="cryptos">Cryptocurrencies</label>
            <select id="cryptos" name="cryptos" multiple size="5">
              {% for sym in all_symbols %}
                <option value="{{ sym }}" {% if sym in selected_symbols %}selected{% endif %}>{{ sym }}</option>
              {% endfor %}
            </select>
            <p class="muted">Hold Ctrl/Cmd to select multiple. Defaults to a curated list.</p>
          </div>
          <div class="full">
            <button type="submit">Compare</button>
          </div>
        </form>

        {% if results %}
          <h2 style="margin-top: 18px;">Results</h2>
          <div class="grid">
            <div class="chip"><strong>Item:</strong> <span>{{ item }}</span></div>
            <div class="chip"><strong>USD:</strong> <span>${{ price }}</span></div>
            <div class="chip"><strong>Live:</strong> <span class="badge">Coinbase rates</span></div>
          </div>

          <table>
            <thead>
              <tr>
                <th>Crypto</th>
                <th>1 USD =</th>
                <th>{{ price }} USD =</th>
              </tr>
            </thead>
            <tbody>
              {% for row in results %}
                <tr>
                  <td><strong>{{ row.symbol }}</strong></td>
                  <td>{{ row.usd_rate }}</td>
                  <td>{{ row.item_amount }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>

          <p class="footer">Tip: Stablecoins like USDC/USDT should track USD ~1:1. Network fees or merchant fees are not included.</p>
        {% endif %}
      </div>
    </div>
  </body>
  </html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    error: str | None = None
    results: List[Dict[str, str]] = []
    item = ""
    price_str = ""

    selected_symbols = SUPPORTED_CRYPTOS.copy()
    if request.method == "POST":
        item = (request.form.get("item") or "").strip()
        price_str = (request.form.get("price") or "").strip()

        # Parse multi-select; if provided, use it, otherwise keep defaults
        provided = request.form.getlist("cryptos")
        if provided:
            selected_symbols = [s.upper() for s in provided]

        try:
            usd_price = Decimal(price_str)
            if usd_price < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            error = "Please enter a valid non-negative USD price."
        else:
            try:
                rates = fetch_usd_exchange_rates()
            except Exception as exc:  # broad but we show a friendly message
                error = f"Failed to fetch live rates: {exc}"
            else:
                # Build results for selected symbols that exist in rates
                for sym in selected_symbols:
                    rate = rates.get(sym)
                    if rate is None:
                        continue
                    amount = (usd_price * rate)
                    results.append(
                        {
                            "symbol": sym,
                            "usd_rate": format_crypto_amount(sym, rate),
                            "item_amount": format_crypto_amount(sym, amount),
                        }
                    )

                # Sort by symbol for stable ordering
                results.sort(key=lambda r: r["symbol"])

    return render_template_string(
        TEMPLATE,
        error=error,
        results=results,
        item=item or None,
        price=price_str or None,
        all_symbols=SUPPORTED_CRYPTOS,
        selected_symbols=selected_symbols,
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    # Configure host/port via environment for container/platform deploys
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)



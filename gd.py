from dotenv import load_dotenv
import os
import requests
import pandas as pd
import platform
from flask import Flask, request

# Load environment variables from .env file
load_dotenv()

# ✅ Use token and API key from environment
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
api_key = os.getenv("TWELVE_DATA_API_KEY")

app = Flask(__name__)
symbol = "XAU/USD"

# ✅ Add this health check route for Render
@app.route("/", methods=["GET"])
def home():
    return "Bot is running!"

if platform.system() == "Windows":
    import winsound

def send_telegram_message(message, chat_id):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    requests.post(url, data=payload)

def fetch_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={api_key}"
    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        print(f"❌ Error fetching {interval} data: {data}")
        return None

    df = pd.DataFrame(data["values"])
    numeric_cols = ['open', 'high', 'low', 'close']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].astype(float)

    return df[::-1].reset_index(drop=True)

def fetch_live_price(symbol):
    url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={api_key}"
    response = requests.get(url)
    data = response.json()

    if "price" in data:
        return float(data["price"])
    else:
        print(f"❌ Error fetching live price for {symbol}: {data}")
        return None

def analyze_data(df, interval):
    df["MA5"] = df["close"].rolling(window=5).mean()
    df["MA20"] = df["close"].rolling(window=20).mean()

    latest_close = df["close"].iloc[-1]
    previous_close = df["close"].iloc[-2]

    market_trend = "Bullish" if latest_close > previous_close else "Bearish"
    ma_signal = "BUY" if df["MA5"].iloc[-1] > df["MA20"].iloc[-1] else "SELL"

    df["H-L"] = df["high"] - df["low"]
    df["H-PC"] = abs(df["high"] - df["close"].shift(1))
    df["L-PC"] = abs(df["low"] - df["close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(window=14).mean()
    atr = df["ATR"].iloc[-1]

    risk = 1.5
    if ma_signal == "BUY":
        sl = latest_close - atr * risk
        tp = latest_close + atr * risk
    else:
        sl = latest_close + atr * risk
        tp = latest_close - atr * risk

    if ma_signal == "BUY" and sl > tp:
        sl, tp = tp, sl
    elif ma_signal == "SELL" and sl < tp:
        sl, tp = tp, sl

    support_level = latest_close - atr
    resistance_level = latest_close + atr

    return f"⏱ Timeframe: {interval}\n" \
           f"📈 Trend: {market_trend}\n" \
           f"📊 Signal: {ma_signal}\n" \
           f"🔎 ATR: {atr:.2f}\n" \
           f"💡 SL: {sl:.2f} | TP: {tp:.2f}\n" \
           f"🔒 Support: {support_level:.2f} | 🔓 Resistance: {resistance_level:.2f}\n"

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if "message" in data:
        message = data['message']['text']
        chat_id = data['message']['chat']['id']
        user_name = data['message']['chat'].get('username') or data['message']['chat'].get('first_name', 'Trader')

        live_price = fetch_live_price(symbol)
        live_price_message = f"💰 Live XAU/USD Price: {live_price:.2f}" if live_price else "❌ Error fetching live price."

        if message == '/signals':
            intervals = ["1h", "30min", "15min", "5min"]
            full_message = f"📩 Hello {user_name}!\n📊 Multi-Timeframe Signal Summary:\n\n{live_price_message}\n\n"
            for interval in intervals:
                df = fetch_data(symbol, interval)
                if df is not None:
                    analysis = analyze_data(df, interval)
                    full_message += analysis + "\n" + ("─" * 40) + "\n"
            send_telegram_message(full_message.strip(), chat_id)

        elif message == '/long_term':
            intervals = ["4h", "8h", "12h", "1day"]
            full_message = f"📩 Hello {user_name}!\n📊 Long-Term Signal Summary:\n\n{live_price_message}\n\n"
            for interval in intervals:
                df = fetch_data(symbol, interval)
                if df is not None:
                    analysis = analyze_data(df, interval)
                    full_message += analysis + "\n" + ("─" * 40) + "\n"
            send_telegram_message(full_message.strip(), chat_id)

        elif message == '/status':
            df = fetch_data(symbol, "1h")
            if df is not None:
                response = analyze_data(df, "1h")
                send_telegram_message(f"📩 Hello {user_name}!\n{live_price_message}\n{response}", chat_id)

        elif message == '/latest_signal':
            df = fetch_data(symbol, "5min")
            if df is not None:
                response = analyze_data(df, "5min")
                send_telegram_message(f"📩 Hello {user_name}!\n{live_price_message}\n{response}", chat_id)

        else:
            send_telegram_message(
                "🤖 Unknown command.\nTry /signals, /status, /latest_signal, or /long_term.",
                chat_id
            )

    return '', 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)

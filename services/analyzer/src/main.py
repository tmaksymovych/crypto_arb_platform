import asyncio
import json
import logging
import os
import redis.asyncio as redis
import time
import aiohttp
from dotenv import load_dotenv
from common.schemas import Ticker

load_dotenv() 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("Analyzer")

REDIS_HOST = os.getenv('REDIS_HOST', '127.0.0.1')

TG_TOKEN = os.getenv("TG_BOT_TOKEN")
raw_ids = os.getenv("CHAT_IDS", "")
test_id = os.getenv("MY_TG_ID", "")
CHAT_IDS = [x.strip() for x in test_id.split(",") if x.strip()]

logger.info(f"Загруженные ID: {CHAT_IDS}")

if not TG_TOKEN or not CHAT_IDS:
    logger.error("Критическая ошибка: TG_BOT_TOKEN или MY_TG_ID не найдены в переменных окружения!")

async def send_telegram(message):
    if not TG_TOKEN:
        return
    async with aiohttp.ClientSession() as session:
        for chatId in CHAT_IDS:

            cleanId = str(chatId).strip()
            if not cleanId:
                continue

            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            payload = {
                "chat_id":chatId,
                "text":message,
                "parse_mode":"HTML"
            }
            try:
                async with session.post(url, json=payload) as response:
                        if response.status != 200:
                            logger.error(f"ошибка отправки в TG: {await response.text()}")
                        else:
                            logger.info(f"Успешно отправлен в чат {chatId}")
            except Exception as e:
                logger.error(f"TG Connection Error: {e}")




LEVERAGE = 6    # Arbitrage threshold in percentage
THRESHOLD = 0.1   # Minimum spread percentage to consider for arbitrage
ESTIMATED_FEE_TOTAL = 0.22  # Estimated total fees for arbitrage
MIN_VOLUME_USDT = 5000000.0 # 5 million USD minimum volume to consider for arbitrage
SIGNAL_TTL = 5
BLACKLIST = ['U/USDT']

def calculate_arbitrage_opportunity(symbol, buy_exchange, sell_exchange, long_ticker, short_ticker):
    long_price = long_ticker.ask
    short_price = short_ticker.bid

    if long_price == 0 or short_price == 0:
        return
    
   # 1. "Грязный" спред в процентах
    spread = ((short_price - long_price) / long_price) * 100
    # 2. Расчет чистой прибыли
    # Сколько мы отдадим бирже за круг (4 сделки)
    fees_cost = ESTIMATED_FEE_TOTAL # 0.22%
    # Чистый спред (Spread - Fees)
    net_spread = spread - fees_cost
    # 3. ROE (Прибыль на вложенные свои деньги с учетом плеча)
    # Пример: Спред 1%, Комиссия 0.22%, Чистыми 0.78%. Плечо x6.
    # ROE = 0.78% * 6 = 4.68%
    roe = net_spread * LEVERAGE

    # Если спред меньше порога (0.6%), даже не смотрим, чтобы не кормить биржу
    if net_spread < THRESHOLD or net_spread > 50:  # И добавляем верхнюю границу, чтобы отсеять аномалии
        return None

    return {
            "symbol": symbol,
            "buy_exchange": buy_exchange,
            "sell_exchange": sell_exchange,
            "long_price": long_price,
            "short_price": short_price,
            "spread": spread,
            "profit": net_spread,
            "roe": roe
        }
     

async def main():
    r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
    logger.info("Redis connected, starting analyzer")
    logger.info(f"Threshold={THRESHOLD}% TTL={SIGNAL_TTL/60:.1f}min")

    while True:
        try:
            keys = await r.keys("ticker:*:*")

            market_snapshot = {}

            for key in keys:
                parts = key.split(":")
                # РЕШЕНИЕ: Разрешаем и 3, и 4 части
                if len(parts) < 3: 
                    continue
                exchange_id = parts[1]
                # РЕШЕНИЕ: Всегда берем символ из 3-й части, игнорируя хвосты
                symbol = parts[2] 
                
                if symbol in BLACKLIST:
                    continue
                # Дальше твой код без изменений...

                raw_data = await r.get(key)
                if raw_data:
                    if symbol not in market_snapshot:
                        market_snapshot[symbol] = {}
                    try:
                        market_snapshot[symbol][exchange_id] = Ticker.model_validate_json(raw_data)
                    except:
                        continue

            for symbol, exchanges in market_snapshot.items():
                exchanges_names = list(exchanges.keys())
                if len(exchanges_names) < 2:
                    continue

                candidates = []
                for i in range(len(exchanges_names)):
                    for j in range(i + 1, len(exchanges_names)):
                        ex1 = exchanges_names[i]
                        ex2 = exchanges_names[j]
                        ticker1 = exchanges[ex1]
                        ticker2 = exchanges[ex2]
                        
                        vol1 = ticker1.quoteVolume
                        if vol1 <= 0:
                            vol1 = ticker1.volume * ticker1.bid if ticker1.volume < 1000000 else ticker1.volume
                        vol2 = ticker2.quoteVolume
                        if vol2 <= 0:
                            vol2 = ticker2.volume * ticker2.bid if ticker2.volume < 1000000 else ticker2.volume
                        if vol1 < MIN_VOLUME_USDT or vol2 < MIN_VOLUME_USDT:
                            continue

                        var1 = calculate_arbitrage_opportunity(symbol, ex1, ex2, ticker1, ticker2)
                        if var1:
                            candidates.append(var1)
                        var2 = calculate_arbitrage_opportunity(symbol, ex2, ex1, ticker2, ticker1)
                        if var2:
                            candidates.append(var2)
                
                if not candidates:
                    continue

                best_opportunity = max(candidates, key=lambda x: x["profit"])
                cooldown_key = f"cooldown:{symbol}"
                timer_key = f"timer:{symbol}"

                if await r.exists(cooldown_key):
                    continue
                
                start_time = await r.get(timer_key)
                if not start_time:
                    await r.set(timer_key, time.time(), ex=30)
                    logging.info(f"NEW SIGNAL {symbol} Profit: {best_opportunity['profit']:.2f}% ROE: {best_opportunity['roe']:.2f}%")
                else:
                    duration = time.time() - float(start_time)
                    if duration >= SIGNAL_TTL:
                        logger.info(f"CONFIRMED {symbol} Profit: {best_opportunity['profit']:.2f}% ROE: {best_opportunity['roe']:.2f}%")
                        msg = (
                                f"🚀 <b>FUTURES ARB (x{LEVERAGE})</b>\n\n"
                                f"💎 <b>{symbol}</b>\n"
                                f"📉 <b>SHORT: {best_opportunity['sell_exchange'].upper()}</b> ({best_opportunity['short_price']})\n"
                                f"📈 <b>LONG:  {best_opportunity['buy_exchange'].upper()}</b> ({best_opportunity['long_price']})\n\n"     
                                f"📊 Raw Spread: {best_opportunity['spread']:.2f}%\n"
                                f"💸 Fees: -{ESTIMATED_FEE_TOTAL}%\n"
                                f"🟢 <b>Net Spread: {best_opportunity['profit']:.2f}%</b>\n\n"
                                
                                f"🔥 <b>Est. ROE: {best_opportunity['roe']:.2f}%</b> (Net Profit)\n"
                                f"⏱ Duration: {duration:.1f}s"
                            )
                        await send_telegram(msg)
                        await r.set(cooldown_key, "sent", ex=1800)  # Cooldown 5 minutes
                        await r.delete(timer_key)

            await asyncio.sleep(1)  # small pause to not overload Redis

        except Exception as e:
            logger.error(f"Main loop error: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
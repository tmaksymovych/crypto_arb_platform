from common.mapper import normalize_ticker


# Тест 1: Обычный случай (Binance)
print(f"Binance BTC/USDT -> {normalize_ticker('BTC/USDT', 'binance')}")

# Тест 2: Проблемный случай (Gate)
print(f"Gate BCC/USDT -> {normalize_ticker('BCC/USDT', 'gate')}")

# Тест 3: Kraken (XBT)
print(f"Kraken XBT/USD -> {normalize_ticker('XBT/USD', 'kraken')}")

# Тест 4: Неизвестная пара
print(f"Gate UNKNOWN/USDT -> {normalize_ticker('UNKNOWN/USDT', 'gate')}")
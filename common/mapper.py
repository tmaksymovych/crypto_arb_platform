"""
Модуль для нормализации тикеров.
Решает проблему разных названий одного актива на разных биржах.
"""



EXCHANGE_MAPPER = {
    'gate':{
        'BCC': 'BCH',
        'BCHSV': 'BSV',
    },
    'kraken':{
        'XBT': 'BTC',
        'XDG': 'DOGE',
    },
    'poloniex':{
        'STR':'XLM'
    }
}

def normalize_symbol(symbol: str, exchange_id: str) -> str:

    if '/' not in symbol:
        return symbol

    try:
        base, quote = symbol.split('/')
    except ValueError:
        return symbol

    mapping = EXCHANGE_MAPPER.get(exchange_id.lower(), {})

    normalized_base = mapping.get(base, base)
    normalized_quote = mapping.get(quote, quote)

    return f"{normalized_base}/{normalized_quote}"
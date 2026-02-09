# Crypto Arbitrage Platform 🚀

Персональная высокопроизводительная система для мониторинга межбиржевого арбитража в реальном времени.

## 📌 Описание
Система отслеживает ценовые аномалии между биржами (на данный момент **Binance** и **Bybit**). Ключевой особенностью является фильтрация "шума" с помощью **правила 30 минут**: сигнал считается валидным только в том случае, если профит удерживается на уровне выше заданного порога непрерывно в течение получаса.

## 🏗 Архитектура
Проект построен на микросервисной архитектуре с использованием Docker:
* **Collector (Binance/Bybit):** Собирает тикеры (Ask/Bid/Volume) через CCXT и записывает в Redis.
* **Redis:** Высокоскоростное хранилище данных (In-memory DB).
* **Analyzer:** Мозг системы. Сравнивает цены, управляет таймерами и находит профитные связки.



## 🛠 Технологический стек
* **Language:** Python 3.10+ (Asyncio)
* **Libraries:** CCXT, Pydantic, Redis-py
* **Infra:** Docker, Redis
* **VCS:** Git

## 🚀 Быстрый старт

### 1. Подготовка окружения
Убедитесь, что у вас установлены Docker и Docker Compose.

```bash
# Клонировать репозиторий
git clone [https://github.com/tmaksimovych/crypto_arb_platform.git](https://github.com/tmaksimovych/crypto_arb_platform.git)
cd crypto_arb_platform

# Настройка виртуального окружения
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import re
from datetime import datetime, timedelta
from prophet import Prophet
import xml.etree.ElementTree as ET
@st.cache_data(ttl=3600)
def get_currency_history(base_currency, target_currency='RUB', days=365):
    """
    Получает исторические курсы валюты через Frankfurter API.
    base_currency: USD, EUR, CNY и т.д.
    target_currency: RUB (по умолчанию)
    days: количество дней назад
    Возвращает DataFrame с колонками Date и Close (курс).
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        url = "https://api.frankfurter.app/timeseries"
        params = {
            'from': base_currency,
            'to': target_currency,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d')
        }
        response = requests.get(url, params=params)
        if response.status_code != 200:
            st.error(f"Frankfurter API вернул ошибку {response.status_code}: {response.text}")
            return None
        data = response.json()
        if 'rates' not in data:
            st.error("Нет данных о курсах в ответе Frankfurter")
            return None
        rates = data['rates']
        # Преобразуем в DataFrame
        df = pd.DataFrame.from_dict(rates, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        # Переименовываем колонку target_currency в 'Close'
        df = df.rename(columns={target_currency: 'Close'})
        df['Date'] = df.index
        df = df[['Date', 'Close']]
        return df
    except Exception as e:
        st.error(f"Ошибка загрузки истории валют: {e}")
        return None

# ================= НАСТРОЙКИ СТРАНИЦЫ =================
st.set_page_config(page_title="Финансовый ассистент", layout="wide")
st.title("📊 Смарт-Ассистент для РФ")

# ================= КУРСЫ ВАЛЮТ (ЦБ РФ) =================
CURRENCY_TICKERS = {'USD', 'EUR', 'CNY', 'GBP', 'JPY', 'CHF'}

@st.cache_data(ttl=3600)
def get_cbr_currency(currency_code):
    """Курс валюты от ЦБ РФ по коду (USD, EUR, CNY)"""
    url = "http://www.cbr.ru/scripts/XML_daily.asp"
    try:
        response = requests.get(url)
        response.encoding = 'windows-1251'
        root = ET.fromstring(response.text)
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode').text
            if char_code == currency_code:
                value = valute.find('Value').text.replace(',', '.')
                return float(value)
        return None
    except Exception as e:
        st.error(f"Ошибка загрузки курса ЦБ: {e}")
        return None

# Отображаем в боковой панели
st.sidebar.header("💱 Курсы валют (ЦБ РФ)")
usd = get_cbr_currency("USD")
eur = get_cbr_currency("EUR")
cny = get_cbr_currency("CNY")
if usd: st.sidebar.metric("🇺🇸 Доллар США", f"{usd:.4f} ₽")
else: st.sidebar.warning("Не удалось загрузить курс USD")
if eur: st.sidebar.metric("🇪🇺 Евро", f"{eur:.4f} ₽")
else: st.sidebar.warning("Не удалось загрузить курс EUR")
if cny: st.sidebar.metric("🇨🇳 Китайский юань", f"{cny:.4f} ₽")
else: st.sidebar.warning("Не удалось загрузить курс CNY")

st.markdown("Анализ акций РФ/США, облигаций, криптовалют, металлов и валют. Портфель и прогноз с учетом сезонности.")

# ================= ФУНКЦИЯ ДЛЯ РОССИЙСКИХ АКЦИЙ (MOEX) =================
@st.cache_data(ttl=3600)
def get_moex_data(ticker, period_days=365):
    """Загружает исторические данные с Мосбиржи для акций и облигаций"""
    try:
        end = datetime.now()
        start = end - timedelta(days=period_days)
        url = f'https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json'
        params = {
            'from': start.strftime('%Y-%m-%d'),
            'till': end.strftime('%Y-%m-%d'),
            'interval': 24,
            'iss.only': 'candles'
        }
        r = requests.get(url, params=params).json()
        if 'candles' not in r or 'data' not in r['candles'] or not r['candles']['data']:
            return None
        candles = r['candles']['data']
        columns = r['candles']['columns']
        df = pd.DataFrame(candles, columns=columns)
        df = df[['begin', 'open', 'close', 'high', 'low', 'volume']]
        df.rename(columns={'begin': 'Date', 'open': 'Open', 'close': 'Close', 'high': 'High', 'low': 'Low', 'volume': 'Volume'}, inplace=True)
        df['Date'] = pd.to_datetime(df['Date'])
        df.sort_values('Date', inplace=True)
        return df
    except:
        return None

# ================= ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ТЕКУЩЕЙ ЦЕНЫ (УНИВЕРСАЛЬНАЯ) =================
@st.cache_data(ttl=300)
def get_live_price(ticker):
    """Текущая цена через Yahoo Finance (для акций США, крипты, металлов)"""
    try:
        df = yf.download(ticker, period="5d", progress=False)
        if df.empty:
            return 0.0
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        val = df['Close'].iloc[-1]
        return float(val) if not pd.isna(val) else 0.0
    except:
        return 0.0

# ================= ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ АКТУАЛЬНЫХ ОФЗ =================
@st.cache_data(ttl=3600)
def get_active_ofz(limit=5):
    """
    Получает список актуальных ОФЗ (торгуемых) с Мосбиржи.
    Возвращает список словарей: {'ticker': 'SU...', 'name': 'ОФЗ ...'}
    """
    try:
        # Запрос к Мосбирже для получения списка облигаций с фильтром по типу 'ОФЗ'
        url = 'https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json'
        params = {
            'iss.only': 'securities',
            'securities.columns': 'SECID,SHORTNAME,REGNUMBER,ISIN,STATUS,LOTVALUE,COUPONPERCENT,COUPONFREQUENCY,MATDATE',
            'q.type': '2'  # фильтр по типу: государственные
        }
        r = requests.get(url, params=params).json()
        data = r['securities']['data']
        cols = r['securities']['columns']
        df_bonds = pd.DataFrame(data, columns=cols)
        
        # Фильтруем только ОФЗ (по короткому имени или по ISIN)
        ofz_mask = df_bonds['SHORTNAME'].str.startswith('ОФЗ') | df_bonds['SHORTNAME'].str.contains('ОФЗ')
        df_ofz = df_bonds[ofz_mask].copy()
        
        # Исключаем погашенные (STATUS != 'A' – активные)
        df_ofz = df_ofz[df_ofz['STATUS'] == 'A']
        
        # Убираем бумаги с истекшим сроком (MATDATE < сегодня)
        df_ofz['MATDATE'] = pd.to_datetime(df_ofz['MATDATE'])
        df_ofz = df_ofz[df_ofz['MATDATE'] > datetime.now()]
        
        # Сортируем по ликвидности (LOTVALUE – объём лота) или просто берём первые
        df_ofz = df_ofz.sort_values('LOTVALUE', ascending=False).head(limit)
        
        # Формируем список
        result = []
        for _, row in df_ofz.iterrows():
            ticker = row['SECID']
            name = row['SHORTNAME'] if pd.notna(row['SHORTNAME']) else f"ОФЗ {ticker}"
            result.append({'ticker': ticker, 'name': name})
        return result
    except Exception as e:
        st.error(f"Не удалось загрузить список ОФЗ: {e}")
        # Возвращаем запасной вариант, если API не работает
        return [{'ticker': 'SU26238RMFS4', 'name': 'ОФЗ 26238'}]

# ================= ДИНАМИЧЕСКАЯ БАЗА АКТИВОВ =================
@st.cache_data(ttl=3600)
def build_assets_db():
    """
    Формирует базу активов:
    - Акции РФ (SBER, LKOH, GAZP, YNDX) – проверяем доступность через MOEX, иначе через Yahoo
    - Акции США (AAPL, NVDA, TSLA) – через Yahoo
    - Индексы, криптовалюты, металлы, валюты – статические
    - ОФЗ – динамически получаем актуальные
    """
    assets = {}
    
    # ---- Акции РФ (с проверкой доступности) ----
    russian_tickers = {
        "Сбербанк": "SBER",
        "Лукойл": "LKOH",
        "Газпром": "GAZP",
        "Яндекс": "YNDX"
    }
    for name, ticker in russian_tickers.items():
        # Проверяем, доступен ли тикер на Мосбирже
        test_data = get_moex_data(ticker, period_days=1)
        if test_data is not None and not test_data.empty:
            assets[f"{name} ({ticker})"] = {
                "ticker": ticker,
                "type": "Акция РФ",
                "risk": "Низкий" if name in ["Сбербанк", "Газпром"] else "Средний",
                "market": "Мосбиржа",
                "currency": "RUB"
            }
        else:
            # Резерв через Yahoo (добавляем .ME)
            yahoo_ticker = f"{ticker}.ME"
            # Проверим, есть ли данные через Yahoo
            try:
                df = yf.download(yahoo_ticker, period="1d", progress=False)
                if not df.empty:
                    assets[f"{name} ({ticker})"] = {
                        "ticker": yahoo_ticker,
                        "type": "Акция РФ",
                        "risk": "Низкий" if name in ["Сбербанк", "Газпром"] else "Средний",
                        "market": "Мосбиржа (Yahoo)",
                        "currency": "RUB"
                    }
            except:
                pass
    
    # ---- Акции США ----
    us_stocks = {
        "Apple Inc. (AAPL)": {"ticker": "AAPL", "risk": "Средний"},
        "NVIDIA (NVDA)": {"ticker": "NVDA", "risk": "Высокий"},
        "Tesla Inc. (TSLA)": {"ticker": "TSLA", "risk": "Высокий"},
    }
    for name, info in us_stocks.items():
        assets[name] = {
            "ticker": info["ticker"],
            "type": "Акция США",
            "risk": info["risk"],
            "market": "NASDAQ",
            "currency": "USD"
        }
    
    # ---- Индексы ----
    assets["S&P 500 (Индекс)"] = {
        "ticker": "^GSPC",
        "type": "Индекс США",
        "risk": "Средний",
        "market": "США",
        "currency": "USD"
    }
    
    # ---- ОФЗ (динамические) ----
    ofz_list = get_active_ofz(limit=5)
    for ofz in ofz_list:
        name = ofz['name'] if ofz['name'] else f"ОФЗ {ofz['ticker']}"
        assets[name] = {
            "ticker": ofz['ticker'],
            "type": "Облигация",
            "risk": "Низкий",
            "market": "Мосбиржа",
            "currency": "RUB"
        }
    
    # ---- Криптовалюты ----
    assets["Биткоин (BTC-USD)"] = {
        "ticker": "BTC-USD",
        "type": "Криптовалюта",
        "risk": "Очень высокий",
        "market": "Крипто",
        "currency": "USD"
    }
    assets["Эфириум (ETH-USD)"] = {
        "ticker": "ETH-USD",
        "type": "Криптовалюта",
        "risk": "Очень высокий",
        "market": "Крипто",
        "currency": "USD"
    }
    
    # ---- Валюты (для отображения в графике) ----
    assets["Доллар США (USDRUB)"] = {
        "ticker": "USDRUB",  # будем использовать get_cbr_currency
        "type": "Валюта",
        "risk": "Средний",
        "market": "Валютный",
        "currency": "RUB"
    }
    assets["Евро (EURRUB)"] = {
        "ticker": "EURRUB",
        "type": "Валюта",
        "risk": "Средний",
        "market": "Валютный",
        "currency": "RUB"
    }
    assets["Китайский юань (CNYRUB)"] = {
        "ticker": "CNYRUB",
        "type": "Валюта",
        "risk": "Средний",
        "market": "Валютный",
        "currency": "RUB"
    }
    
    # ---- Металлы ----
    metals = {
        "Золото (GC=F)": {"ticker": "GC=F", "risk": "Низкий"},
        "Серебро (SI=F)": {"ticker": "SI=F", "risk": "Средний"},
        "Платина (PL=F)": {"ticker": "PL=F", "risk": "Средний"}
    }
    for name, info in metals.items():
        assets[name] = {
            "ticker": info["ticker"],
            "type": "Металл",
            "risk": info["risk"],
            "market": "Сырье",
            "currency": "USD"
        }
    
    return assets

# Строим базу активов при загрузке (кэшируется)
ASSETS_DB = build_assets_db()

# ================= БАЗА БАНКОВСКИХ СТАВОК (статическая, для примера) =================
BANK_RATES = [
    {"name": "Сбербанк", "rate": 18.50, "min_sum": 100000, "term_months": 6, "note": "Накопительный счет"},
    {"name": "Т-Банк (Тинькофф)", "rate": 19.20, "min_sum": 50000, "term_months": 6, "note": "С пополнением"},
    {"name": "ВТБ", "rate": 18.70, "min_sum": 100000, "term_months": 6, "note": "Лучший для пенсионеров"},
    {"name": "Альфа-Банк", "rate": 19.00, "min_sum": 50000, "term_months": 3, "note": "Короткий срок"},
    {"name": "Газпромбанк", "rate": 18.40, "min_sum": 100000, "term_months": 6, "note": "Надежный"},
    {"name": "Райффайзенбанк", "rate": 18.20, "min_sum": 50000, "term_months": 6, "note": "Для премиум"},
    {"name": "ПСБ", "rate": 18.30, "min_sum": 100000, "term_months": 6, "note": "Гос. поддержка"},
    {"name": "Совкомбанк", "rate": 18.60, "min_sum": 30000, "term_months": 6, "note": "Для всех"},
    {"name": "МКБ", "rate": 18.90, "min_sum": 100000, "term_months": 6, "note": "Хорошая ставка"},
]

# ================= ВКЛАДКИ =================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 График", "💼 Портфель", "🤖 ИИ-прогноз", "📊 Доходность", "🏦 Вклады банков"])

# ================================
# Вкладка 1: Детальный анализ актива
# ================================
with tab1:
    asset_name = st.selectbox("Выберите актив", list(ASSETS_DB.keys()), index=0)
    meta = ASSETS_DB[asset_name]
    ticker = meta["ticker"]
    is_russian = meta["market"] == "Мосбиржа" or "Yahoo" in meta["market"]
    currency = "₽" if is_russian or meta["currency"] == "RUB" else "$"

    st.caption(f"Рынок: {meta['market']} | Риск: {meta['risk']}")

    with st.spinner(f"Загружаем данные для {asset_name}..."):
        data = None
        # Если это валюта — используем get_cbr_currency
        if meta["type"] == "Валюта":
            currency_code = ticker.replace("USDRUB", "USD").replace("EURRUB", "EUR").replace("CNYRUB", "CNY")
            rate = get_cbr_currency(currency_code)
            if rate is not None:
                # Создаём DataFrame с одной точкой
                data = pd.DataFrame({
                    'Date': [datetime.now()],
                    'Open': [rate], 'High': [rate], 'Low': [rate], 'Close': [rate], 'Volume': [0]
                })
            else:
                st.error("Не удалось загрузить курс валюты.")
                st.stop()
        else:
            if is_russian and not meta["type"] == "Криптовалюта":
                data = get_moex_data(ticker, period_days=365)
                if data is None or data.empty:
                    st.warning("⚠️ Официальный API Мосбиржи временно недоступен. Данные загружаются через Yahoo Finance.")
                    ticker_yahoo = f"{ticker}.ME" if not ticker.endswith('.ME') else ticker
                    data = yf.download(ticker_yahoo, period="1y", progress=False)
                    if not data.empty:
                        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.droplevel(1)
                        data = data.reset_index()
            else:
                data = yf.download(ticker, period="1y", progress=False)
                if not data.empty:
                    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.droplevel(1)
                    data = data.reset_index()

        if data is None or data.empty:
            st.error("❌ Не удалось загрузить данные. Проверьте интернет.")
            st.stop()

        latest = data['Close'].iloc[-1]
        first = data['Close'].iloc[0]
        delta = latest - first
        if pd.isna(latest): latest = 0.0
        if pd.isna(delta): delta = 0.0

        c1, c2, c3 = st.columns(3)
        c1.metric(f"Цена", f"{currency}{latest:.2f}", f"{currency}{delta:.2f}")
        c2.metric("Максимум", f"{currency}{data['High'].max():.2f}")
        c3.metric("Минимум", f"{currency}{data['Low'].min():.2f}")

        # Рисуем свечной график, если данных больше одной точки
        if len(data) > 1:
            fig = go.Figure(data=[go.Candlestick(
                x=data['Date'], open=data['Open'], high=data['High'],
                low=data['Low'], close=data['Close'], name="Цена"
            )])
            fig.update_layout(title=f"{asset_name} — График цены", xaxis_title="Дата", yaxis_title=f"Цена ({currency})",
                              hovermode="x unified", xaxis_tickformat="%d %b %Y")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Для валют отображается только текущий курс, история недоступна.")

# ================================
# Функция генерации плана действий (без изменений)
# ================================
def generate_action_plan(asset_name, price, risk_profile, alloc_rub):
    price = float(price)
    if price <= 0:
        return "Цена недоступна. Проверьте данные."
    
    if risk_profile == "Консервативный (Низкий риск)":
        if "ОФЗ" in asset_name:
            return "✅ **Купить и держать до погашения.** Облигации дают стабильный купонный доход."
        elif "Золото" in asset_name or "GC=F" in asset_name:
            return "🛡️ **Защитный актив.** Рекомендация: купить и держать 6-12 месяцев. Стоп-лосс: -5%, Тейк-профит: +8%."
        else:
            return "📉 **Акции с низким риском.** Рекомендация: держать 1-2 года. Стоп-лосс: -8%."
    elif risk_profile == "Сбалансированный (Средний риск)":
        if "BTC" in asset_name or "ETH" in asset_name:
            return "⚡ **Спекулятивный актив.** Рекомендация: DCA-стратегия (покупать частями). Стоп-лосс: -15%, Тейк-профит: +20%."
        elif "NVDA" in asset_name or "TSLA" in asset_name:
            return "🚀 **Акции роста.** Рекомендация: следить за квартальными отчетами. Стоп-лосс: -10%, Тейк-профит: +15%."
        else:
            return "📊 **Сбалансированный актив.** Рекомендация: держать 3-6 месяцев. При росте на 10% - зафиксируйте 50% прибыли."
    else: 
        if "BTC" in asset_name or "ETH" in asset_name:
            return "🔥 **Высокорисковый актив.** Стоп-лосс: -20%, Тейк-профит: +30%. При падении не паникуйте, ждите восстановления."
        elif "NVDA" in asset_name:
            return "🚀 **Агрессивный рост.** Стоп-лосс: -15%, Тейк-профит: +25%. При достижении +25% продавайте 50%."
        else:
            return "📈 **Актив роста.** Стоп-лосс: -10%. При росте на 15% - зафиксируйте часть прибыли."

# ================================
# Вкладка 2: Портфель (с автоматическим подбором)
# ================================
if 'portfolio_data' not in st.session_state:
    st.session_state.portfolio_data = None

with tab2:
    st.subheader("💼 Динамический портфель с ИИ-планом действий")
    st.info("Количество позиций подбирается автоматически. Если сумма на актив меньше 3000 ₽, он исключается (чтобы избежать лишних комиссий).")

    budget = st.number_input("Введите бюджет (₽)", min_value=1000, value=100000, step=5000)
    risk_profile = st.selectbox("Профиль риска", ["Консервативный (Низкий риск)", "Сбалансированный (Средний риск)", "Агрессивный (Максимальный доход)"])

    if st.button("Собрать портфель и получить план"):
        with st.spinner("Загружаем цены и просчитываем стратегию..."):
            MIN_POSITION_RUB = 3000
            # Определяем список тикеров для проверки
            tickers_to_check = []
            # Добавляем тикеры из ASSETS_DB, которые не являются валютами (их мы будем обрабатывать отдельно)
            for key, val in ASSETS_DB.items():
                if val["type"] == "Валюта":
                    continue
                tickers_to_check.append(val["ticker"])
            # Убираем дубликаты
            tickers_to_check = list(set(tickers_to_check))
            
            prices = {t: 0.0 for t in tickers_to_check}

            # Получаем курс доллара из ЦБ (для конвертации USD-активов)
            usd_rub_price = get_cbr_currency("USD")
            if usd_rub_price is None or usd_rub_price <= 0:
                usd_rub_price = 90.0

            # Словарь для преобразования валютных тикеров в коды ЦБ
            currency_map = {"USDRUB": "USD", "EURRUB": "EUR", "CNYRUB": "CNY"}

            for t in tickers_to_check:
                # Проверяем, является ли тикер валютой (если он в currency_map)
                if t in currency_map:
                    curr_code = currency_map[t]
                    price_rub = get_cbr_currency(curr_code)
                    if price_rub is not None:
                        prices[t] = float(price_rub)
                    else:
                        prices[t] = 0.0
                elif t in CURRENCY_TICKERS:
                    # Если это просто USD, EUR и т.д. (не используется)
                    price_rub = get_cbr_currency(t)
                    if price_rub is not None:
                        prices[t] = float(price_rub)
                    else:
                        prices[t] = 0.0
                else:
                    # Пытаемся загрузить через MOEX или Yahoo
                    # Сначала пробуем MOEX (для российских акций и облигаций)
                    df = get_moex_data(t, period_days=2)
                    if df is not None and not df.empty:
                        val = df['Close'].iloc[-1]
                        prices[t] = float(val) if not pd.isna(val) else 0.0
                    else:
                        # Если не получилось, используем Yahoo
                        prices[t] = get_live_price(t)

            # Формируем структуру аллокации на основе доступных активов
            # Выбираем активы в зависимости от профиля риска
            # Для простоты используем фиксированный набор, но с динамическими тикерами
            # Мы будем брать из ASSETS_DB те, которые есть в списке tickers_to_check и у которых цена > 0
            
            # Сортируем активы по типу (защитные, доходные, рискованные)
            conservative_assets = []
            balanced_assets = []
            aggressive_assets = []
            
            for name, meta in ASSETS_DB.items():
                ticker = meta["ticker"]
                price = prices.get(ticker, 0.0)
                if price <= 0:
                    continue
                if meta["type"] in ["Облигация", "Металл"] and meta.get("risk") == "Низкий":
                    conservative_assets.append(name)
                elif meta["type"] in ["Акция РФ", "Акция США"] and meta.get("risk") in ["Низкий", "Средний"]:
                    balanced_assets.append(name)
                elif meta["type"] in ["Криптовалюта"] or meta.get("risk") in ["Высокий", "Очень высокий"]:
                    aggressive_assets.append(name)
                else:
                    balanced_assets.append(name)
            
            # Выбираем активы в зависимости от профиля
            if risk_profile == "Консервативный (Низкий риск)":
                selected_assets = conservative_assets[:3] + balanced_assets[:2]
            elif risk_profile == "Сбалансированный (Средний риск)":
                selected_assets = conservative_assets[:2] + balanced_assets[:3] + aggressive_assets[:1]
            else:  # Агрессивный
                selected_assets = balanced_assets[:2] + aggressive_assets[:3] + conservative_assets[:1]
            
            # Если активов мало, добавляем из других категорий
            if len(selected_assets) < 3:
                all_assets = list(ASSETS_DB.keys())
                for name in all_assets:
                    if name not in selected_assets:
                        ticker = ASSETS_DB[name]["ticker"]
                        if prices.get(ticker, 0.0) > 0:
                            selected_assets.append(name)
                        if len(selected_assets) >= 5:
                            break
            
            # Распределяем бюджет равномерно между выбранными активами
            num_assets = len(selected_assets)
            if num_assets == 0:
                st.warning("Не удалось найти доступные активы для портфеля.")
                st.stop()
            
            # Создаём словарь долей (равномерно)
            equal_share = 1.0 / num_assets
            asset_alloc = {name: equal_share for name in selected_assets}
            
            # Далее формируем таблицу и план действий (как в старом коде)
            table_data = []
            total_spent_rub = 0
            
            for name, ratio in asset_alloc.items():
                alloc_rub = int(budget * ratio)
                if num_assets == 1:
                    alloc_rub = budget

                meta = ASSETS_DB[name]
                ticker_code = meta["ticker"]
                price = float(prices.get(ticker_code, 0.0))
                
                qty_to_buy = 0.0
                actual_cost_rub = 0.0
                display_qty = "Нет данных"
                display_price = "-"

                if price > 0.0:
                    display_price = f"{price:.2f}"
                    if meta["currency"] == "USD":
                        alloc_usd = alloc_rub / usd_rub_price
                        qty_to_buy = alloc_usd / price
                        actual_cost_usd = qty_to_buy * price
                        actual_cost_rub = actual_cost_usd * usd_rub_price
                        if not np.isfinite(qty_to_buy): qty_to_buy = 0.0
                        if "BTC" in ticker_code:
                            display_qty = f"{qty_to_buy:.6f} BTC"
                        elif "GC=F" in ticker_code or "SI=F" in ticker_code or "PL=F" in ticker_code:
                            display_qty = f"{qty_to_buy:.4f} унц."
                        else:
                            display_qty = f"{qty_to_buy:.4f} шт."
                    else:
                        qty_to_buy = alloc_rub / price
                        actual_cost_rub = qty_to_buy * price
                        if not np.isfinite(qty_to_buy): qty_to_buy = 0.0
                        if "USDRUB" in ticker_code or "EURRUB" in ticker_code or "CNYRUB" in ticker_code:
                            display_qty = f"{qty_to_buy:.2f} ед."
                        else:
                            display_qty = f"{qty_to_buy:.2f} шт."
                else:
                    actual_cost_rub = 0.0
                    display_qty = "⚠️ Цена не загружена"

                total_spent_rub += actual_cost_rub
                table_data.append({
                    "Актив": name,
                    "Доля": f"{int(ratio*100)}%",
                    "Выделено (₽)": f"{alloc_rub:,.0f}",
                    "Цена": display_price,
                    "Нужно купить": display_qty,
                    "Итог (₽)": f"{actual_cost_rub:,.2f}"
                })

            st.success(f"✅ Портфель готов! Подобрано **{len(table_data)}** позиций.")
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

            leftover = budget - total_spent_rub
            if leftover > 0:
                st.info(f"💰 Остаток: **{leftover:,.0f} ₽**. Рекомендуем оставить на комиссию брокера.")

            st.divider()
            st.subheader("🧠 План действий от ИИ-советника")
            plan_text = ""
            for row in table_data:
                asset_name = row["Актив"]
                price_str = row["Цена"]
                alloc_amount = row["Выделено (₽)"]
                try:
                    price = float(price_str) if price_str != "-" else 0.0
                except:
                    price = 0.0
                action = generate_action_plan(asset_name, price, risk_profile, alloc_amount)
                plan_text += f"🔹 **{asset_name}**: \n{action}\n\n"

            st.markdown(plan_text)
            
            st.session_state.portfolio_data = table_data
            st.session_state.portfolio_risk = risk_profile

# ================================
# Вкладка 3: Умный ИИ и прогноз (без изменений)
# ================================
with tab3:
    st.subheader("🤖 Прогноз сезонности и анализ прошлых аномалий")
    asset_pred_name = st.selectbox("Выберите актив для прогноза", list(ASSETS_DB.keys()), index=1)
    pred_meta = ASSETS_DB[asset_pred_name]
    pred_ticker = pred_meta["ticker"]
    pred_russian = pred_meta["market"] == "Мосбиржа" or "Yahoo" in pred_meta["market"]
    is_currency = pred_meta["type"] == "Валюта"

    # ================= ФУНКЦИЯ ДЛЯ ИСТОРИЧЕСКИХ КУРСОВ ВАЛЮТ =================
    @st.cache_data(ttl=3600)
    def get_currency_history(base_currency, target_currency='RUB', days=365):
        """
        Получает исторические курсы валюты через exchangerate.host.
        base_currency: USD, EUR, CNY и т.д.
        target_currency: RUB (по умолчанию)
        days: количество дней назад
        Возвращает DataFrame с колонками Date и Close (курс).
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            url = f"https://api.exchangerate.host/timeseries"
            params = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'base': base_currency,
                'symbols': target_currency
            }
            response = requests.get(url, params=params)
            data = response.json()
            if 'rates' not in data:
                return None
            rates = data['rates']
            df = pd.DataFrame.from_dict(rates, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            df = df.rename(columns={target_currency: 'Close'})
            df['Date'] = df.index
            df = df[['Date', 'Close']]
            return df
        except Exception as e:
            st.error(f"Ошибка загрузки истории валют: {e}")
            return None

    if st.button("Запустить ИИ-анализ (с сезонностью)"):
        with st.spinner("Модель Prophet рассчитывает сезонные тренды..."):
            pred_data = None
            
            # ---- Если выбран актив "Валюта" ----
            if is_currency:
                # Определяем код базовой валюты (USD, EUR, CNY)
                if "USDRUB" in pred_ticker:
                    base = "USD"
                elif "EURRUB" in pred_ticker:
                    base = "EUR"
                elif "CNYRUB" in pred_ticker:
                    base = "CNY"
                else:
                    # Если вдруг другой тикер, пробуем взять первые 3 буквы
                    base = pred_ticker[:3].upper()
                pred_data = get_currency_history(base, 'RUB', days=365)
                if pred_data is None or pred_data.empty:
                    st.error("Не удалось загрузить историю валюты. Попробуйте другой актив.")
                    st.stop()
                st.caption(f"Исторические данные для {base}/RUB за последние 365 дней (источник: exchangerate.host)")

            # ---- Для остальных активов (акции, облигации, крипта, металлы) ----
            else:
                if pred_russian and not is_currency:
                    pred_data = get_moex_data(pred_ticker, 500)
                    if pred_data is None or pred_data.empty:
                        st.warning("⚠️ Официальный API Мосбиржи временно недоступен. Данные загружаются через Yahoo Finance.")
                        ticker_yahoo = f"{pred_ticker}.ME" if not pred_ticker.endswith('.ME') else pred_ticker
                        pred_data = yf.download(ticker_yahoo, period="1y", progress=False)
                        if not pred_data.empty:
                            if isinstance(pred_data.columns, pd.MultiIndex):
                                pred_data.columns = pred_data.columns.droplevel(1)
                            pred_data = pred_data.reset_index()
                else:
                    pred_data = yf.download(pred_ticker, period="1y", progress=False)
                    if not pred_data.empty:
                        if isinstance(pred_data.columns, pd.MultiIndex):
                            pred_data.columns = pred_data.columns.droplevel(1)
                        pred_data = pred_data.reset_index()

            if pred_data is None or pred_data.empty:
                st.error("Недостаточно данных для построения прогноза.")
                st.stop()

            # ---- Убедимся, что колонки называются 'Date' и 'Close' ----
            if 'Date' not in pred_data.columns:
                pred_data = pred_data.reset_index()
                pred_data.rename(columns={'index': 'Date'}, inplace=True)
            if 'Close' not in pred_data.columns:
                st.error("В данных нет колонки 'Close'.")
                st.stop()

            # ---- Прогноз через Prophet ----
            df_prophet = pred_data[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
            m = Prophet(daily_seasonality=False, yearly_seasonality=True)
            # Добавляем праздники только для не-валют
            if not is_currency:
                m.add_country_holidays(country_name='US' if not pred_russian else 'Russia')
            m.fit(df_prophet)
            future = m.make_future_dataframe(periods=60)
            forecast = m.predict(future)

            # ---- Рисуем график ----
            fig_pred = go.Figure()
            fig_pred.add_trace(go.Scatter(x=pred_data['Date'], y=pred_data['Close'], mode='lines', name='Реальная цена'))
            fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Прогноз ИИ (Prophet)', line=dict(dash='dash', color='red')))
            fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], fill=None, mode='lines', line_color='rgba(255,0,0,0.05)', name='Верхняя граница', showlegend=False))
            fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], fill='tonexty', mode='lines', line_color='rgba(255,0,0,0.05)', name='Нижняя граница', showlegend=False))
            fig_pred.update_layout(title=f"ИИ-прогноз (Сезонная модель Facebook Prophet) на 60 дней", xaxis_title="Дата")
            st.plotly_chart(fig_pred, use_container_width=True)

            # ---- Анализ сильных изменений (только для акций, для валют тоже можно) ----
            st.divider()
            st.subheader("📉 Анализ исторических провалов и взлетов")
            daily_returns = pred_data['Close'].pct_change()
            
            if len(daily_returns) > 0:
                worst_days = daily_returns.nsmallest(5).dropna()
                best_days = daily_returns.nlargest(5).dropna()

                st.markdown("**Дни самого сильного падения:**")
                if not worst_days.empty:
                    for idx, pct in worst_days.items():
                        real_date = pred_data.iloc[idx]['Date']
                        date_formatted = real_date.strftime("%d.%m.%Y")
                        st.write(f"📉 {date_formatted}: падение на **{pct:.2%}**. *Примечание: часто это связано с выходом плохой отчетности или макроэкономическими новостями.*")
                else:
                    st.write("Нет значительных падений.")

                st.markdown("**Дни самого сильного роста:**")
                if not best_days.empty:
                    for idx, pct in best_days.items():
                        real_date = pred_data.iloc[idx]['Date']
                        date_formatted = real_date.strftime("%d.%m.%Y")
                        st.write(f"📈 {date_formatted}: рост на **{pct:.2%}**. *Примечание: обычно происходит на позитивных новостях или сильных квартальных отчетах.*")
                else:
                    st.write("Нет значительных ростов.")
            else:
                st.write("Недостаточно данных для анализа.")

# ================================
# Вкладка 4: Чистая доходность и макро-риски
# ================================
with tab4:
    st.subheader("📊 Чистая доходность и макроэкономические риски")
    
    with st.expander("ℹ️ Как это работает и зачем это нужно"):
        st.markdown("""
        *   **Банковский вклад** дает фиксированный процент, но **НЕ защищает от обвала рубля**. Если курс доллара завтра вырастет на 30%, ваши рубли в банке обесценятся на те же 30% в реальной покупательной способности.
        *   **Наш портфель** содержит валюту и золото. Это даёт защиту от обесценивания рубля. В этой вкладке мы считаем реальную прибыль с учетом налогов.
        *   *Важно:* Налог 13% на дивиденды и купоны по облигациям удерживается брокером автоматически. Мы учтем это в расчетах.
        """)

    st.subheader("1️⃣ Банковский вклад (ваш базовый вариант)")
    col_bank, col_infl = st.columns(2)
    with col_bank:
        bank_rate = st.number_input("Ставка по вкладу (годовых, %)", min_value=0.0, max_value=30.0, value=18.0, step=0.5)
    with col_infl:
        inflation_rate = st.number_input("Ожидаемая инфляция (годовых, %)", min_value=0.0, max_value=50.0, value=8.5, step=0.5)

    real_bank_return = ((1 + bank_rate/100) / (1 + inflation_rate/100) - 1) * 100
    st.metric(
        label="Реальная доходность вклада (очищенная от инфляции)", 
        value=f"{real_bank_return:.1f}%",
        delta="Пассивный доход без риска девальвации"
    )
    st.caption("⚠️ Если рубль упадет (девальвация), банковский вклад потеряет покупательную способность.")

    st.divider()

    st.subheader("2️⃣ Ваш инвестиционный портфель (с учетом налога)")
    
    if st.session_state.portfolio_data is not None and len(st.session_state.portfolio_data) > 0:
        st.success("✅ Портфель найден! Используются данные из вкладки «Портфель».")
        
        st.markdown("**Введите ваши ожидания по доходности на следующие 12 месяцев:**")
        col_div, col_coup = st.columns(2)
        with col_div:
            exp_div_yield = st.number_input("Дивидендная доходность акций (%)", min_value=0.0, max_value=30.0, value=10.0, step=0.5)
        with col_coup:
            exp_coup_yield = st.number_input("Купонная доходность по ОФЗ (%)", min_value=0.0, max_value=30.0, value=16.0, step=0.5)

        portfolio_df = pd.DataFrame(st.session_state.portfolio_data)
        
        total_allocated_rub = pd.to_numeric(
            portfolio_df['Выделено (₽)'].astype(str).str.replace(r'[^\d]', '', regex=True), 
            errors='coerce'
        ).sum()

        stock_rub = 0.0
        bond_rub = 0.0
        gold_rub = 0.0
        crypto_rub = 0.0
        forex_rub = 0.0

        for _, row in portfolio_df.iterrows():
            name = row['Актив']
            cleaned_str = re.sub(r'[^\d]', '', str(row['Выделено (₽)']))
            amount = float(cleaned_str) if cleaned_str else 0.0

            if "ОФЗ" in name: bond_rub += amount
            elif "Золото" in name or "GC=F" in name or "PL=F" in name: gold_rub += amount
            elif "BTC" in name or "ETH" in name: crypto_rub += amount
            elif "USD" in name or "CNY" in name or "EUR" in name: forex_rub += amount
            else: stock_rub += amount

        income_before_tax = (stock_rub * (exp_div_yield/100)) + (bond_rub * (exp_coup_yield/100))
        tax_13 = income_before_tax * 0.13
        income_after_tax = income_before_tax - tax_13
        
        if total_allocated_rub > 0:
            nominal_yield_pct = (income_after_tax / total_allocated_rub) * 100
            real_portfolio_return = ((1 + nominal_yield_pct/100) / (1 + inflation_rate/100) - 1) * 100
            
            st.metric(
                label="Реальная доходность портфеля после налога 13%", 
                value=f"{real_portfolio_return:.1f}%",
                delta=f"Чистый доход: ~{income_after_tax:,.0f} ₽"
            )
            st.write(f"Налог 13%, удержанный брокером, уже включен в расчеты.")
    else:
        st.info("👈 Сначала соберите портфель во вкладке «Портфель», затем возвращайтесь сюда для расчёта чистой прибыли.")
    
    st.divider()
    st.subheader("🛡️ Анализ рисков: Девальвация и Дефолт")
    st.markdown("""
    **1. Риск девальвации (обвала рубля):**
    Если вы держите все деньги в рублях (вклад), обвал курса на 20% превратит вашу реальную доходность в -20% за один день. 
    *Решение:* В нашем портфеле 30-40% выделено на доллар, юань и золото. При обвале рубля эти активы взлетают в цене в рублях и компенсируют потери.

    **2. Риск дефолта (краха банка или государства):**
    Вклад до 1,4 млн ₽ застрахован государством (АСВ) — это значит, что деньги вернут.
    *Решение:* Держать деньги свыше 1,4 млн рублей в одном банке опасно. Наш портфель распределяет деньги между разными активами, снижая риск потери капитала до минимума.
    """)

# ================================
# Вкладка 5: Сравнение банковских ставок
# ================================
with tab5:
    st.subheader("🏦 Лучшие предложения по вкладам в РФ")
    st.caption("Данные основаны на текущей ключевой ставке ЦБ РФ (~19%) и актуальны на 2026 год. Информация носит ознакомительный характер.")

    col_sum, col_time = st.columns(2)
    with col_sum:
        calc_sum = st.number_input("Ваша сумма вклада (₽)", min_value=10000, value=1000000, step=50000)
    with col_time:
        calc_term = st.number_input("Срок вклада (месяцев)", min_value=1, max_value=36, value=12, step=1)

    st.divider()

    results = []
    for bank in BANK_RATES:
        profit_before_tax = calc_sum * (bank["rate"] / 100) * (calc_term / 12)
        tax_13 = profit_before_tax * 0.13
        profit_after_tax = profit_before_tax - tax_13
        total_amount = calc_sum + profit_after_tax
        
        results.append({
            "Банк": bank["name"],
            "Ставка": f"{bank['rate']}%",
            "Мин. сумма": f"{bank['min_sum']:,.0f} ₽",
            "Примечание": bank["note"],
            "Прибыль до налога (₽)": round(profit_before_tax, 2),
            "Прибыль после налога 13% (₽)": round(profit_after_tax, 2),
            "Итоговая сумма (₽)": round(total_amount, 2)
        })

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values(by="Прибыль после налога 13% (₽)", ascending=False)

    st.dataframe(
        df_results, 
        use_container_width=True, 
        hide_index=True,
        column_config={
            "Итоговая сумма (₽)": st.column_config.NumberColumn(format="%.2f ₽"),
            "Прибыль до налога (₽)": st.column_config.NumberColumn(format="%.2f ₽"),
            "Прибыль после налога 13% (₽)": st.column_config.NumberColumn(format="%.2f ₽"),
        }
    )

    st.info("💡 **О налоге на вклады:** Согласно законодательству РФ, налогом (13%) облагается не вся прибыль, а только та часть, которая превышает 1 млн ₽ или превышает сумму, рассчитанную по ключевой ставке ЦБ. Для упрощения расчетов мы вычли 13% со всей прибыли. Реальная сумма к выплате может быть немного выше, чем указано в таблице.")

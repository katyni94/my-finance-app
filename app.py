import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import re
from datetime import datetime, timedelta
from prophet import Prophet
import requests
import xml.etree.ElementTree as ET
CURRENCY_TICKERS = {'USD', 'EUR', 'CNY', 'GBP', 'JPY', 'CHF'}

@st.cache_data(ttl=3600)
def get_cbr_currency(currency_code):
    """
    Получает курс валюты от ЦБ РФ по коду (USD, EUR, CNY)
    """
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

st.set_page_config(page_title="Финансовый ассистент", layout="wide")

st.title("📊 Смарт-Ассистент для РФ")
# --- Блок курсов валют (ЦБ РФ) ---
st.sidebar.header("💱 Курсы валют (ЦБ РФ)")

usd = get_cbr_currency("USD")
eur = get_cbr_currency("EUR")
cny = get_cbr_currency("CNY")

if usd:
    st.sidebar.metric("🇺🇸 Доллар США", f"{usd:.4f} ₽")
else:
    st.sidebar.warning("Не удалось загрузить курс USD")

if eur:
    st.sidebar.metric("🇪🇺 Евро", f"{eur:.4f} ₽")
else:
    st.sidebar.warning("Не удалось загрузить курс EUR")

if cny:
    st.sidebar.metric("🇨🇳 Китайский юань", f"{cny:.4f} ₽")
else:
    st.sidebar.warning("Не удалось загрузить курс CNY")
st.markdown("Анализ акций РФ/США, облигаций, криптовалют, металлов и валют. Портфель и прогноз с учетом сезонности.")

# ================= ФУНКЦИЯ ДЛЯ РОССИЙСКИХ АКЦИЙ (MOEX) =================
def get_moex_data(ticker, period_days=365):
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

# ================= БАЗА ДАННЫХ АКТИВОВ =================
ASSETS_DB = {
    "Сбербанк (SBER)": {"ticker": "SBER", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},
    "Лукойл (LKOH)": {"ticker": "LKOH", "type": "Акция РФ", "risk": "Средний", "market": "Мосбиржа", "currency": "RUB"},
    "Газпром (GAZP)": {"ticker": "GAZP", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},
    "Яндекс (YNDX)": {"ticker": "YNDX", "type": "Акция РФ", "risk": "Высокий", "market": "Мосбиржа", "currency": "RUB"},
    "Apple Inc. (AAPL)": {"ticker": "AAPL", "type": "Акция США", "risk": "Средний", "market": "NASDAQ", "currency": "USD"},
    "NVIDIA (NVDA)": {"ticker": "NVDA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ", "currency": "USD"},
    "Tesla Inc. (TSLA)": {"ticker": "TSLA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ", "currency": "USD"},
    "S&P 500 (Индекс)": {"ticker": "^GSPC", "type": "Индекс США", "risk": "Средний", "market": "США", "currency": "USD"},
    "ОФЗ (Гос. облигации РФ)": {"ticker": "SU26227RMFS4", "type": "Облигация", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},
    "Биткоин (BTC-USD)": {"ticker": "BTC-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто", "currency": "USD"},
    "Эфириум (ETH-USD)": {"ticker": "ETH-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто", "currency": "USD"},
    "Доллар США (USDRUB)": {"ticker": "USDRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},
    "Евро (EURRUB)": {"ticker": "EURRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},
    "Китайский юань (CNYRUB)": {"ticker": "CNYRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},
    "Золото (GC=F)": {"ticker": "GC=F", "type": "Металл", "risk": "Низкий", "market": "Сырье", "currency": "USD"},
    "Серебро (SI=F)": {"ticker": "SI=F", "type": "Металл", "risk": "Средний", "market": "Сырье", "currency": "USD"},
    "Платина (PL=F)": {"ticker": "PL=F", "type": "Металл", "risk": "Средний", "market": "Сырье", "currency": "USD"},
}

# ================= УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ЗАГРУЗКИ ЦЕНЫ =================
def get_live_price(ticker):
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

# ================= БАЗА БАНКОВСКИХ СТАВОК =================
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

# --- Интерфейс ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 График", "💼 Портфель", "🤖 ИИ-прогноз", "📊 Доходность", "🏦 Вклады банков"])

# ================================
# Вкладка 1: Детальный анализ актива
# ================================
with tab1:
    asset_name = st.selectbox("Выберите актив", list(ASSETS_DB.keys()), index=0)
    meta = ASSETS_DB[asset_name]
    ticker = meta["ticker"]
    is_russian = meta["market"] == "Мосбиржа"
    currency = "₽" if is_russian or meta["currency"] == "RUB" else "$"

    st.caption(f"Рынок: {meta['market']} | Риск: {meta['risk']}")

    with st.spinner(f"Загружаем данные для {asset_name}..."):
        data = None
        if is_russian:
            data = get_moex_data(ticker, period_days=365)
            if data is None or data.empty:
                st.warning("⚠️ Официальный API Мосбиржи временно недоступен. Данные загружаются через Yahoo Finance.")
                ticker_yahoo = f"{ticker}.ME"
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

        fig = go.Figure(data=[go.Candlestick(
            x=data['Date'], open=data['Open'], high=data['High'],
            low=data['Low'], close=data['Close'], name="Цена"
        )])
        fig.update_layout(title=f"{asset_name} — График цены", xaxis_title="Дата", yaxis_title=f"Цена ({currency})",
                          hovermode="x unified", xaxis_tickformat="%d %b %Y")
        st.plotly_chart(fig, use_container_width=True)

# ================================
# Вкладка 2: Портфель (Динамическое кол-во активов)
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
            tickers_to_check = ["GC=F", "BTC-USD", "NVDA", "SBER", "USDRUB=X", "CNYRUB=X", "SU26227RMFS4"]
            prices = {t: 0.0 for t in tickers_to_check}

            # Получаем курс доллара из ЦБ (для конвертации USD-активов)
            usd_rub_price = get_cbr_currency("USD")
            if usd_rub_price is None or usd_rub_price <= 0:
                usd_rub_price = 90.0  # запасное значение

            for t in tickers_to_check:
                # Проверяем, является ли тикер валютой
                if t in CURRENCY_TICKERS or t.startswith(('USDRUB', 'EURRUB', 'CNYRUB')):
                    if t == "USDRUB=X":
                        curr_code = "USD"
                    elif t == "EURRUB=X":
                        curr_code = "EUR"
                    elif t == "CNYRUB=X":
                        curr_code = "CNY"
                    else:
                        curr_code = t
                    price_rub = get_cbr_currency(curr_code)
                    if price_rub is not None:
                        prices[t] = float(price_rub)
                    else:
                        prices[t] = 0.0
                elif t == "SBER" or t == "SU26227RMFS4":
                    df = get_moex_data(t, 2)
                    if df is not None and not df.empty:
                        val = df['Close'].iloc[-1]
                        prices[t] = float(val) if not pd.isna(val) else 0.0
                else:
                    prices[t] = get_live_price(t)

            asset_alloc_base = {
                "Консервативный (Низкий риск)": {"Золото (GC=F)": 0.25, "ОФЗ (SU26227RMFS4)": 0.25, "Доллар США (USDRUB)": 0.20, "Китайский юань (CNYRUB)": 0.15, "Сбербанк (SBER)": 0.10, "Биткоин (BTC-USD)": 0.05},
                "Сбалансированный (Средний риск)": {"Золото (GC=F)": 0.15, "ОФЗ (SU26227RMFS4)": 0.15, "Доллар США (USDRUB)": 0.15, "Китайский юань (CNYRUB)": 0.10, "Сбербанк (SBER)": 0.15, "NVIDIA (NVDA)": 0.15, "Биткоин (BTC-USD)": 0.15},
                "Агрессивный (Максимальный доход)": {"Биткоин (BTC-USD)": 0.25, "NVIDIA (NVDA)": 0.20, "Сбербанк (SBER)": 0.15, "Золото (GC=F)": 0.10, "Доллар США (USDRUB)": 0.10, "Китайский юань (CNYRUB)": 0.10, "ОФЗ (SU26227RMFS4)": 0.10}
            }
            initial_alloc = asset_alloc_base[risk_profile]
            
            final_alloc = {}
            pool_cash = 0.0
            
            for name, ratio in initial_alloc.items():
                alloc_rub = int(budget * ratio)
                if alloc_rub >= MIN_POSITION_RUB:
                    final_alloc[name] = ratio
                else:
                    pool_cash += alloc_rub

            if not final_alloc:
                st.warning("⚠️ Бюджет слишком мал для разделения на активы. Все деньги направлены в самый надежный актив.")
                first_asset = list(initial_alloc.keys())[0]
                final_alloc[first_asset] = 1.0

            table_data = []
            total_spent_rub = 0
            
            for name, ratio in final_alloc.items():
                alloc_rub = int(budget * ratio)
                if len(final_alloc) == 1:
                    alloc_rub = budget

                ticker_code = name.split("(")[1].replace(")", "")
                price = float(prices.get(ticker_code, 0.0))
                
                qty_to_buy = 0.0
                actual_cost_rub = 0.0
                display_qty = "Нет данных"
                display_price = "-"

                if price > 0.0:
                    display_price = f"{price:.2f}"
                    meta = next((v for k, v in ASSETS_DB.items() if v["ticker"] == ticker_code), None)
                    
                    if meta and meta["currency"] == "USD":
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
# Вкладка 3: Умный ИИ и прогноз
# ================================
with tab3:
    st.subheader("🤖 Прогноз сезонности и анализ прошлых аномалий")
    asset_pred_name = st.selectbox("Выберите актив для прогноза", list(ASSETS_DB.keys()), index=1)
    pred_meta = ASSETS_DB[asset_pred_name]
    pred_ticker = pred_meta["ticker"]
    pred_russian = pred_meta["market"] == "Мосбиржа"

    if st.button("Запустить ИИ-анализ (с сезонностью)"):
        with st.spinner("Модель Prophet рассчитывает сезонные тренды..."):
            pred_data = None
            if pred_russian:
                pred_data = get_moex_data(pred_ticker, 500)
                if pred_data is None or pred_data.empty:
                    pred_data = yf.download(f"{pred_ticker}.ME", period="1mo", progress=False)
                    if not pred_data.empty and isinstance(pred_data.columns, pd.MultiIndex):
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
            else:
                df_prophet = pred_data[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})
                m = Prophet(daily_seasonality=False, yearly_seasonality=True)
                m.add_country_holidays(country_name='US' if not pred_russian else 'Russia')
                m.fit(df_prophet)
                future = m.make_future_dataframe(periods=60)
                forecast = m.predict(future)

                fig_pred = go.Figure()
                fig_pred.add_trace(go.Scatter(x=pred_data['Date'], y=pred_data['Close'], mode='lines', name='Реальная цена'))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Прогноз ИИ (Prophet)', line=dict(dash='dash', color='red')))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], fill=None, mode='lines', line_color='rgba(255,0,0,0.05)', name='Верхняя граница', showlegend=False))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], fill='tonexty', mode='lines', line_color='rgba(255,0,0,0.05)', name='Нижняя граница', showlegend=False))
                fig_pred.update_layout(title=f"ИИ-прогноз (Сезонная модель Facebook Prophet) на 60 дней", xaxis_title="Дата")
                st.plotly_chart(fig_pred, use_container_width=True)

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
# Вкладка 4: Чистая доходность и макро-риски (ОКОНЧАТЕЛЬНОЕ ИСПРАВЛЕНИЕ)
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
            
            # ================= ОКОНЧАТЕЛЬНОЕ ИСПРАВЛЕНИЕ =================
            # Удаляем ВСЕ, кроме цифр. Это безопасно для float()
            cleaned_str = re.sub(r'[^\d]', '', str(row['Выделено (₽)']))
            amount = float(cleaned_str) if cleaned_str else 0.0
            # ============================================================

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

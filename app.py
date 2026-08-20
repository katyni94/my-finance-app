import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from prophet import Prophet

st.set_page_config(page_title="Финансовый ассистент", layout="wide")

st.title("📊 Смарт-Ассистент для РФ")
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
    # Акции РФ
    "Сбербанк (SBER)": {"ticker": "SBER", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},
    "Лукойл (LKOH)": {"ticker": "LKOH", "type": "Акция РФ", "risk": "Средний", "market": "Мосбиржа", "currency": "RUB"},
    "Газпром (GAZP)": {"ticker": "GAZP", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},
    "Яндекс (YNDX)": {"ticker": "YNDX", "type": "Акция РФ", "risk": "Высокий", "market": "Мосбиржа", "currency": "RUB"},

    # Акции США
    "Apple Inc. (AAPL)": {"ticker": "AAPL", "type": "Акция США", "risk": "Средний", "market": "NASDAQ", "currency": "USD"},
    "NVIDIA (NVDA)": {"ticker": "NVDA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ", "currency": "USD"},
    "Tesla Inc. (TSLA)": {"ticker": "TSLA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ", "currency": "USD"},
    "S&P 500 (Индекс)": {"ticker": "^GSPC", "type": "Индекс США", "risk": "Средний", "market": "США", "currency": "USD"},

    # Облигации
    "ОФЗ (Гос. облигации РФ)": {"ticker": "SU26227RMFS4", "type": "Облигация", "risk": "Низкий", "market": "Мосбиржа", "currency": "RUB"},

    # Криптовалюты
    "Биткоин (BTC-USD)": {"ticker": "BTC-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто", "currency": "USD"},
    "Эфириум (ETH-USD)": {"ticker": "ETH-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто", "currency": "USD"},

    # Валюты
    "Доллар США (USDRUB)": {"ticker": "USDRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},
    "Евро (EURRUB)": {"ticker": "EURRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},
    "Китайский юань (CNYRUB)": {"ticker": "CNYRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный", "currency": "RUB"},

    # Драгметаллы
    "Золото (GC=F)": {"ticker": "GC=F", "type": "Металл", "risk": "Низкий", "market": "Сырье", "currency": "USD"},
    "Серебро (SI=F)": {"ticker": "SI=F", "type": "Металл", "risk": "Средний", "market": "Сырье", "currency": "USD"},
    "Платина (PL=F)": {"ticker": "PL=F", "type": "Металл", "risk": "Средний", "market": "Сырье", "currency": "USD"},
}

# --- Интерфейс ---
tab1, tab2, tab3 = st.tabs(["📈 График и данные", "💼 Сбор портфеля", "🤖 Прогноз и анализ рисков"])

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
# Вкладка 2: Конкретный портфель по бюджету (исправлена ошибка)
# ================================
with tab2:
    st.subheader("💼 Конкретный портфель по вашему бюджету")
    st.info("Алгоритм рассчитает точное количество активов для покупки по текущим рыночным ценам. Для USD-активов конвертация происходит по текущему курсу.")

    budget = st.number_input("Введите бюджет (₽)", min_value=1000, value=100000, step=5000)
    risk_profile = st.selectbox("Профиль риска", ["Консервативный (Низкий риск)", "Сбалансированный (Средний риск)", "Агрессивный (Максимальный доход)"])

    if st.button("Собрать идеальный портфель"):
        with st.spinner("Загружаем актуальные цены для расчета..."):
            # Список тикеров, которые участвуют в портфелях
            tickers_to_check = ["GC=F", "BTC-USD", "NVDA", "SBER", "USDRUB=X", "CNYRUB=X", "SU26227RMFS4"]
            
            # Инициализируем цены нулями, чтобы избежать ошибок типа None/NaN
            prices = {t: 0.0 for t in tickers_to_check}
            usd_rub_price = 90.0 # Заглушка

            # Получаем курс доллара
            usd_rub_data = yf.download("USDRUB=X", period="1d", progress=False)
            if not usd_rub_data.empty:
                if isinstance(usd_rub_data.columns, pd.MultiIndex): usd_rub_data.columns = usd_rub_data.columns.droplevel(1)
                usd_rub_price = float(usd_rub_data['Close'].iloc[-1])

            # Получаем цены на все активы портфеля
            for t in tickers_to_check:
                try:
                    if t == "SBER" or t == "SU26227RMFS4": # Российские активы
                        df = get_moex_data(t, 2)
                        if df is not None and not df.empty:
                            val = df['Close'].iloc[-1]
                            prices[t] = float(val) if not pd.isna(val) else 0.0
                    else: # Остальные (идут в USD, включая металлы и крипту)
                        df = yf.download(t, period="1d", progress=False)
                        if not df.empty:
                            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
                            val = df['Close'].iloc[-1]
                            prices[t] = float(val) if not pd.isna(val) else 0.0
                except:
                    prices[t] = 0.0 # Если произошла ошибка загрузки

            # Логика распределения
            asset_alloc = {}
            if risk_profile == "Консервативный (Низкий риск)":
                asset_alloc = {
                    "Золото (GC=F)": 0.25,
                    "ОФЗ (SU26227RMFS4)": 0.25,
                    "Доллар США (USDRUB)": 0.20,
                    "Китайский юань (CNYRUB)": 0.15,
                    "Сбербанк (SBER)": 0.10,
                    "Биткоин (BTC-USD)": 0.05
                }
            elif risk_profile == "Сбалансированный (Средний риск)":
                asset_alloc = {
                    "Золото (GC=F)": 0.15,
                    "ОФЗ (SU26227RMFS4)": 0.15,
                    "Доллар США (USDRUB)": 0.15,
                    "Китайский юань (CNYRUB)": 0.10,
                    "Сбербанк (SBER)": 0.15,
                    "NVIDIA (NVDA)": 0.15,
                    "Биткоин (BTC-USD)": 0.15
                }
            else: # Агрессивный
                asset_alloc = {
                    "Биткоин (BTC-USD)": 0.25,
                    "NVIDIA (NVDA)": 0.20,
                    "Сбербанк (SBER)": 0.15,
                    "Золото (GC=F)": 0.10,
                    "Доллар США (USDRUB)": 0.10,
                    "Китайский юань (CNYRUB)": 0.10,
                    "ОФЗ (SU26227RMFS4)": 0.10,
                }

            st.success(f"✅ Портфель под ваш бюджет ({risk_profile}) готов! Вот что нужно купить прямо сейчас:")

            # Сбор данных для таблицы
            table_data = []
            total_spent_rub = 0

            for name, ratio in asset_alloc.items():
                alloc_rub = int(budget * ratio)
                ticker_code = name.split("(")[1].replace(")", "")
                price = float(prices.get(ticker_code, 0.0))
                
                qty_to_buy = 0.0
                actual_cost_rub = 0.0
                display_qty = "Нет данных"
                display_price = f"-"

                # Если цена больше 0, рассчитываем кол-во
                if price > 0.0:
                    display_price = f"{price:.2f}"
                    meta = next((v for k, v in ASSETS_DB.items() if v["ticker"] == ticker_code), None)
                    
                    if meta and meta["currency"] == "USD":
                        # Для USD-активов переводим рубли в доллары
                        alloc_usd = alloc_rub / usd_rub_price
                        qty_to_buy = alloc_usd / price
                        actual_cost_usd = qty_to_buy * price
                        actual_cost_rub = actual_cost_usd * usd_rub_price

                        # Проверяем, чтобы число было конечным (не NaN и не Inf)
                        if not np.isfinite(qty_to_buy): qty_to_buy = 0.0
                        
                        if "BTC" in ticker_code:
                            display_qty = f"{qty_to_buy:.6f} BTC"
                        elif "GC=F" in ticker_code or "SI=F" in ticker_code or "PL=F" in ticker_code:
                            display_qty = f"{qty_to_buy:.4f} унц."
                        else:
                            display_qty = f"{qty_to_buy:.4f} шт."
                    else:
                        # Для RUB-активов
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
                    "Цена за ед.": display_price,
                    "Нужно купить": display_qty,
                    "Факт. затраты (₽)": f"{actual_cost_rub:,.2f}"
                })

            # Выводим таблицу
            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

            # Остаток бюджета
            leftover = budget - total_spent_rub
            if leftover > 0:
                st.info(f"💰 Остаток нераспределенного бюджета: **{leftover:,.0f} ₽**. Вы можете добавить его в любой из активов или оставить на комиссию брокера.")
            else:
                st.success("🎯 Бюджет использован практически полностью!")
            
            st.caption("❗ Внимание: расчет сделан алгоритмически по текущим рыночным ценам. Учитывайте комиссию брокера и возможное изменение котировок в момент совершения сделки.")

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
                        for date_str, pct in worst_days.items():
                            date_formatted = pd.to_datetime(date_str).strftime("%d.%m.%Y")
                            st.write(f"📉 {date_formatted}: падение на **{pct:.2%}**. *Примечание: часто это связано с выходом плохой отчетности или макроэкономическими новостями.*")
                    else:
                        st.write("Нет значительных падений.")

                    st.markdown("**Дни самого сильного роста:**")
                    if not best_days.empty:
                        for date_str, pct in best_days.items():
                            date_formatted = pd.to_datetime(date_str).strftime("%d.%m.%Y")
                            st.write(f"📈 {date_formatted}: рост на **{pct:.2%}**. *Примечание: обычно происходит на позитивных новостях или сильных квартальных отчетах.*")
                    else:
                        st.write("Нет значительных ростов.")
                else:
                    st.write("Недостаточно данных для анализа.")

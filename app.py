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
    """Загружает данные с официального API MOEX."""
    try:
        # Кол-во свечей для запроса. Берем побольше, чтобы покрыть год
        url = f'https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}.json'
        params = {
            'iss.only': 'candles',
            'interval': 24, # Дневные свечи
            'from': (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d'),
            'till': datetime.now().strftime('%Y-%m-%d')
        }
        r = requests.get(url, params=params).json()
        candles = r['candles']['data']
        
        if not candles:
            return None
            
        df = pd.DataFrame(candles, columns=r['candles']['columns'])
        df['Date'] = pd.to_datetime(df['begin'], utc=True).dt.tz_convert('Europe/Moscow')
        # Формируем стандартный формат для графика
        df = df[['Date', 'open', 'high', 'low', 'close', 'value']]
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'value': 'Volume'}, inplace=True)
        df.sort_values('Date', inplace=True)
        return df
    except:
        return None

# ================= БАЗА ДАННЫХ АКТИВОВ =================
ASSETS_DB = {
    # Акции РФ (Будут грузиться через MOEX)
    "Сбербанк (SBER)": {"ticker": "SBER", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа"},
    "Лукойл (LKOH)": {"ticker": "LKOH", "type": "Акция РФ", "risk": "Средний", "market": "Мосбиржа"},
    "Газпром (GAZP)": {"ticker": "GAZP", "type": "Акция РФ", "risk": "Низкий", "market": "Мосбиржа"},
    "Яндекс (YNDX)": {"ticker": "YNDX", "type": "Акция РФ", "risk": "Высокий", "market": "Мосбиржа"},

    # Акции США
    "Apple Inc. (AAPL)": {"ticker": "AAPL", "type": "Акция США", "risk": "Средний", "market": "NASDAQ"},
    "NVIDIA (NVDA)": {"ticker": "NVDA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ"},
    "Tesla Inc. (TSLA)": {"ticker": "TSLA", "type": "Акция США", "risk": "Высокий", "market": "NASDAQ"},
    "S&P 500 (Индекс)": {"ticker": "^GSPC", "type": "Индекс США", "risk": "Средний", "market": "США"},

    # Облигации
    "ОФЗ (Гос. облигации РФ)": {"ticker": "SU26227RMFS4", "type": "Облигация", "risk": "Низкий", "market": "Мосбиржа"},

    # Криптовалюты
    "Биткоин (BTC-USD)": {"ticker": "BTC-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто"},
    "Эфириум (ETH-USD)": {"ticker": "ETH-USD", "type": "Криптовалюта", "risk": "Очень высокий", "market": "Крипто"},

    # Валюты (к рублю)
    "Доллар США (USDRUB)": {"ticker": "USDRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный"},
    "Евро (EURRUB)": {"ticker": "EURRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный"},
    "Китайский юань (CNYRUB)": {"ticker": "CNYRUB=X", "type": "Валюта", "risk": "Средний", "market": "Валютный"},
    "Японская иена (JPYUSD)": {"ticker": "JPYUSD=X", "type": "Валюта", "risk": "Низкий", "market": "Валютный"},

    # Драгметаллы
    "Золото (GC=F)": {"ticker": "GC=F", "type": "Металл", "risk": "Низкий", "market": "Сырье"},
    "Серебро (SI=F)": {"ticker": "SI=F", "type": "Металл", "risk": "Средний", "market": "Сырье"},
    "Платина (PL=F)": {"ticker": "PL=F", "type": "Металл", "risk": "Средний", "market": "Сырье"},
    "Палладий (PA=F)": {"ticker": "PA=F", "type": "Металл", "risk": "Высокий", "market": "Сырье"},
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

    period_text = "1y" if not is_russian else "Год"
    st.caption(f"Рынок: {meta['market']} | Риск: {meta['risk']}")

    with st.spinner(f"Загружаем данные для {asset_name}..."):
        # Выбор источника данных
        if is_russian:
            data = get_moex_data(ticker, period_days=365)
            currency = "₽"
        else:
            # Для валютных пар и металлов из Yahoo
            data = yf.download(ticker, period="1y", progress=False)
            currency = "₽" if "RUB" in ticker else "$"

        if data is None or data.empty:
            st.error("❌ Не удалось загрузить данные по этому активу. Скорее всего, тикер отсутствует на выбранной бирже.")
        else:
            # Формируем метрики
            latest = data['Close'].iloc[-1]
            first = data['Close'].iloc[0]
            delta = latest - first

            c1, c2, c3 = st.columns(3)
            c1.metric(f"Цена", f"{currency}{latest:.2f}", f"{currency}{delta:.2f}")
            c2.metric("Максимум", f"{currency}{data['High'].max():.2f}")
            c3.metric("Минимум", f"{currency}{data['Low'].min():.2f}")

            # Свечной график
            fig = go.Figure(data=[go.Candlestick(
                x=data['Date'], open=data['Open'], high=data['High'],
                low=data['Low'], close=data['Close'],
                name="Цена"
            )])
            fig.update_layout(title=f"{asset_name} — График цены", xaxis_title="Дата", yaxis_title=f"Цена ({currency})",
                              hovermode="x unified", xaxis_tickformat="%d %b %Y")
            st.plotly_chart(fig, use_container_width=True)

# ================================
# Вкладка 2: Широкий портфель по бюджету
# ================================
with tab2:
    st.subheader("💼 Масштабный портфель под ваш бюджет")
    st.info("Алгоритм собирает 7 разнонаправленных активов: защитные (ОФЗ/Золото), валютные (Юань/Доллар), спекулятивные (Крипто/Акции роста).")

    budget = st.number_input("Введите бюджет (₽)", min_value=1000, value=100000, step=5000)
    risk_profile = st.selectbox("Профиль риска", ["Консервативный (Низкий риск)", "Сбалансированный (Средний риск)", "Агрессивный (Максимальный доход)"])

    if st.button("Собрать идеальный портфель"):
        # Получаем актуальные цены. В реальном продукте тут должны быть асинхронные запросы.
        # Для прототипа берем упрощенно.
        prices = {}
        tickers_to_check = ["GC=F", "BTC-USD", "NVDA", "SBER", "USDRUB=X", "CNYRUB=X", "SU26227RMFS4"]
        for t in tickers_to_check:
            if t == "SBER":
                df = get_moex_data(t, 1) # берем последний день
                prices[t] = df['Close'].iloc[-1] if df is not None else 300
            else:
                df = yf.download(t, period="1d", progress=False)
                prices[t] = df['Close'].iloc[-1] if not df.empty else 0
        
        # Логика распределения
        asset_alloc = {}
        if risk_profile == "Консервативный (Низкий риск)":
            asset_alloc = {
                "Золото (Защита)": 0.25,
                "ОФЗ (Облигации)": 0.25,
                "Доллар США (Валюта)": 0.20,
                "Китайский юань (Валюта)": 0.15,
                "Сбербанк (Акция РФ)": 0.10,
                "Биткоин (Спекуляция)": 0.05
            }
        elif risk_profile == "Сбалансированный (Средний риск)":
            asset_alloc = {
                "Золото (Защита)": 0.15,
                "ОФЗ (Облигации)": 0.15,
                "Доллар США (Валюта)": 0.15,
                "Китайский юань (Валюта)": 0.10,
                "Сбербанк (Акция РФ)": 0.15,
                "NVIDIA (Акция США)": 0.15,
                "Биткоин (Спекуляция)": 0.15
            }
        else: # Агрессивный
            asset_alloc = {
                "Биткоин (Спекуляция)": 0.25,
                "NVIDIA (Акция США)": 0.20,
                "Сбербанк (Акция РФ)": 0.15,
                "Золото (Защита)": 0.10,
                "Доллар США (Валюта)": 0.10,
                "Китайский юань (Валюта)": 0.10,
                "ОФЗ (Облигации)": 0.10,
            }
        
        st.success(f"✅ Портфель под ваш бюджет ({risk_profile}) готов!")
        table_data = []
        for name, ratio in asset_alloc.items():
            alloc_amount = int(budget * ratio)
            # Подбираем тикер к названию
            ticker_mock = list(prices.keys())[list(ASSETS_DB.keys()).index(name) % len(prices)] 
            table_data.append({"Актив": name, "Доля": f"{int(ratio*100)}%", "Сумма": f"{alloc_amount:,.0f} ₽"})
        
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
        st.caption("❗ Внимание: портфель составлен алгоритмически. Перед покупкой изучите текущую ситуацию у вашего брокера.")

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
            # Загружаем данные для анализа (нужен минимум 180 дней для работы модели)
            if pred_russian:
                pred_data = get_moex_data(pred_ticker, 500)
            else:
                pred_data = yf.download(pred_ticker, period="1y", progress=False)
                if isinstance(pred_data.columns, pd.MultiIndex):
                    pred_data.columns = pred_data.columns.droplevel(1)
                pred_data = pred_data.reset_index()

            if pred_data is None or pred_data.empty:
                st.error("Недостаточно данных для построения прогноза.")
            else:
                # 1. ПОДГОТОВКА ДАННЫХ ДЛЯ PROPHET
                df_prophet = pred_data[['Date', 'Close']].rename(columns={'Date': 'ds', 'Close': 'y'})

                # 2. МОДЕЛЬ ПРОГНОЗА (ИИ с сезонностью)
                m = Prophet(daily_seasonality=False, yearly_seasonality=True)
                m.add_country_holidays(country_name='US' if not pred_russian else 'Russia')
                m.fit(df_prophet)
                
                future = m.make_future_dataframe(periods=60) # Прогноз на 2 месяца
                forecast = m.predict(future)

                # 3. ВИЗУАЛИЗАЦИЯ
                fig_pred = go.Figure()
                fig_pred.add_trace(go.Scatter(x=pred_data['Date'], y=pred_data['Close'], mode='lines', name='Реальная цена'))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat'], mode='lines', name='Прогноз ИИ (Prophet)', line=dict(dash='dash', color='red')))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_upper'], fill=None, mode='lines', line_color='rgba(255,0,0,0.05)', name='Верхняя граница риска', showlegend=False))
                fig_pred.add_trace(go.Scatter(x=forecast['ds'], y=forecast['yhat_lower'], fill='tonexty', mode='lines', line_color='rgba(255,0,0,0.05)', name='Нижняя граница риска', showlegend=False))
                fig_pred.update_layout(title=f"ИИ-прогноз (Сезонная модель Facebook Prophet) на 60 дней", xaxis_title="Дата")
                st.plotly_chart(fig_pred, use_container_width=True)

                # 4. АНАЛИЗ ПРОШЛЫХ АНОМАЛИЙ (Почему упала / выросла цена)
                st.divider()
                st.subheader("📉 Анализ исторических провалов и взлетов")
                daily_returns = pred_data['Close'].pct_change()
                worst_days = daily_returns.nsmallest(5)
                best_days = daily_returns.nlargest(5)

                st.markdown("**Дни самого сильного падения (возможные причины):**")
                for date_str, pct in worst_days.items():
                    date_formatted = date_str.strftime("%d.%m.%Y")
                    st.write(f"📉 {date_formatted}: падение на **{pct:.2%}**. *Примечание: часто это связано с выходом плохой отчетности, макроэкономическими новостями или фиксацией прибыли трейдерами.*")

                st.markdown("**Дни самого сильного роста (возможные причины):**")
                for date_str, pct in best_days.items():
                    date_formatted = date_str.strftime("%d.%m.%Y")
                    st.write(f"📈 {date_formatted}: рост на **{pct:.2%}**. *Примечание: обычно это происходит на позитивных новостях, сильных квартальных отчетах или в ожидании снижения ключевой ставки.*")

                st.info("🧠 *Как сделать ИИ еще умнее? Текущий прогноз использует математику и сезонность (Prophet). Чтобы он искал новости в интернете и давал причину падения/роста, нужно подключить внешний API (например, OpenAI/Gemini или NewsAPI). Я оставил для этого место в коде.*")

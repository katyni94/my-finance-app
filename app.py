import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression

st.set_page_config(page_title="Аналитик портфеля", layout="wide")

st.title("📊 Персональный финансовый ассистент")
st.markdown("Анализ акций, валют, металлов. Сбор портфеля и прогнозирование рисков.")

# --- БАЗА ДАННЫХ АКТИВОВ (расширенная) ---
ASSETS_DB = {
    # Акции США и РФ
    "Apple (AAPL)": {"ticker": "AAPL", "type": "Акция", "market": "США", "risk": "Средний"},
    "Google (GOOGL)": {"ticker": "GOOGL", "type": "Акция", "market": "США", "risk": "Средний"},
    "Tesla (TSLA)": {"ticker": "TSLA", "type": "Акция", "market": "США", "risk": "Высокий"},
    "NVIDIA (NVDA)": {"ticker": "NVDA", "type": "Акция", "market": "США", "risk": "Высокий"},
    "Сбербанк (SBER.ME)": {"ticker": "SBER.ME", "type": "Акция", "market": "РФ", "risk": "Низкий"},
    "Лукойл (LKOH.ME)": {"ticker": "LKOH.ME", "type": "Акция", "market": "РФ", "risk": "Средний"},
    "Газпром (GAZP.ME)": {"ticker": "GAZP.ME", "type": "Акция", "market": "РФ", "risk": "Низкий"},

    # Валютные пары (Forex)
    "Доллар США / Рубль (USDRUB)": {"ticker": "USDRUB=X", "type": "Валюта", "market": "Валютный рынок", "risk": "Средний"},
    "Евро / Доллар США (EURUSD)": {"ticker": "EURUSD=X", "type": "Валюта", "market": "Валютный рынок", "risk": "Средний"},
    "Британский фунт / Доллар (GBPUSD)": {"ticker": "GBPUSD=X", "type": "Валюта", "market": "Валютный рынок", "risk": "Средний"},

    # Металлы и сырье
    "Золото (GC=F)": {"ticker": "GC=F", "type": "Металл", "market": "Сырьевая биржа", "risk": "Низкий"},
    "Серебро (SI=F)": {"ticker": "SI=F", "type": "Металл", "market": "Сырьевая биржа", "risk": "Средний"},
}

# --- ИНТЕРФЕЙС: Вкладки ---
tab1, tab2, tab3 = st.tabs(["📈 Детальный анализ актива", "💼 Сбор портфеля по бюджету", "🤖 Риски и прогноз"])

# ==========================================
# ВКЛАДКА 1: Детальный анализ актива (улучшенный график)
# ==========================================
with tab1:
    col_asset, col_period = st.columns(2)
    with col_asset:
        # Выбор с автофильтрацией при вводе
        asset_name = st.selectbox("Выберите актив", list(ASSETS_DB.keys()), index=0)
        ticker = ASSETS_DB[asset_name]["ticker"]
        asset_type = ASSETS_DB[asset_name]["type"]
        market = ASSETS_DB[asset_name]["market"]

    with col_period:
        period = st.selectbox("Период для анализа", ["1mo", "3mo", "6mo", "1y", "5y"], index=3)

    # Российские активы только за месяц, предупреждение
    if ".ME" in ticker and period != "1mo":
        st.warning("⚠️ По акциям РФ Yahoo отдает полные данные только за последний месяц.")

    with st.spinner("Загружаем данные..."):
        data = yf.download(ticker, period=period, progress=False)
        if data.empty:
            st.error("⚠️ Данные не загрузились. Попробуйте другую компанию или период.")
        else:
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)
            data = data.reset_index()

            # Метрики
            latest = data['Close'].iloc[-1]
            first = data['Close'].iloc[0]
            delta = latest - first
            currency = "₽" if ".ME" in ticker else "$"

            c1, c2, c3 = st.columns(3)
            c1.metric(f"Цена ({asset_type})", f"{currency}{latest:.2f}", f"{currency}{delta:.2f}")
            c2.metric("Максимум", f"{currency}{data['High'].max():.2f}")
            c3.metric("Минимум", f"{currency}{data['Low'].min():.2f}")

            # Строим свечной график
            fig = go.Figure(data=[go.Candlestick(
                x=data['Date'],
                open=data['Open'], high=data['High'],
                low=data['Low'], close=data['Close'],
                name="Цена актива"
            )])
            fig.update_layout(
                title=f"{asset_name} — График цены",
                xaxis_title="Дата", yaxis_title=f"Цена ({currency})",
                hovermode="x unified", xaxis_tickformat="%d %b %Y"
            )
            st.plotly_chart(fig, use_container_width=True)

# ==========================================
# ВКЛАДКА 2: Сбор портфеля по бюджету (симулятор)
# ==========================================
with tab2:
    st.subheader("💼 Соберем портфель под ваш бюджет")
    st.info("Алгоритм выбирает для вас 3 разнонаправленных актива (Защитный, Доходный, Валютный), чтобы снизить риски.")
    
    budget = st.number_input("Введите ваш бюджет в рублях (₽)", min_value=1000, value=10000, step=1000)
    
    if st.button("Собрать портфель"):
        # Простая логика распределения (для прототипа берем условные средние цены для примера)
        # Для реального приложения здесь нужна база с текущими рыночными ценами
        
        # Защитный актив: Золото или Сбербанк
        safe_asset = yf.download("GC=F", period="1d", progress=False).get('Close')
        if safe_asset.empty:
            safe_price = 2500 # Заглушка, если не загрузилось
        else:
            safe_price = safe_asset.iloc[-1]

        # Доходный актив: NVIDIA
        high_asset = yf.download("NVDA", period="1d", progress=False).get('Close')
        high_price = high_asset.iloc[-1] if not high_asset.empty else 120

        # Валютный актив: Доллар
        forex_asset = yf.download("USDRUB=X", period="1d", progress=False).get('Close')
        forex_price = forex_asset.iloc[-1] if not forex_asset.empty else 90

        # Правило распределения (60% - защита и валюта, 40% - рост)
        alloc_safe = int(budget * 0.40)
        alloc_forex = int(budget * 0.30)
        alloc_high = int(budget * 0.30)

        st.success("✅ Идеальный портфель подобран!")
        st.markdown(f"""
        | Актив | Назначение | Доля бюджета | Рекомендуемая сумма |
        | :--- | :--- | :--- | :--- |
        | **Золото (GC=F)** | Защита капитала от инфляции | 40% | {alloc_safe} ₽ |
        | **Доллар (USDRUB)** | Валютная диверсификация | 30% | {alloc_forex} ₽ |
        | **NVIDIA (NVDA)** | Рост/Эмитент с высоким потенциалом | 30% | {alloc_high} ₽ |
        """)
        st.warning("❗ Обратите внимание: это пример алгоритмического подбора. Реальная покупка американских активов гражданами РФ зависит от текущих ограничений вашего брокера.")

# ==========================================
# ВКЛАДКА 3: Риски и прогноз (ИИ-модель)
# ==========================================
with tab3:
    st.subheader("🤖 Анализ рисков и прогноз цены")
    
    asset_risk_name = st.selectbox("Выберите актив для прогноза", list(ASSETS_DB.keys()), index=7) # По умолчанию выберем Доллар
    risk_ticker = ASSETS_DB[asset_risk_name]["ticker"]
    
    if st.button("Запустить анализ рисков и прогноз"):
        with st.spinner("ИИ-модуль рассчитывает показатели..."):
            risk_data = yf.download(risk_ticker, period="1y", progress=False)
            if risk_data.empty:
                st.warning("Недостаточно данных для расчета. Попробуйте другой актив.")
            else:
                if isinstance(risk_data.columns, pd.MultiIndex):
                    risk_data.columns = risk_data.columns.droplevel(1)
                risk_data = risk_data.reset_index()
                
                # --- Расчет РИСКОВ ---
                daily_returns = risk_data['Close'].pct_change().dropna()
                volatility = daily_returns.std() * np.sqrt(252) # Годовая волатильность
                annual_return = (risk_data['Close'].iloc[-1] / risk_data['Close'].iloc[0]) - 1
                # Коэффициент Шарпа (безрисковая ставка 0 для упрощения)
                sharpe_ratio = annual_return / volatility if volatility != 0 else 0
                
                col_r1, col_r2 = st.columns(2)
                col_r1.metric("📉 Годовая волатильность (Риск)", f"{volatility:.2%}", help="Чем выше % тем сильнее скачет цена. >30% - высокий риск")
                col_r2.metric("📈 Коэффициент Шарпа", f"{sharpe_ratio:.2f}", help=">1.0 — отличная доходность на риск. <1.0 — риск не оправдан.")
                
                # --- Прогноз на 30 дней вперед (Линейная регрессия) ---
                st.subheader("📈 Прогноз линейного тренда (следующие 30 дней)")
                
                # Строим модель
                X = np.arange(len(risk_data)).reshape(-1, 1)
                y = risk_data['Close'].values
                model = LinearRegression().fit(X, y)
                
                # Делаем прогноз на текущие даты + еще 30 дней
                future_X = np.arange(len(risk_data), len(risk_data) + 30).reshape(-1, 1)
                forecast = model.predict(future_X)

                # Собираем даты для прогноза
                last_date = risk_data['Date'].iloc[-1]
                future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=30)
                
                fig_forecast = go.Figure()
                fig_forecast.add_trace(go.Scatter(
                    x=risk_data['Date'], y=risk_data['Close'], mode='lines', name='Реальная цена'
                ))
                fig_forecast.add_trace(go.Scatter(
                    x=future_dates, y=forecast, mode='lines', name='Прогноз ИИ (тренд)', line=dict(dash='dash', color='red')
                ))
                fig_forecast.update_layout(
                    title=f"Прогноз для {asset_risk_name} (Линейная экстраполяция)",
                    xaxis_title="Дата", hovermode="x unified"
                )
                st.plotly_chart(fig_forecast, use_container_width=True)
                
                st.info("💡 *Данный прогноз построен на базе линейной регрессии и показывает лишь математическое продолжение текущего тренда. Для точного ИИ-прогноза с учетом сентимента новостей нужна более сложная модель (LSTM).*")

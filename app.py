import streamlit as st
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Мой финансовый дашборд", layout="wide")
st.title("📈 Биржевой дашборд")

# --- Словарь компаний ---
COMPANIES = {
    "Apple Inc. (AAPL)": "AAPL",
    "Google / Alphabet (GOOGL)": "GOOGL",
    "Microsoft (MSFT)": "MSFT",
    "Tesla Inc. (TSLA)": "TSLA",
    "NVIDIA Corp. (NVDA)": "NVDA",
    "Amazon.com Inc. (AMZN)": "AMZN",
    "Сбербанк (SBER.ME)": "SBER.ME",
    "Лукойл (LKOH.ME)": "LKOH.ME",
    "Газпром (GAZP.ME)": "GAZP.ME"
}

# --- Интерфейс выбора ---
col_company, col_period, col_chart = st.columns([2, 1, 1])

with col_company:
    selected_name = st.selectbox("📌 Выберите компанию", list(COMPANIES.keys()), index=0)
    ticker = COMPANIES[selected_name]

with col_period:
    period = st.selectbox("📅 Период", ["1mo", "3mo", "6mo", "1y", "5y"], index=3)

with col_chart:
    chart_type = st.selectbox("📊 Тип графика", ["Линейный", "Свечной"], index=0)

# --- Корректировка периода для российских акций ---
if ".ME" in ticker and period != "1mo":
    st.info("ℹ️ По российским акциям Yahoo отдает данные только за месяц. Период изменен на '1mo'.")
    period = "1mo"

# --- Загрузка данных ---
with st.spinner(f"Загружаю данные для {selected_name}..."):
    try:
        data = yf.download(ticker, period=period, progress=False)
        if data.empty:
            st.error("Данные не найдены. Попробуйте позже.")
            st.stop()

        # Обработка колонок
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)
        data = data.reset_index()

        # Валюты и метрики
        is_russian = ".ME" in ticker
        currency = "₽" if is_russian else "$"

        # Метрики
        latest_close = data['Close'].iloc[-1]
        delta_price = latest_close - data['Close'].iloc[0]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Текущая цена", f"{currency}{latest_close:.2f}", delta=f"{currency}{delta_price:.2f}")
        c2.metric("📈 Максимум", f"{currency}{data['High'].max():.2f}")
        c3.metric("📉 Минимум", f"{currency}{data['Low'].min():.2f}")
        c4.metric("📊 Объём", f"{data['Volume'].iloc[-1]:,.0f}")

        # --- Построение графика (Выбор между линейным и свечным) ---
        if chart_type == "Линейный":
            # Скользящая средняя
            data['MA20'] = data['Close'].rolling(window=20).mean()
            fig = px.line(data, x="Date", y=["Close", "MA20"], 
                          title=f"{selected_name} — Динамика цены")
            fig.for_each_trace(lambda t: t.update(name="Цена" if t.name == "Close" else "Средняя (20 дней)"))
        else:
            # Свечной график (Candlestick)
            fig = go.Figure(data=[go.Candlestick(
                x=data['Date'],
                open=data['Open'], high=data['High'],
                low=data['Low'], close=data['Close'],
                name="Свечной график"
            )])
            fig.update_layout(title=f"{selected_name} — Свечной график цены")

        # Оформление графика
        fig.update_layout(
            xaxis_title="Дата",
            yaxis_title=f"Цена ({currency})",
            hovermode="x unified",
            xaxis_tickformat="%d %b %Y",
            paper_bgcolor="rgba(0,0,0,0)", # Прозрачный фон для красоты
            plot_bgcolor="rgba(0,0,0,0)"
        )
        
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Ошибка: {e}")
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Произошла неожиданная ошибка: {e}")

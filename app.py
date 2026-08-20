import streamlit as st
import yfinance as yf
import plotly.express as px
import pandas as pd

# Настройка страницы
st.set_page_config(page_title="Мой финансовый дашборд", layout="wide")

st.title("📈 Мой финансовый дашборд")

# --- Словарь компаний: Название для пользователя -> Код тикера для программы ---
# Вы можете добавлять сюда любые компании
COMPANIES = {
    "Apple Inc. (AAPL)": "AAPL",
    "Google (Alphabet) (GOOGL)": "GOOGL",
    "Microsoft Corp. (MSFT)": "MSFT",
    "Tesla Inc. (TSLA)": "TSLA",
    "Сбербанк (SBER.ME)": "SBER.ME",
    "Лукойл (LKOH.ME)": "LKOH.ME",
    "Газпром (GAZP.ME)": "GAZP.ME"
}

# --- Блок выбора (В две колонки для красоты) ---
col_company, col_period = st.columns(2)

with col_company:
    # Выпадающий список вместо текстового поля
    selected_name = st.selectbox(
        "Выберите компанию", 
        list(COMPANIES.keys()),
        index=0 # По умолчанию выбираем первый пункт (Apple)
    )
    ticker = COMPANIES[selected_name] # Получаем код тикера

with col_period:
    # Выбор периода
    period = st.selectbox(
        "Период данных", 
        ["1mo", "3mo", "6mo", "1y", "5y"], # 1 месяц, 3, 6, 1 год, 5 лет
        index=3 # По умолчанию 1 год ("1y")
    )

# --- Загрузка и обработка данных ---
with st.spinner(f"Загружаю данные для {selected_name}..."):
    try:
        data = yf.download(ticker, period=period, progress=False)

        if data.empty:
            st.error(f"Не удалось найти данные для {selected_name}. Попробуйте позже.")
        else:
            # Определяем валюту (если в тикере есть .ME, значит это Россия/Рубль)
            currency = "₽" if ".ME" in ticker else "$"

            # Исправление мультиуровневых колонок (yfinance)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            # Превращаем индекс в колонку Date
            data = data.reset_index()

            # --- ДОБАВЛЕНИЕ СКОЛЬЗЯЩЕЙ СРЕДНЕЙ (MA20) ---
            # Считаем среднюю цену закрытия за последние 20 дней
            data['MA20'] = data['Close'].rolling(window=20).mean()

            # --- Блок цифр (Метрики) ---
            c1, c2, c3, c4 = st.columns(4)
            
            # Берем значения из самого последнего дня
            latest_close = data['Close'].iloc[-1]
            latest_volume = data['Volume'].iloc[-1]
            
            c1.metric("Последняя цена", f"{currency}{latest_close:.2f}")
            c2.metric("Максимум", f"{currency}{data['High'].max():.2f}")
            c3.metric("Минимум", f"{currency}{data['Low'].min():.2f}")
            c4.metric("Объём", f"{latest_volume:,.0f}")

            # --- Блок графика с двумя линиями (Цена и средняя) ---
            fig = px.line(
                data,
                x="Date",
                y=["Close", "MA20"], # Рисуем две линии
                title=f"{selected_name} - цена закрытия и скользящая средняя (20 дней)"
            )
            
            # Настраиваем подписи, чтобы было понятно на графике
            fig.update_layout(
                xaxis_title="Дата",
                yaxis_title=f"Цена ({currency})",
                legend_title="Линии",
                hovermode="x unified" # Удобный всплывающий подсказки при наведении
            )
            
            # Переименовываем линии в легенде для красоты
            fig.for_each_trace(lambda t: t.update(name="Цена закрытия" if t.name == "Close" else "Средняя (20 дней)"))

            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Произошла ошибка при загрузке данных: {e}")

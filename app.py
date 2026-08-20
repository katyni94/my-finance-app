import streamlit as st
import yfinance as yf
import plotly.express as px
import pandas as pd

# Настройка страницы
st.set_page_config(page_title="Мой финансовый дашборд", layout="wide")

st.title("📈 Мой финансовый дашборд")

# --- Словарь компаний (расширенный список) ---
# Название для пользователя -> Код тикера
COMPANIES = {
    # Международные гиганты (работают стабильно)
    "Apple Inc. (AAPL)": "AAPL",
    "Google / Alphabet (GOOGL)": "GOOGL",
    "Microsoft (MSFT)": "MSFT",
    "Tesla Inc. (TSLA)": "TSLA",
    "NVIDIA Corp. (NVDA)": "NVDA",
    "Advanced Micro Devices (AMD)": "AMD",
    "Amazon.com Inc. (AMZN)": "AMZN",
    "Meta Platforms (META)": "META",
    "Netflix Inc. (NFLX)": "NFLX",
    "Toyota Motor (TM)": "TM",
    
    # Российские компании (Yahoo отдает по ним данные только за месяц, учтено в коде)
    "Сбербанк (SBER.ME) - только за месяц": "SBER.ME",
    "Лукойл (LKOH.ME) - только за месяц": "LKOH.ME",
    "Газпром (GAZP.ME) - только за месяц": "GAZP.ME"
}

# --- Блок выбора (Компания и Период) ---
col_company, col_period = st.columns(2)

with col_company:
    selected_name = st.selectbox("Выберите компанию", list(COMPANIES.keys()), index=0)
    ticker = COMPANIES[selected_name]

with col_period:
    # Пользователь выбирает период, но мы можем переопределить его для России
    user_period = st.selectbox("Период данных", ["1mo", "3mo", "6mo", "1y", "5y"], index=3)
    period = user_period

# --- Проверка для российских тикеров ---
# Принудительно ставим 1 месяц для российских акций, чтобы данные точно прогрузились
is_russian = ".ME" in ticker
if is_russian and period != "1mo":
    st.warning("⚠️ Обратите внимание: Yahoo Finance отдает данные по российским акциям только за последний месяц. Период автоматически изменен на '1mo'.")
    period = "1mo"

# --- Загрузка и обработка данных ---
with st.spinner(f"Загружаю данные для {selected_name}..."):
    try:
        data = yf.download(ticker, period=period, progress=False)

        # Проверка на пустой ответ от сервера (например, если тикер недоступен)
        if data.empty:
            st.error(f"❌ Не удалось найти данные для {selected_name}. Проверьте интернет или попробуйте другую компанию.")
            st.stop() # Останавливаем выполнение скрипта, чтобы не было ошибок ниже

        # Исправление мультиуровневых колонок yfinance
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.droplevel(1)

        # Превращаем индекс даты в обычную колонку для графика
        data = data.reset_index()

        # --- ДОБАВЛЕНИЕ СКОЛЬЗЯЩЕЙ СРЕДНЕЙ (MA20) ---
        data['MA20'] = data['Close'].rolling(window=20).mean()

        # --- Блок цифр (Метрики с подробным описанием на русском) ---
        # Определяем валюту
        currency = "₽" if is_russian else "$"
        
        # Берем данные для расчетов
        latest_close = data['Close'].iloc[-1]
        first_close = data['Close'].iloc[0]
        delta_price = latest_close - first_close # Изменение цены с начала периода
        latest_volume = data['Volume'].iloc[-1]

        c1, c2, c3, c4 = st.columns(4)
        
        c1.metric(
            label="💰 Текущая цена (Close)",
            value=f"{currency}{latest_close:.2f}",
            delta=f"{currency}{delta_price:.2f}", # Показывает зеленую/красную стрелку роста
            delta_color="normal",
            help="Цена закрытия последней торговой сессии. Зеленая стрелка означает, что цена выросла с начала выбранного периода."
        )
        
        c2.metric(
            label="📈 Максимум за период (High)",
            value=f"{currency}{data['High'].max():.2f}",
            help="Самая высокая цена, которой достигла акция за выбранный промежуток времени."
        )
        
        c3.metric(
            label="📉 Минимум за период (Low)",
            value=f"{currency}{data['Low'].min():.2f}",
            help="Самая низкая цена, которой достигла акция за выбранный промежуток времени."
        )
        
        c4.metric(
            label="📊 Объём торгов (Volume)",
            value=f"{latest_volume:,.0f}",
            help="Количество акций, которые были куплены и проданы за последнюю торговую сессию. Чем выше объём, тем интереснее акция для трейдеров."
        )

        # --- Блок графика ---
        fig = px.line(
            data,
            x="Date",
            y=["Close", "MA20"],
            title=f"{selected_name} — Динамика цены и скользящая средняя (20 дней)",
            labels={"value": f"Цена ({currency})", "Date": "Дата"}
        )
        
        # Настройка оформления графика
        fig.update_layout(
            legend_title="Графики",
            hovermode="x unified", # Удобно: при наведении показывает цену сразу по двум линиям
            xaxis_tickformat="%d %b %Y" # Красивый формат даты (день месяц год)
        )
        
        # Переименование линий в легенде для полной ясности
        fig.for_each_trace(lambda t: t.update(
            name="Цена закрытия" if t.name == "Close" else "Средняя цена (20 дней)"
        ))

        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Произошла неожиданная ошибка: {e}")

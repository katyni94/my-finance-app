import streamlit as st
import yfinance as yf
import plotly.express as px
import pandas as pd

# Настройка страницы (широкий формат и название)
st.set_page_config(page_title="Мой финансовый дашборд", layout="wide")

st.title("📈 Мой финансовый дашборд")

# Поле ввода тикера
ticker = st.text_input("Введите тикер (например, AAPL, GOOGL, SBER.ME)", "AAPL")

# Запускаем логику, если тикер введен
if ticker:
    # Показывает спиннер загрузки, пока данные скачиваются
    with st.spinner(f"Загружаю данные для {ticker}..."):
        try:
            # Скачиваем данные за последний год
            data = yf.download(ticker, period="1y", progress=False)

            # Если данных нет (например, неправильный тикер)
            if data.empty:
                st.error(f"Не удалось найти данные для тикера {ticker}. Проверьте написание.")
            else:
                # ================= ВАЖНОЕ ИСПРАВЛЕНИЕ =================
                # yfinance часто возвращает мультиуровневые колонки ('Close', 'AAPL').
                # Мы убираем лишний уровень, чтобы осталась просто 'Close'.
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.droplevel(1)

                # Сбрасываем индекс, чтобы Дата (Date) стала обычной колонкой
                # Это нужно, чтобы передать её в Plotly (x="Date")
                data = data.reset_index()
                # =====================================================

                # --- Блок цифр (Метрики) ---
                # Создаём 4 колонки для цифр сверху
                c1, c2, c3, c4 = st.columns(4)
                
                c1.metric(
                    "Последняя цена", 
                    f"${data['Close'].iloc[-1]:.2f}"  # Берём самое последнее значение цены закрытия
                )
                c2.metric(
                    "Максимум", 
                    f"${data['High'].max():.2f}"     # Максимальная цена за период
                )
                c3.metric(
                    "Минимум", 
                    f"${data['Low'].min():.2f}"      # Минимальная цена за период
                )
                c4.metric(
                    "Объём", 
                    f"{data['Volume'].iloc[-1]:,.0f}" # Последний объём торгов
                )

                # --- Блок графика ---
                # Теперь ошибки не будет, потому что 'Close' существует, а 'Date' - это обычная колонка
                fig = px.line(
                    data,
                    x="Date",      # Ось X: Дата
                    y="Close",     # Ось Y: Цена закрытия
                    title=f"{ticker} - цена закрытия"
                )
                
                # Отображаем график на всю ширину контейнера
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            # Если произошла любая другая ошибка (например, проблемы с интернетом)
            st.error(f"Произошла ошибка при загрузке данных: {e}")

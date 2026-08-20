import yfinance as yf
import streamlit as st
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Финансовый дашборд", layout="wide")
st.title("📈 Мой финансовый дашборд")

ticker = st.text_input("Введите тикер (например, AAPL, GOOGL, SBER.ME)", "AAPL")

@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        data = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=False)
        return data
    except Exception as e:
        st.error(f"Ошибка загрузки: {e}")
        return None

if ticker:
    data = load_data(ticker)
    
    if data is not None and not data.empty:
        close = data['Close']
        # Извлекаем скалярные значения с помощью .item()
        last_close = close.iloc[-1].item()
        last_high = data['High'].iloc[-1].item()
        last_low = data['Low'].iloc[-1].item()
        last_volume = data['Volume'].iloc[-1].item()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Последняя цена", f"${last_close:.2f}")
        col2.metric("Максимум", f"${last_high:.2f}")
        col3.metric("Минимум", f"${last_low:.2f}")
        col4.metric("Объём", f"{last_volume:,.0f}")
        
        fig = px.line(data, x=data.index, y="Close", title=f"{ticker} — цена закрытия")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Тикер не найден или данные недоступны. Попробуйте другой тикер (например, AAPL, GOOGL, SBER.ME).")
else:
    st.info("Введите тикер в поле выше.")

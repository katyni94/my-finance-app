import yfinance as yf
import streamlit as st
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Финансовый дашборд", layout="wide")
st.title("📈 Мой финансовый дашборд")

ticker = st.text_input("Введите тикер (например, AAPL, GOOGL, SBER.ME)", "AAPL")

try:
    data = yf.download(ticker, period="6mo", interval="1d", auto_adjust=False)
    
    if not data.empty:
        col1, col2, col3, col4 = st.columns(4)
        close = data['Close']
        last_close = close.iloc[-1]
        
        col1.metric("Последняя цена", f"${last_close:.2f}")
        col2.metric("Максимум", f"${data['High'].iloc[-1]:.2f}")
        col3.metric("Минимум", f"${data['Low'].iloc[-1]:.2f}")
        col4.metric("Объём", f"{data['Volume'].iloc[-1]:,.0f}")
        
        fig = px.line(data, x=data.index, y="Close", title=f"{ticker} — цена закрытия")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Тикер не найден. Попробуйте другой.")
except Exception as e:
    st.error(f"Ошибка: {e}")
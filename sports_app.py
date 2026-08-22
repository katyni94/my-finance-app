import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import time

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
st.title("⚽ Спортивный аналитик — поиск валуйных ставок")

# ---- Загрузка API-ключа ----
api_key = st.secrets.get("FOOTBALL_API_KEY")
if not api_key:
    api_key = st.text_input("Введите ваш API-ключ Football-Data.org", type="password")
    if not api_key:
        st.warning("Получите ключ на football-data.org и введите его.")
        st.stop()

# ---- Кэширование данных (на 5 минут) ----
@st.cache_data(ttl=300)
def fetch_matches_and_standings(comp_id, api_key):
    """
    Загружает матчи и таблицу за один вызов (с кэшированием).
    Возвращает (matches, team_stats) или None при ошибке.
    """
    headers = {'X-Auth-Token': api_key}
    
    # 1. Загружаем матчи
    url_matches = f"https://api.football-data.org/v4/competitions/{comp_id}/matches"
    params = {
        'status': 'SCHEDULED',
        'dateFrom': datetime.now().strftime('%Y-%m-%d'),
        'dateTo': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    }
    resp = requests.get(url_matches, headers=headers, params=params)
    if resp.status_code == 429:
        # Ошибка лимита запросов
        raise Exception("429")
    if resp.status_code != 200:
        raise Exception(f"Ошибка API: {resp.status_code} - {resp.text}")
    data = resp.json()
    matches = data.get('matches', [])
    
    # 2. Загружаем таблицу
    table_url = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
    table_resp = requests.get(table_url, headers=headers)
    if table_resp.status_code == 429:
        raise Exception("429")
    team_stats = {}
    if table_resp.status_code == 200:
        table_data = table_resp.json()
        standings = table_data.get('standings', [])
        if standings:
            rows = standings[0].get('table', [])
            for row in rows:
                name = row['team']['name']
                team_stats[name] = {
                    'points': row['points'],
                    'played': row['playedGames'],
                    'goals_for': row['goalsFor'],
                    'goals_against': row['goalsAgainst'],
                }
    return matches, team_stats

# ---- Выбор турнира ----
competitions = {
    "АПЛ (Англия)": 2021,
    "Ла Лига (Испания)": 2014,
    "Бундеслига (Германия)": 2002,
    "Серия А (Италия)": 2019,
    "Лига 1 (Франция)": 2015,
    "Лига Чемпионов": 2001,
}
comp_name = st.selectbox("Выберите турнир", list(competitions.keys()))
comp_id = competitions[comp_name]

show_only_value = st.checkbox("Показать только матчи с валуйными ставками", value=False)

# ---- Загрузка ----
if st.button("🚀 Найти лучшие ставки"):
    with st.spinner("Анализируем матчи и коэффициенты..."):
        try:
            matches, team_stats = fetch_matches_and_standings(comp_id, api_key)
        except Exception as e:
            if "429" in str(e):
                st.error("⏳ Превышен лимит запросов к API (10 в минуту). Подождите 30 секунд и попробуйте снова.")
            else:
                st.error(f"Ошибка: {e}")
            st.stop()
        
        if not matches:
            st.info("Нет предстоящих матчей в этом турнире.")
            st.stop()
        
        if not team_stats:
            st.warning("⚠️ Не удалось загрузить турнирную таблицу. Использую упрощённый расчёт на основе средних голов.")
        
        # Анализ каждого матча
        results = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            
            h = team_stats.get(home, {})
            a = team_stats.get(away, {})
            
            if not h or not a:
                prob_home = 0.40
                prob_draw = 0.30
                prob_away = 0.30
            else:
                h_ppg = h.get('points', 0) / max(1, h.get('played', 1))
                a_ppg = a.get('points', 0) / max(1, a.get('played', 1))
                h_gd = (h.get('goals_for', 0) - h.get('goals_against', 0)) / max(1, h.get('played', 1))
                a_gd = (a.get('goals_for', 0) - a.get('goals_against', 0)) / max(1, a.get('played', 1))
                home_boost = 0.15
                
                home_rating = h_ppg + h_gd + home_boost
                away_rating = a_ppg + a_gd
                total_rating = home_rating + away_rating
                
                if total_rating > 0:
                    prob_home = home_rating / total_rating
                    prob_away = away_rating / total_rating
                else:
                    prob_home = prob_away = 0.4
                prob_draw = 1 - prob_home - prob_away
                
                prob_home = max(0.05, min(0.85, prob_home))
                prob_away = max(0.05, min(0.85, prob_away))
                prob_draw = max(0.05, min(0.50, prob_draw))
                total = prob_home + prob_draw + prob_away
                prob_home /= total
                prob_draw /= total
                prob_away /= total
            
            odds = match.get('odds', {})
            home_odds = odds.get('homeWin')
            away_odds = odds.get('awayWin')
            draw_odds = odds.get('draw')
            
            def value_found(prob, odds):
                if prob is None or odds is None or odds <= 0:
                    return False
                return prob > 1/odds
            
            best_bet = None
            best_value = 0
            if home_odds and prob_home > 0 and value_found(prob_home, home_odds):
                value = prob_home - 1/home_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{home} (кф {home_odds:.2f})"
            if draw_odds and prob_draw > 0 and value_found(prob_draw, draw_odds):
                value = prob_draw - 1/draw_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"Ничья (кф {draw_odds:.2f})"
            if away_odds and prob_away > 0 and value_found(prob_away, away_odds):
                value = prob_away - 1/away_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{away} (кф {away_odds:.2f})"
            
            if best_bet:
                stars = "⭐" * min(5, int(best_value * 20) + 1)
                recommendation = f"{stars} {best_bet}"
            else:
                recommendation = "⏳ Нет явных валуйных ставок"
            
            results.append({
                "Дата": match_date,
                "Хозяева": home,
                "Гости": away,
                "Победа хозяев": prob_home,
                "Ничья": prob_draw,
                "Победа гостей": prob_away,
                "Рекомендация": recommendation,
                "Кф хозяев": home_odds,
                "Кф ничья": draw_odds,
                "Кф гости": away_odds,
                "value": best_value,
                "is_value": best_value > 0
            })
        
        if show_only_value:
            results = [r for r in results if r['is_value']]
            if not results:
                st.info("Нет матчей с валуйными ставками в выбранном турнире.")
                st.stop()
        
        st.success(f"✅ Найдено {len(results)} матчей")
        
        df = pd.DataFrame(results)
        df['Дата'] = pd.to_datetime(df['Дата'])
        dates = sorted(df['Дата'].unique())
        
        for date in dates:
            st.subheader(f"📅 {date.strftime('%d %B %Y')}")
            day_matches = df[df['Дата'] == date]
            
            for _, row in day_matches.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 3])
                    
                    with col1:
                        st.markdown(f"**{row['Хозяева']}**")
                        st.progress(row['Победа хозяев'], text=f"Победа: {row['Победа хозяев']:.0%}")
                    
                    with col2:
                        st.markdown("**vs**")
                        st.progress(row['Ничья'], text=f"Ничья: {row['Ничья']:.0%}")
                    
                    with col3:
                        st.markdown(f"**{row['Гости']}**")
                        st.progress(row['Победа гостей'], text=f"Победа: {row['Победа гостей']:.0%}")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown(f"**Рекомендация:** {row['Рекомендация']}")
                    with col_b:
                        odds_str = f"Кф: {row['Кф хозяев']:.2f} / {row['Кф ничья']:.2f} / {row['Кф гости']:.2f}" if row['Кф хозяев'] else "Коэффициенты не загружены"
                        st.caption(odds_str)
                    
                    st.divider()
        
        if st.checkbox("Показать график сравнения вероятностей"):
            plot_df = df.copy()
            plot_df['match'] = plot_df['Хозяева'] + " vs " + plot_df['Гости']
            fig = go.Figure()
            for outcome in ['Победа хозяев', 'Ничья', 'Победа гостей']:
                fig.add_trace(go.Bar(
                    x=plot_df['match'],
                    y=plot_df[outcome],
                    name=outcome,
                    text=[f"{v:.0%}" for v in plot_df[outcome]],
                    textposition='inside'
                ))
            fig.update_layout(
                barmode='group',
                yaxis_title='Вероятность',
                xaxis_tickangle=-45,
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
        
        st.caption("""
        **Интерпретация:**
        - Прогресс-бары показывают вероятность каждого исхода.
        - ⭐ — чем больше звёзд, тем выше потенциальная ценность ставки.
        - Если вы видите одинаковые вероятности для всех матчей, значит турнирная таблица не загрузилась — попробуйте другой турнир.
        """)

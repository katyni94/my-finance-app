import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
st.title("⚽ Спортивный аналитик — прототип")

# ---- Загрузка API-ключа ----
api_key = st.secrets.get("FOOTBALL_API_KEY")
if not api_key:
    api_key = st.text_input("Введите ваш API-ключ Football-Data.org", type="password")
    if not api_key:
        st.warning("Получите ключ на football-data.org и введите его.")
        st.stop()

# --- Выбор турнира ---
competition_id = st.selectbox(
    "Выберите турнир",
    options=[
        {"name": "АПЛ (Англия)", "id": 2021},
        {"name": "Ла Лига (Испания)", "id": 2014},
        {"name": "Бундеслига (Германия)", "id": 2002},
        {"name": "Серия А (Италия)", "id": 2019},
        {"name": "Лига 1 (Франция)", "id": 2015},
        {"name": "Лига Чемпионов", "id": 2001},
    ],
    format_func=lambda x: x["name"]
)

if st.button("Загрузить матчи и сделать прогноз"):
    with st.spinner("Загружаем данные..."):
        headers = {'X-Auth-Token': api_key}
        
        # --- 1. Получаем предстоящие матчи ---
        url = f"https://api.football-data.org/v4/competitions/{competition_id['id']}/matches"
        params = {
            'status': 'SCHEDULED',
            'dateFrom': datetime.now().strftime('%Y-%m-%d'),
            'dateTo': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            st.error(f"Ошибка загрузки: {response.status_code} - {response.text}")
            st.stop()
        
        data = response.json()
        matches = data.get('matches', [])
        if not matches:
            st.info("Нет предстоящих матчей в выбранном турнире.")
            st.stop()import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
st.title("⚽ Спортивный аналитик — поиск валуйных ставок")

# ---- Загрузка API-ключа ----
api_key = st.secrets.get("FOOTBALL_API_KEY")
if not api_key:
    api_key = st.text_input("Введите ваш API-ключ Football-Data.org", type="password")
    if not api_key:
        st.warning("Получите ключ на football-data.org и введите его.")
        st.stop()

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

# ---- Загрузка ----
if st.button("🚀 Найти лучшие ставки"):
    with st.spinner("Анализируем матчи и коэффициенты..."):
        headers = {'X-Auth-Token': api_key}
        
        # 1. Загружаем предстоящие матчи на 7 дней
        url = f"https://api.football-data.org/v4/competitions/{comp_id}/matches"
        params = {
            'status': 'SCHEDULED',
            'dateFrom': datetime.now().strftime('%Y-%m-%d'),
            'dateTo': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        }
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            st.error(f"Ошибка API: {resp.status_code} - {resp.text}")
            st.stop()
        data = resp.json()
        matches = data.get('matches', [])
        if not matches:
            st.info("Нет предстоящих матчей в этом турнире.")
            st.stop()
        
        # 2. Загружаем турнирную таблицу для статистики
        table_url = f"https://api.football-data.org/v4/competitions/{comp_id}/standings"
        table_resp = requests.get(table_url, headers=headers)
        team_stats = {}
        if table_resp.status_code == 200:
            table_data = table_resp.json()
            standings = table_data.get('standings', [])
            if standings:
                rows = standings[0].get('table', [])
                for row in rows:
                    name = row['team']['name']
                    team_stats[name] = {
                        'position': row['position'],
                        'points': row['points'],
                        'played': row['playedGames'],
                        'wins': row['won'],
                        'draws': row['draw'],
                        'losses': row['lost'],
                        'goals_for': row['goalsFor'],
                        'goals_against': row['goalsAgainst'],
                    }
        else:
            st.warning("Не удалось загрузить таблицу, прогноз будет менее точным.")

        # 3. Анализ каждого матча
        results = []
        match_data_for_plot = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            
            h = team_stats.get(home, {})
            a = team_stats.get(away, {})
            
            # --- Вычисляем силу команд ---
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
                "Победа хозяев": f"{prob_home:.0%}",
                "Ничья": f"{prob_draw:.0%}",
                "Победа гостей": f"{prob_away:.0%}",
                "Рекомендация": recommendation,
                "Кф хозяев": f"{home_odds:.2f}" if home_odds else "—",
                "Кф ничья": f"{draw_odds:.2f}" if draw_odds else "—",
                "Кф гости": f"{away_odds:.2f}" if away_odds else "—",
                "value": best_value
            })
            
            match_data_for_plot.append({
                "match": f"{home} vs {away}",
                "Победа хозяев": prob_home,
                "Ничья": prob_draw,
                "Победа гостей": prob_away
            })

        # --- Вывод ---
        st.success(f"✅ Найдено {len(results)} матчей")
        
        # Сортируем по ценности
        df = pd.DataFrame(results)
        df = df.sort_values('value', ascending=False).drop('value', axis=1)
        
        # Стилизация таблицы: цветные вероятности
        def color_prob(val):
            if isinstance(val, str) and '%' in val:
                p = float(val.replace('%', '')) / 100
                if p > 0.55:
                    return 'background-color: #d4edda'  # зелёный
                elif p > 0.40:
                    return 'background-color: #fff3cd'  # жёлтый
                else:
                    return 'background-color: #f8d7da'  # красный
            return ''
        
        st.dataframe(
            df.style.applymap(color_prob, subset=['Победа хозяев', 'Ничья', 'Победа гостей']),
            use_container_width=True,
            hide_index=True
        )
        
        # ---- График вероятностей ----
        if match_data_for_plot:
            st.subheader("📊 Сравнение вероятностей по матчам")
            plot_df = pd.DataFrame(match_data_for_plot)
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
        - Зелёный фон — высокая вероятность (≥55%), жёлтый — средняя, красный — низкая.
        - ⭐ — чем больше звёзд, тем выше потенциальная ценность ставки.
        - Ставка считается валуйной, если наша оценка вероятности выше, чем подразумевает коэффициент букмекера.
        """)

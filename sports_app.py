import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
st.title("⚽ Спортивный аналитик — прототип")

# --- Ввод API-ключа ---
api_key = st.secrets.get("FOOTBALL_API_KEY")
if not api_key:
    api_key = st.text_input("Введите ваш API-ключ", type="6ae3050890b64e31927722642996172f")

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
            st.stop()
        
        # --- 2. Получаем статистику команд (последние 5 матчей) ---
        # Для простоты используем данные по таблице (позиция, очки)
        table_url = f"https://api.football-data.org/v4/competitions/{competition_id['id']}/standings"
        table_response = requests.get(table_url, headers=headers)
        if table_response.status_code == 200:
            table_data = table_response.json()
            standings = table_data.get('standings', [])
            if standings:
                # Берём первую таблицу (обычно это общая)
                table_rows = standings[0].get('table', [])
                team_stats = {}
                for row in table_rows:
                    team_name = row['team']['name']
                    team_stats[team_name] = {
                        'position': row['position'],
                        'points': row['points'],
                        'played': row['playedGames'],
                        'wins': row['won'],
                        'draws': row['draw'],
                        'losses': row['lost']
                    }
            else:
                team_stats = {}
        else:
            team_stats = {}
            st.warning("Не удалось загрузить таблицу, буду использовать только предстоящие матчи.")

        # --- 3. Формируем прогнозы (простая модель) ---
        predictions = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate']
            
            # Если есть статистика, считаем силу команд
            home_info = team_stats.get(home, {})
            away_info = team_stats.get(away, {})
            
            # Простой индикатор: соотношение очков за игру
            home_pts_per_game = home_info.get('points', 0) / max(1, home_info.get('played', 1))
            away_pts_per_game = away_info.get('points', 0) / max(1, away_info.get('played', 1))
            
            # Вероятность победы хозяев (приблизительно)
            if home_pts_per_game + away_pts_per_game > 0:
                prob_home = home_pts_per_game / (home_pts_per_game + away_pts_per_game)
            else:
                prob_home = 0.4  # дефолт
            
            # Ограничим разумными пределами
            prob_home = max(0.1, min(0.9, prob_home))
            prob_away = 1 - prob_home
            prob_draw = 0.3  # упрощённо
            
            # Сравниваем с букмекерскими коэффициентами (если есть)
            odds = match.get('odds', {})
            if odds:
                home_odds = odds.get('homeWin')
                away_odds = odds.get('awayWin')
                draw_odds = odds.get('draw')
            else:
                home_odds = away_odds = draw_odds = None
            
            # Рекомендация
            recommendation = "⚖️ Нет данных"
            if home_odds and prob_home > 1/home_odds:
                recommendation = f"✅ Ставка на {home} (кэф {home_odds})"
            elif away_odds and prob_away > 1/away_odds:
                recommendation = f"✅ Ставка на {away} (кэф {away_odds})"
            elif draw_odds and prob_draw > 1/draw_odds:
                recommendation = f"✅ Ставка на ничью (кэф {draw_odds})"
            else:
                recommendation = "⏳ Нет явных валуйных ставок"
            
            predictions.append({
                "Дата": match_date[:10],
                "Хозяева": home,
                "Гости": away,
                "Прогноз на победу хозяев": f"{prob_home:.0%}",
                "Прогноз на ничью": f"{prob_draw:.0%}",
                "Прогноз на победу гостей": f"{prob_away:.0%}",
                "Рекомендация": recommendation
            })

        # --- 4. Вывод ---
        st.success(f"✅ Загружено {len(predictions)} матчей.")
        df = pd.DataFrame(predictions)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.caption("⚠️ Это прототип. Модель упрощённая и не учитывает множество факторов (травмы, форма, мотивация и т.д.). Используйте для развлечения.")

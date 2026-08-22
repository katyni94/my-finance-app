import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import re

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
st.title("⚽ Спортивный аналитик — поиск валуйных ставок")

# ---- Словарь флагов для лиг ----
FLAGS = {
    "АПЛ (Англия)": "🇬🇧",
    "Ла Лига (Испания)": "🇪🇸",
    "Бундеслига (Германия)": "🇩🇪",
    "Серия А (Италия)": "🇮🇹",
    "Лига 1 (Франция)": "🇫🇷",
    "Лига Чемпионов": "🏆"
}

# ---- Функция для упрощения названий команд ----
def clean_team_name(name):
    name = re.sub(r'\s+FC$', '', name)
    name = re.sub(r'\s+AFC$', '', name)
    return name

# ---- Загрузка API-ключей ----
football_key = st.secrets.get("FOOTBALL_API_KEY")
if not football_key:
    football_key = st.text_input("Введите API-ключ Football-Data.org", type="password")
    if not football_key:
        st.warning("Ключ нужен для расписания матчей.")
        st.stop()

odds_key = st.secrets.get("ODDS_API_KEY")
if not odds_key:
    odds_key = st.text_input("Введите API-ключ TheOddsAPI (опционально, для коэффициентов)", type="password")
    if not odds_key:
        st.info("Можно работать без коэффициентов или вводить их вручную.")

# ---- Кэширование данных ----
@st.cache_data(ttl=300)
def fetch_matches_and_standings(comp_id, api_key):
    headers = {'X-Auth-Token': api_key}
    url_matches = f"https://api.football-data.org/v4/competitions/{comp_id}/matches"
    params = {
        'status': 'SCHEDULED',
        'dateFrom': datetime.now().strftime('%Y-%m-%d'),
        'dateTo': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    }
    resp = requests.get(url_matches, headers=headers, params=params)
    if resp.status_code == 429:
        raise Exception("429")
    if resp.status_code != 200:
        raise Exception(f"Ошибка API: {resp.status_code} - {resp.text}")
    data = resp.json()
    matches = data.get('matches', [])
    
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
                    'points': row['points'],
                    'played': row['playedGames'],
                    'goals_for': row['goalsFor'],
                    'goals_against': row['goalsAgainst'],
                }
    return matches, team_stats

@st.cache_data(ttl=300)
def fetch_all_matches(api_key):
    headers = {'X-Auth-Token': api_key}
    url = "https://api.football-data.org/v4/matches"
    params = {
        'status': 'SCHEDULED',
        'dateFrom': datetime.now().strftime('%Y-%m-%d'),
        'dateTo': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    }
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 429:
        raise Exception("429")
    if resp.status_code != 200:
        raise Exception(f"Ошибка API: {resp.status_code} - {resp.text}")
    data = resp.json()
    return data.get('matches', [])

# ---- Функция для получения коэффициентов через TheOddsAPI ----
def fetch_odds_from_odds_api(api_key, sport='soccer', region='eu', market='h2h'):
    """
    Загружает коэффициенты для всех матчей на сегодня.
    Возвращает словарь: (home_team, away_team) -> {home_win, draw, away_win}
    """
    if not api_key:
        return {}
    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            'apiKey': api_key,
            'regions': region,
            'markets': market,
            'dateFormat': 'iso'
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            st.warning(f"Не удалось загрузить коэффициенты: {resp.status_code}")
            return {}
        data = resp.json()
        odds_map = {}
        for event in data:
            home = event.get('home_team')
            away = event.get('away_team')
            if not home or not away:
                continue
            # Ищем первую БК (можно выбрать конкретную позже)
            bookmakers = event.get('bookmakers', [])
            if not bookmakers:
                continue
            # Берём первую БК
            bm = bookmakers[0]
            markets = bm.get('markets', [])
            for m in markets:
                if m.get('key') == 'h2h':
                    outcomes = m.get('outcomes', [])
                    h_odds = None
                    d_odds = None
                    a_odds = None
                    for o in outcomes:
                        if o.get('name') == home:
                            h_odds = o.get('price')
                        elif o.get('name') == away:
                            a_odds = o.get('price')
                        elif o.get('name') == 'Draw':
                            d_odds = o.get('price')
                    odds_map[(home, away)] = {
                        'home_win': h_odds,
                        'draw': d_odds,
                        'away_win': a_odds,
                        'bookmaker': bm.get('title', 'Неизвестная БК')
                    }
                    break
        return odds_map
    except Exception as e:
        st.warning(f"Ошибка загрузки коэффициентов: {e}")
        return {}

# ---- Боковая панель ----
with st.sidebar:
    st.header("⚙️ Настройки")
    
    mode = st.radio(
        "Режим анализа",
        ["Один турнир", "Все турниры (экспериментальный)"],
        index=0
    )
    
    competitions = {
        "АПЛ (Англия)": 2021,
        "Ла Лига (Испания)": 2014,
        "Бундеслига (Германия)": 2002,
        "Серия А (Италия)": 2019,
        "Лига 1 (Франция)": 2015,
        "Лига Чемпионов": 2001,
    }
    
    if mode == "Один турнир":
        comp_name = st.selectbox("Выберите турнир", list(FLAGS.keys()))
        comp_id = competitions[comp_name]
        flag = FLAGS.get(comp_name, "⚽")
    else:
        comp_name = None
        comp_id = None
        flag = "🌍"
        st.caption("⚠️ В этом режиме турнирная таблица не загружается, прогноз менее точный.")
    
    show_only_value = st.checkbox("Показать только матчи с валуйными ставками", value=False)
    
    # Выбор источника коэффициентов
    odds_source = st.selectbox(
        "Источник коэффициентов",
        ["Автоматически (TheOddsAPI)", "Вводить вручную"],
        index=0
    )
    
    with st.expander("ℹ️ Как это работает"):
        st.markdown("""
        **Что такое валуйная ставка?**
        - Мы оцениваем вероятность победы хозяев, ничьей и победы гостей на основе статистики команд.
        - Если наша вероятность **выше**, чем подразумевает коэффициент букмекера (1/коэф), ставка **валуйная**.
        
        **Источники коэффициентов:**
        - TheOddsAPI — бесплатный ключ даёт 500 запросов/день.
        - Ручной ввод — вы сами вводите коэффициенты из любимой БК.
        """)

# ---- Основная кнопка ----
if st.button("🚀 Найти лучшие ставки"):
    with st.spinner("Анализируем матчи и коэффициенты..."):
        try:
            if mode == "Один турнир":
                matches, team_stats = fetch_matches_and_standings(comp_id, football_key)
            else:
                matches = fetch_all_matches(football_key)
                team_stats = {}
                st.info("🌍 Режим всех турниров: прогноз строится без турнирной таблицы.")
        except Exception as e:
            if "429" in str(e):
                st.error("⏳ Превышен лимит запросов к API (10 в минуту). Подождите 30 секунд и попробуйте снова.")
            else:
                st.error(f"Ошибка: {e}")
            st.stop()
        
        if not matches:
            st.info("Нет предстоящих матчей.")
            st.stop()
        
        # Загружаем коэффициенты, если выбран автоматический режим
        odds_data = {}
        if odds_source == "Автоматически (TheOddsAPI)" and odds_key:
            odds_data = fetch_odds_from_odds_api(odds_key)
            if odds_data:
                st.success(f"✅ Загружены коэффициенты для {len(odds_data)} матчей")
            else:
                st.warning("⚠️ Не удалось загрузить коэффициенты. Попробуйте ручной ввод.")
        
        results = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            
            home_clean = clean_team_name(home)
            away_clean = clean_team_name(away)
            
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
            
            # Получаем коэффициенты (из API или из ручного ввода)
            home_odds = None
            away_odds = None
            draw_odds = None
            bookmaker_name = "Неизвестная БК"
            
            if odds_source == "Автоматически (TheOddsAPI)" and odds_data:
                key = (home, away)
                if key in odds_data:
                    home_odds = odds_data[key]['home_win']
                    away_odds = odds_data[key]['away_win']
                    draw_odds = odds_data[key]['draw']
                    bookmaker_name = odds_data[key]['bookmaker']
                else:
                    # Попробуем поискать по очищенным названиям
                    for (h, a), val in odds_data.items():
                        if clean_team_name(h) == home_clean and clean_team_name(a) == away_clean:
                            home_odds = val['home_win']
                            away_odds = val['away_win']
                            draw_odds = val['draw']
                            bookmaker_name = val['bookmaker']
                            break
            
            # Если ручной ввод или нет коэффициентов, даём поля для ввода
            if odds_source == "Вводить вручную" or not (home_odds and away_odds and draw_odds):
                st.markdown(f"**Введите коэффициенты для {home_clean} vs {away_clean}:**")
                col_h, col_d, col_a = st.columns(3)
                with col_h:
                    home_odds = st.number_input(f"Победа {home_clean}", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key=f"h_{home}_{away}")
                with col_d:
                    draw_odds = st.number_input("Ничья", min_value=1.0, max_value=20.0, value=3.0, step=0.1, key=f"d_{home}_{away}")
                with col_a:
                    away_odds = st.number_input(f"Победа {away_clean}", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key=f"a_{home}_{away}")
                bookmaker_name = "Ручной ввод"
            
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
                    best_bet = f"{home_clean} (кф {home_odds:.2f})"
            if draw_odds and prob_draw > 0 and value_found(prob_draw, draw_odds):
                value = prob_draw - 1/draw_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"Ничья (кф {draw_odds:.2f})"
            if away_odds and prob_away > 0 and value_found(prob_away, away_odds):
                value = prob_away - 1/away_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{away_clean} (кф {away_odds:.2f})"
            
            if best_bet:
                stars = "⭐" * min(5, int(best_value * 20) + 1)
                recommendation = f"{stars} {best_bet}"
            else:
                recommendation = "⏳ Нет явных валуйных ставок"
            
            odds_available = home_odds is not None and away_odds is not None and draw_odds is not None
            if not odds_available:
                recommendation = "⚖️ Коэффициенты не загружены"
            
            results.append({
                "Дата": match_date,
                "Хозяева": home_clean,
                "Гости": away_clean,
                "Победа хозяев": prob_home,
                "Ничья": prob_draw,
                "Победа гостей": prob_away,
                "Рекомендация": recommendation,
                "Кф хозяев": home_odds,
                "Кф ничья": draw_odds,
                "Кф гости": away_odds,
                "Букмекер": bookmaker_name,
                "value": best_value,
                "is_value": best_value > 0 and odds_available
            })
        
        if show_only_value:
            results = [r for r in results if r['is_value']]
            if not results:
                st.info("Нет матчей с валуйными ставками.")
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
                    st.markdown(f"{flag} **{row['Хозяева']}** vs **{row['Гости']}**")
                    st.caption(f"Букмекер: {row['Букмекер']}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.progress(row['Победа хозяев'], text=f"Победа хозяев: {row['Победа хозяев']:.0%}")
                        if row['Кф хозяев']:
                            st.caption(f"Кф: {row['Кф хозяев']:.2f}")
                    with col2:
                        st.progress(row['Ничья'], text=f"Ничья: {row['Ничья']:.0%}")
                        if row['Кф ничья']:
                            st.caption(f"Кф: {row['Кф ничья']:.2f}")
                    with col3:
                        st.progress(row['Победа гостей'], text=f"Победа гостей: {row['Победа гостей']:.0%}")
                        if row['Кф гости']:
                            st.caption(f"Кф: {row['Кф гости']:.2f}")
                    
                    st.markdown(f"**Рекомендация:** {row['Рекомендация']}")
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
        - Коэффициенты могут быть загружены через TheOddsAPI или введены вручную.
        """)

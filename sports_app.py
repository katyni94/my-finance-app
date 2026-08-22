import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import re

# ---- Аутентификация ----
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.title("🔐 Вход в систему")
    username = st.text_input("Логин", placeholder="Введите логин (если требуется)")
    password = st.text_input("Пароль", type="password", placeholder="Введите пароль")
    if st.button("Войти"):
        correct_username = st.secrets.get("APP_USERNAME", "")
        correct_password = st.secrets.get("APP_PASSWORD", "")
        if not correct_password:
            st.error("Пароль не настроен в Secrets. Добавьте APP_PASSWORD.")
            return False
        if correct_username:
            if username == correct_username and password == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
        else:
            if password == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Неверный пароль")
    return False

# ---- Настройки страницы ----
st.set_page_config(page_title="Спортивный аналитик", layout="wide")
if not check_password():
    st.stop()

st.title("⚽ Спортивный аналитик — ИИ прогнозы + валуйные ставки")

# ---- Инициализация состояния ----
if 'last_request_time' not in st.session_state:
    st.session_state.last_request_time = None
if 'odds_request_count' not in st.session_state:
    st.session_state.odds_request_count = 0
if 'odds_request_date' not in st.session_state:
    st.session_state.odds_request_date = datetime.now().date()

def can_make_request(min_interval_seconds=30):
    if st.session_state.last_request_time is None:
        return True, 0
    elapsed = (datetime.now() - st.session_state.last_request_time).total_seconds()
    if elapsed >= min_interval_seconds:
        return True, 0
    return False, int(min_interval_seconds - elapsed)

def can_request_odds(limit=500):
    today = datetime.now().date()
    if today != st.session_state.odds_request_date:
        st.session_state.odds_request_count = 0
        st.session_state.odds_request_date = today
    if st.session_state.odds_request_count >= limit:
        return False, st.session_state.odds_request_count, limit
    return True, st.session_state.odds_request_count, limit

# ---- Словарь лиг Bet Better ----
BETBETTER_LEAGUES = {
    "АПЛ (Англия)": "soccer/epl",
    "Ла Лига (Испания)": "soccer/la-liga",
    "Бундеслига (Германия)": "soccer/bundesliga",
    "Серия А (Италия)": "soccer/serie-a",
    "Лига 1 (Франция)": "soccer/ligue-1",
    "Лига Чемпионов": "soccer/world-cup",
}

# ---- Функция для запроса ИИ-прогнозов от Bet Better ----
@st.cache_data(ttl=900)
def fetch_betbetter_predictions(league_slug, min_probability=0):
    try:
        url = f"https://betbetter.world/{league_slug}/picks.aspx?format=json"
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'betbetter-mcp/1.0 (+https://betbetter.world/api)'
        }
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            st.warning(f"Bet Better API вернул ошибку: {response.status_code}")
            return []
        data = response.json()
        picks = data.get('picks', [])
        if min_probability > 0:
            picks = [p for p in picks if p.get('modelProbabilityPct', 0) >= min_probability]
        return picks
    except Exception as e:
        st.warning(f"Ошибка при запросе к Bet Better API: {e}")
        return []

# ---- Флаги и утилиты ----
FLAGS = {
    "АПЛ (Англия)": "🇬🇧",
    "Ла Лига (Испания)": "🇪🇸",
    "Бундеслига (Германия)": "🇩🇪",
    "Серия А (Италия)": "🇮🇹",
    "Лига 1 (Франция)": "🇫🇷",
    "Лига Чемпионов": "🏆"
}

def clean_team_name(name):
    name = re.sub(r'\s+FC$', '', name)
    name = re.sub(r'\s+AFC$', '', name)
    return name

# ---- Загрузка ключей ----
football_key = st.secrets.get("FOOTBALL_API_KEY")
if not football_key:
    football_key = st.text_input("Введите API-ключ Football-Data.org", type="password")
    if not football_key:
        st.warning("Ключ нужен для автоматического режима.")
        st.stop()

odds_key = st.secrets.get("ODDS_API_KEY")
if not odds_key:
    odds_key = st.text_input("Введите API-ключ TheOddsAPI (опционально)", type="password")
    if not odds_key:
        st.info("Для ручного режима ключ не нужен.")

# ---- Кэшируемые функции (автоматический режим) ----
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

# ---- Функция для загрузки коэффициентов (автоматический режим) ----
def fetch_odds_from_odds_api(api_key, sport='soccer', region='eu', market='h2h'):
    if not api_key:
        return {}
    can_request, count, limit = can_request_odds()
    if not can_request:
        st.warning(f"⚠️ Дневной лимит TheOddsAPI ({limit}) исчерпан. (Сделано {count} запросов)")
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
        st.session_state.odds_request_count += 1
        odds_map = {}
        for event in data:
            home = event.get('home_team')
            away = event.get('away_team')
            if not home or not away:
                continue
            bookmakers = event.get('bookmakers', [])
            if not bookmakers:
                continue
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
        ["Автоматический (турниры)", "Ручной ввод (любые команды)"],
        index=0
    )
    
    if mode == "Автоматический (турниры)":
        comp_name = st.selectbox("Выберите турнир", list(FLAGS.keys()))
        comp_id = {
            "АПЛ (Англия)": 2021,
            "Ла Лига (Испания)": 2014,
            "Бундеслига (Германия)": 2002,
            "Серия А (Италия)": 2019,
            "Лига 1 (Франция)": 2015,
            "Лига Чемпионов": 2001,
        }[comp_name]
        flag = FLAGS.get(comp_name, "⚽")
        league_slug = BETBETTER_LEAGUES.get(comp_name)
        if league_slug:
            st.info("🤖 ИИ-прогнозы от Bet Better будут использоваться для этого турнира.")
        else:
            st.warning("⚠️ Для этой лиги нет ИИ-прогнозов от Bet Better. Будет использована статистическая модель.")
    else:
        comp_name = None
        comp_id = None
        flag = "✏️"
        st.caption("Введите любые команды и свои оценки вероятностей.")
    
    show_only_value = st.checkbox("Показать только матчи с валуйными ставками", value=False)
    
    odds_source = st.selectbox(
        "Источник коэффициентов (для авт. режима)",
        ["Автоматически (TheOddsAPI)", "Вводить вручную"],
        index=0
    )
    
    with st.expander("ℹ️ Как это работает"):
        st.markdown("""
        **🤖 ИИ-прогнозы от Bet Better:**
        - Бесплатный сервис, который на основе машинного обучения даёт вероятность победы для каждой команды.
        - Прогнозы доступны для топ-лиг (АПЛ, Ла Лига, Бундеслига, Серия А, Лига 1, Лига Чемпионов).
        - Если ИИ-прогноз доступен, он используется вместо статистической модели.
        
        **📊 Коэффициенты:**
        - Автоматически загружаются через TheOddsAPI (если есть ключ и данные).
        - Если автоматическая загрузка не удалась, появляются поля для ручного ввода.
        - Вы можете ввести коэффициенты из своей БК или пропустить этот шаг.
        
        **Ручной режим:**
        - Введите любые команды и свои оценки вероятностей.
        - Приложение сравнит вашу оценку с коэффициентами и покажет валуйность.
        """)

# ---- Основная логика ----
if st.button("🚀 Анализировать"):
    # ---- Ручной режим ----
    if mode == "Ручной ввод (любые команды)":
        st.subheader("✏️ Введите данные матча")
        with st.form("manual_form"):
            home = st.text_input("Хозяева", value="Команда А")
            away = st.text_input("Гости", value="Команда Б")
            st.markdown("**Коэффициенты букмекера (опционально):**")
            col_h_odd, col_d_odd, col_a_odd = st.columns(3)
            with col_h_odd:
                home_odd = st.number_input("Победа хозяев", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key="odd_h")
            with col_d_odd:
                draw_odd = st.number_input("Ничья", min_value=1.0, max_value=20.0, value=3.0, step=0.1, key="odd_d")
            with col_a_odd:
                away_odd = st.number_input("Победа гостей", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key="odd_a")
            
            st.markdown("**Ваша оценка вероятности (в процентах):**")
            col_h_prob, col_d_prob, col_a_prob = st.columns(3)
            with col_h_prob:
                prob_h = st.number_input("Победа хозяев %", min_value=0, max_value=100, value=40, step=1, key="prob_h")
            with col_d_prob:
                prob_d = st.number_input("Ничья %", min_value=0, max_value=100, value=30, step=1, key="prob_d")
            with col_a_prob:
                prob_a = st.number_input("Победа гостей %", min_value=0, max_value=100, value=30, step=1, key="prob_a")
            
            total = prob_h + prob_d + prob_a
            if total == 0:
                st.error("Сумма вероятностей не может быть нулевой.")
                st.stop()
            prob_h = prob_h / total
            prob_d = prob_d / total
            prob_a = prob_a / total
            
            submitted = st.form_submit_button("Рассчитать валуйность")
        
        if submitted:
            if home_odd > 0 and draw_odd > 0 and away_odd > 0:
                implied_h = 1/home_odd
                implied_d = 1/draw_odd
                implied_a = 1/away_odd
                margin = implied_h + implied_d + implied_a
                if margin > 0:
                    implied_h /= margin
                    implied_d /= margin
                    implied_a /= margin
            else:
                implied_h = implied_d = implied_a = None
            
            value_found = False
            best_bet = None
            best_value = 0
            
            if implied_h is not None and prob_h > implied_h:
                value = prob_h - implied_h
                if value > best_value:
                    best_value = value
                    best_bet = f"{home} (кф {home_odd:.2f})"
                    value_found = True
            if implied_d is not None and prob_d > implied_d:
                value = prob_d - implied_d
                if value > best_value:
                    best_value = value
                    best_bet = f"Ничья (кф {draw_odd:.2f})"
                    value_found = True
            if implied_a is not None and prob_a > implied_a:
                value = prob_a - implied_a
                if value > best_value:
                    best_value = value
                    best_bet = f"{away} (кф {away_odd:.2f})"
                    value_found = True
            
            st.divider()
            st.subheader("📊 Результат анализа")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Ваша оценка (хозяева)", f"{prob_h:.1%}")
                if implied_h is not None:
                    st.caption(f"Букмекер: {implied_h:.1%}")
            with col2:
                st.metric("Ваша оценка (ничья)", f"{prob_d:.1%}")
                if implied_d is not None:
                    st.caption(f"Букмекер: {implied_d:.1%}")
            with col3:
                st.metric("Ваша оценка (гости)", f"{prob_a:.1%}")
                if implied_a is not None:
                    st.caption(f"Букмекер: {implied_a:.1%}")
            
            if value_found:
                stars = "⭐" * min(5, int(best_value * 20) + 1)
                st.success(f"✅ Найдена валуйная ставка! {stars}\n\nРекомендуемая ставка: **{best_bet}**")
            else:
                st.info("⏳ Валуйных ставок не обнаружено. Ваша оценка не выше букмекерской.")

    # ---- Автоматический режим ----
    else:
        # Проверяем лимит запросов к Football-Data.org
        can_request, wait_seconds = can_make_request(30)
        if not can_request:
            st.warning(f"⏳ Подождите {wait_seconds} секунд перед следующим запросом.")
            st.stop()
        
        with st.spinner("Загружаем данные и ИИ-прогнозы..."):
            try:
                matches, team_stats = fetch_matches_and_standings(comp_id, football_key)
                st.session_state.last_request_time = datetime.now()
            except Exception as e:
                if "429" in str(e):
                    import re
                    match = re.search(r'Wait (\d+) seconds', str(e))
                    if match:
                        st.error(f"⏳ Лимит запросов. Подождите {match.group(1)} секунд.")
                    else:
                        st.error("⏳ Лимит запросов. Подождите 30 секунд.")
                else:
                    st.error(f"Ошибка: {e}")
                st.stop()
        
        if not matches:
            st.info("Нет предстоящих матчей.")
            st.stop()
        
        # Загружаем ИИ-прогнозы от Bet Better
        betbetter_picks = []
        if league_slug:
            betbetter_picks = fetch_betbetter_predictions(league_slug)
            if betbetter_picks:
                st.success(f"✅ Загружено {len(betbetter_picks)} ИИ-прогнозов от Bet Better")
            else:
                st.warning("⚠️ ИИ-прогнозы от Bet Better не загружены. Использую статистическую модель.")
        else:
            st.info("Для этой лиги нет ИИ-прогнозов. Использую статистическую модель.")
        
        # Строим индекс по матчам для быстрого поиска прогноза
        betbetter_map = {}
        for pick in betbetter_picks:
            game = pick.get('game', '')
            if ' @ ' in game:
                away_team, home_team = game.split(' @ ', 1)
                home_team = home_team.strip()
                away_team = away_team.strip()
                betbetter_map[(home_team, away_team)] = pick
                betbetter_map[(clean_team_name(home_team), clean_team_name(away_team))] = pick

        # Загружаем коэффициенты (если выбран авто-режим)
        odds_data = {}
        if odds_source == "Автоматически (TheOddsAPI)" and odds_key:
            odds_data = fetch_odds_from_odds_api(odds_key)
            if odds_data:
                used = st.session_state.odds_request_count
                st.success(f"✅ Загружены коэффициенты для {len(odds_data)} матчей (запросов: {used}/500)")
            else:
                st.warning("⚠️ Не удалось загрузить коэффициенты. Будет ручной ввод.")

        results = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            home_clean = clean_team_name(home)
            away_clean = clean_team_name(away)

            # ---- Ищем ИИ-прогноз от Bet Better ----
            ai_pick = None
            if (home, away) in betbetter_map:
                ai_pick = betbetter_map[(home, away)]
            elif (home_clean, away_clean) in betbetter_map:
                ai_pick = betbetter_map[(home_clean, away_clean)]
            else:
                for (h, a), pick in betbetter_map.items():
                    if (home_clean in h and away_clean in a) or (home in h and away in a):
                        ai_pick = pick
                        break

            # ---- Если есть ИИ-прогноз - используем его ----
            if ai_pick:
                selection = ai_pick.get('selection', '')
                prob_pct = ai_pick.get('modelProbabilityPct', 50)
                confidence = ai_pick.get('confidence', 'LEAN')
                verdict = ai_pick.get('verdict', '')
                if selection == home or selection == home_clean:
                    prob_home = prob_pct / 100
                    remaining = 1 - prob_home
                    prob_draw = remaining * 0.5
                    prob_away = remaining * 0.5
                elif selection == away or selection == away_clean:
                    prob_away = prob_pct / 100
                    remaining = 1 - prob_away
                    prob_home = remaining * 0.5
                    prob_draw = remaining * 0.5
                else:
                    prob_home = prob_pct / 100
                    prob_away = 0.3
                    prob_draw = 0.3
                total = prob_home + prob_draw + prob_away
                if total > 0:
                    prob_home /= total
                    prob_draw /= total
                    prob_away /= total
                source = f"🤖 Bet Better ({confidence})"
                if verdict:
                    source += f": {verdict}"
            else:
                # ---- Иначе используем статистическую модель ----
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
                source = "📊 Статистическая модель"

            # ---- Коэффициенты (из API или ручной ввод) ----
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
                    for (h, a), val in odds_data.items():
                        if clean_team_name(h) == home_clean and clean_team_name(a) == away_clean:
                            home_odds = val['home_win']
                            away_odds = val['away_win']
                            draw_odds = val['draw']
                            bookmaker_name = val['bookmaker']
                            break

            # Если коэффициенты не загружены, предлагаем ручной ввод с улучшенным оформлением
            if not (home_odds and away_odds and draw_odds):
                st.markdown("---")
                st.markdown(f"**🎯 Введите коэффициенты для матча:**")
                st.markdown(f"**{home_clean}** vs **{away_clean}**")
                st.caption("Если коэффициенты не загружены автоматически, введите их из вашей БК. Если оставить как есть — сравнение с букмекером не будет выполнено.")
                col_h, col_d, col_a = st.columns(3)
                with col_h:
                    home_odds = st.number_input(f"Победа {home_clean}", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key=f"h_{home}_{away}")
                with col_d:
                    draw_odds = st.number_input("Ничья", min_value=1.0, max_value=20.0, value=3.0, step=0.1, key=f"d_{home}_{away}")
                with col_a:
                    away_odds = st.number_input(f"Победа {away_clean}", min_value=1.0, max_value=20.0, value=2.0, step=0.1, key=f"a_{home}_{away}")
                bookmaker_name = "Ручной ввод"

            # ---- Поиск валуйной ставки ----
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
                "Источник прогноза": source,
                "value": best_value,
                "is_value": best_value > 0 and home_odds is not None and draw_odds is not None and away_odds is not None
            })

        # ---- Фильтрация и вывод ----
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
                    st.caption(f"Источник прогноза: {row['Источник прогноза']} | Букмекер: {row['Букмекер']}")
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
        - 🤖 — прогноз от ИИ-модели Bet Better (на основе машинного обучения).
        - 📊 — прогноз на основе статистической модели (турнирная таблица).
        """)

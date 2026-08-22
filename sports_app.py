import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
import re
from io import StringIO

# =================== ОПРЕДЕЛЕНИЯ ===================
FLAGS = {
    "АПЛ (Англия)": "🇬🇧",
    "Ла Лига (Испания)": "🇪🇸",
    "Бундеслига (Германия)": "🇩🇪",
    "Серия А (Италия)": "🇮🇹",
    "Лига 1 (Франция)": "🇫🇷",
    "Лига Чемпионов": "🏆"
}

COMP_IDS = {
    "АПЛ (Англия)": 2021,
    "Ла Лига (Испания)": 2014,
    "Бундеслига (Германия)": 2002,
    "Серия А (Италия)": 2019,
    "Лига 1 (Франция)": 2015,
    "Лига Чемпионов": 2001,
}

LEAGUE_CSV_CODES = {
    "АПЛ (Англия)": "E0",
    "Ла Лига (Испания)": "SP1",
    "Бундеслига (Германия)": "D1",
    "Серия А (Италия)": "I1",
    "Лига 1 (Франция)": "F1",
    "Лига Чемпионов": None
}

# =================== АУТЕНТИФИКАЦИЯ ===================
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

st.set_page_config(page_title="Спортивный аналитик", layout="wide")
if not check_password():
    st.stop()

st.title("⚽ Спортивный аналитик — прогнозы и комбинации")

# =================== ИНИЦИАЛИЗАЦИЯ СОСТОЯНИЯ ===================
if 'league_cache' not in st.session_state:
    st.session_state.league_cache = {}
if 'selected_matches' not in st.session_state:
    st.session_state.selected_matches = {}
if 'selected_bookmaker' not in st.session_state:
    st.session_state.selected_bookmaker = "Лига Ставок"
if 'filter_date' not in st.session_state:
    st.session_state.filter_date = datetime.now().date()
if 'show_best' not in st.session_state:
    st.session_state.show_best = False
if 'odds_data' not in st.session_state:
    st.session_state.odds_data = {}
if 'uploaded_csvs' not in st.session_state:
    st.session_state.uploaded_csvs = {}

# ---- Ограничение для TheOddsAPI ----
if 'odds_request_count' not in st.session_state:
    st.session_state.odds_request_count = 0
if 'odds_request_date' not in st.session_state:
    st.session_state.odds_request_date = datetime.now().date()

def can_request_odds(limit=500):
    today = datetime.now().date()
    if today != st.session_state.odds_request_date:
        st.session_state.odds_request_count = 0
        st.session_state.odds_request_date = today
    if st.session_state.odds_request_count >= limit:
        return False, st.session_state.odds_request_count, limit
    return True, st.session_state.odds_request_count, limit

# ---- Функции для работы с коэффициентами ----
def update_odds_from_session():
    for key in list(st.session_state.keys()):
        if key.startswith('num_') and key.endswith('_h'):
            match_id = key[4:-2]
            if match_id not in st.session_state.odds_data:
                st.session_state.odds_data[match_id] = {'h': 2.0, 'd': 3.0, 'a': 2.0}
            st.session_state.odds_data[match_id]['h'] = st.session_state[key]
        elif key.startswith('num_') and key.endswith('_d'):
            match_id = key[4:-2]
            if match_id not in st.session_state.odds_data:
                st.session_state.odds_data[match_id] = {'h': 2.0, 'd': 3.0, 'a': 2.0}
            st.session_state.odds_data[match_id]['d'] = st.session_state[key]
        elif key.startswith('num_') and key.endswith('_a'):
            match_id = key[4:-2]
            if match_id not in st.session_state.odds_data:
                st.session_state.odds_data[match_id] = {'h': 2.0, 'd': 3.0, 'a': 2.0}
            st.session_state.odds_data[match_id]['a'] = st.session_state[key]

def get_odds(match_id):
    if match_id not in st.session_state.odds_data:
        st.session_state.odds_data[match_id] = {'h': 2.0, 'd': 3.0, 'a': 2.0}
    return st.session_state.odds_data[match_id]

# ---- Словарь лиг Bet Better ----
BETBETTER_LEAGUES = {
    "АПЛ (Англия)": "soccer/epl",
    "Ла Лига (Испания)": "soccer/la-liga",
    "Бундеслига (Германия)": "soccer/bundesliga",
    "Серия А (Италия)": "soccer/serie-a",
    "Лига 1 (Франция)": "soccer/ligue-1",
    "Лига Чемпионов": "soccer/world-cup",
}

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

def clean_team_name(name):
    name = re.sub(r'\s+FC$', '', name)
    name = re.sub(r'\s+AFC$', '', name)
    return name

# ---- Загрузка ключей ----
football_key = st.secrets.get("FOOTBALL_API_KEY")
if not football_key:
    football_key = st.text_input("Введите API-ключ Football-Data.org", type="password")
    if not football_key:
        st.warning("Ключ нужен для загрузки матчей.")
        st.stop()

odds_key = st.secrets.get("ODDS_API_KEY")

# ---- Функции загрузки данных ----
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

def fetch_odds_from_odds_api(api_key, sport='soccer', region='eu', market='h2h'):
    if not api_key:
        return {}
    can_request, count, limit = can_request_odds()
    if not can_request:
        st.warning(f"⚠️ Дневной лимит TheOddsAPI ({limit}) исчерпан.")
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

# ---- Новые функции для улучшенного алгоритма (исправленные) ----
@st.cache_data(ttl=3600)
def load_csv_data(league_code):
    if league_code is None:
        return None
    urls = [
        f"https://www.football-data.co.uk/new/{league_code}.csv",
        f"https://www.football-data.co.uk/current/{league_code}.csv",
        f"https://www.football-data.co.uk/archive/{league_code}.csv"
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                df = pd.read_csv(StringIO(response.text))
                # Проверяем обязательные колонки
                if 'Date' in df.columns and 'HomeTeam' in df.columns and 'AwayTeam' in df.columns:
                    # Пытаемся преобразовать дату в разных форматах
                    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y'):
                        try:
                            df['Date'] = pd.to_datetime(df['Date'], format=fmt, errors='coerce')
                            break
                        except:
                            continue
                    # Если не удалось, пробуем с dayfirst=True (для формата дд/мм/гггг)
                    if df['Date'].isna().all():
                        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
                    # Удаляем строки с некорректной датой
                    df = df.dropna(subset=['Date'])
                    if not df.empty:
                        df = df.sort_values('Date')
                        return df
        except:
            continue
    return None

def find_team_name_mapping(api_name, csv_team_names):
    api_clean = clean_team_name(api_name).lower()
    for csv_name in csv_team_names:
        csv_clean = clean_team_name(csv_name).lower()
        if api_clean == csv_clean:
            return csv_name
        if api_clean in csv_clean or csv_clean in api_clean:
            return csv_name
    return None

def get_team_form(csv_df, team_name, n_matches=5):
    # Убедимся, что Date - datetime
    if not pd.api.types.is_datetime64_any_dtype(csv_df['Date']):
        csv_df['Date'] = pd.to_datetime(csv_df['Date'], errors='coerce')
    csv_df = csv_df.dropna(subset=['Date'])
    today = datetime.now().date()
    df_past = csv_df[csv_df['Date'].dt.date < today]
    if df_past.empty:
        return 0, 0
    # Проверяем наличие колонок с голами
    if 'HomeGoals' not in df_past.columns or 'AwayGoals' not in df_past.columns:
        if 'FTHG' in df_past.columns and 'FTAG' in df_past.columns:
            df_past = df_past.rename(columns={'FTHG': 'HomeGoals', 'FTAG': 'AwayGoals'})
        else:
            return 0, 0
    home_matches = df_past[df_past['HomeTeam'] == team_name][['Date', 'HomeGoals', 'AwayGoals']].copy()
    home_matches['Points'] = home_matches.apply(lambda row: 3 if row['HomeGoals'] > row['AwayGoals'] else (1 if row['HomeGoals'] == row['AwayGoals'] else 0), axis=1)
    home_matches['GD'] = home_matches['HomeGoals'] - home_matches['AwayGoals']
    away_matches = df_past[df_past['AwayTeam'] == team_name][['Date', 'HomeGoals', 'AwayGoals']].copy()
    away_matches['Points'] = away_matches.apply(lambda row: 3 if row['AwayGoals'] > row['HomeGoals'] else (1 if row['HomeGoals'] == row['AwayGoals'] else 0), axis=1)
    away_matches['GD'] = away_matches['AwayGoals'] - away_matches['HomeGoals']
    all_matches = pd.concat([home_matches, away_matches]).sort_values('Date', ascending=False)
    last_n = all_matches.head(n_matches)
    if last_n.empty:
        return 0, 0
    return last_n['Points'].sum(), last_n['GD'].sum()

def get_h2h(csv_df, home_team, away_team, n_matches=3):
    # Убедимся, что Date - datetime (хотя мы не используем .dt в этой функции, но для безопасности)
    if not pd.api.types.is_datetime64_any_dtype(csv_df['Date']):
        csv_df['Date'] = pd.to_datetime(csv_df['Date'], errors='coerce')
    csv_df = csv_df.dropna(subset=['Date'])
    mask = ((csv_df['HomeTeam'] == home_team) & (csv_df['AwayTeam'] == away_team)) | \
           ((csv_df['HomeTeam'] == away_team) & (csv_df['AwayTeam'] == home_team))
    h2h_matches = csv_df[mask].copy()
    if h2h_matches.empty:
        return 0.33, 0.34, 0.33
    h2h_matches = h2h_matches.sort_values('Date', ascending=False).head(n_matches)
    wins_home = 0
    draws = 0
    wins_away = 0
    for _, row in h2h_matches.iterrows():
        if 'HomeGoals' not in row or 'AwayGoals' not in row:
            continue
        if row['HomeTeam'] == home_team:
            if row['HomeGoals'] > row['AwayGoals']:
                wins_home += 1
            elif row['HomeGoals'] == row['AwayGoals']:
                draws += 1
            else:
                wins_away += 1
        else:
            if row['AwayGoals'] > row['HomeGoals']:
                wins_home += 1
            elif row['HomeGoals'] == row['AwayGoals']:
                draws += 1
            else:
                wins_away += 1
    total = len(h2h_matches)
    if total == 0:
        return 0.33, 0.34, 0.33
    return wins_home/total, draws/total, wins_away/total

# ---- Функция загрузки данных для лиги ----
def load_league_data(league_name, force=False):
    if force and league_name in st.session_state.league_cache:
        del st.session_state.league_cache[league_name]
    if league_name in st.session_state.league_cache:
        return
    
    comp_id = COMP_IDS[league_name]
    league_slug = BETBETTER_LEAGUES.get(league_name)
    league_code = LEAGUE_CSV_CODES.get(league_name)
    
    with st.spinner(f"Загружаем данные для {league_name}..."):
        try:
            matches, team_stats = fetch_matches_and_standings(comp_id, football_key)
        except Exception as e:
            if "429" in str(e):
                st.error("⏳ Лимит запросов к Football-Data.org. Подождите 30 секунд.")
                return
            else:
                st.error(f"Ошибка загрузки матчей: {e}")
                return
        
        # ---- Загрузка CSV ----
        csv_df = None
        if league_name in st.session_state.uploaded_csvs and st.session_state.uploaded_csvs[league_name] is not None:
            csv_df = st.session_state.uploaded_csvs[league_name]
            st.info(f"📊 Используется загруженный CSV для {league_name}")
        else:
            if league_code:
                csv_df = load_csv_data(league_code)
                if csv_df is not None and not csv_df.empty:
                    st.info(f"📊 Загружена статистика из CSV для {league_name} (файл {league_code}.csv)")
                else:
                    st.warning(f"⚠️ Не удалось загрузить CSV для {league_name}. Будет использована упрощённая модель.")
            else:
                st.info(f"Для {league_name} нет данных CSV, используется упрощённая модель.")
        
        betbetter_picks = []
        if league_slug:
            betbetter_picks = fetch_betbetter_predictions(league_slug)
        
        odds_data = {}
        if odds_key:
            odds_data = fetch_odds_from_odds_api(odds_key)
        
        st.session_state.league_cache[league_name] = {
            'matches': matches,
            'team_stats': team_stats,
            'betbetter_picks': betbetter_picks,
            'odds_data': odds_data,
            'csv_data': csv_df
        }

def refresh_current_league(league_name):
    load_league_data(league_name, force=True)
    st.rerun()

# ---- Боковая панель (без изменений) ----
with st.sidebar:
    st.header("⚙️ Настройки")
    bookmaker = st.selectbox(
        "Букмекерская контора (для ручного ввода)",
        ["Лига Ставок", "Winline", "BetBoom", "1xСтавка", "Марафон", "Другой"],
        index=0,
        key="bookmaker_select"
    )
    st.session_state.selected_bookmaker = bookmaker
    show_only_value = st.checkbox("Показать только матчи с явными преимуществами", value=False)
    st.divider()
    refresh_league = st.selectbox("Выберите лигу для обновления", list(FLAGS.keys()), key="refresh_league_select")
    if st.button("🔄 Обновить данные для выбранной лиги"):
        refresh_current_league(refresh_league)
        st.success(f"Данные для {refresh_league} обновлены!")
    st.divider()
    st.header("🔍 Фильтр по дате")
    filter_date = st.date_input("Выберите дату", value=st.session_state.filter_date, key="date_filter")
    if st.button("📊 Показать лучшие позиции за выбранную дату"):
        st.session_state.filter_date = filter_date
        st.session_state.show_best = True
        st.rerun()
    if st.button("🔄 Сбросить фильтр"):
        st.session_state.show_best = False
        st.rerun()
    
    st.divider()
    st.header("📁 Загрузить CSV")
    st.caption("Загрузите CSV-файл для выбранной лиги. Файлы хранятся отдельно для каждой лиги.")
    csv_league_to_upload = st.selectbox(
        "Выберите лигу для загрузки CSV",
        list(FLAGS.keys()),
        key="csv_league_select"
    )
    uploaded_file = st.file_uploader(
        "Выберите CSV-файл",
        type=["csv"],
        key="csv_uploader_main"
    )
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            # Проверяем структуру
            if 'Date' in df.columns and 'HomeTeam' in df.columns and 'AwayTeam' in df.columns:
                # Конвертируем дату
                for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%m/%d/%Y'):
                    try:
                        df['Date'] = pd.to_datetime(df['Date'], format=fmt, errors='coerce')
                        break
                    except:
                        continue
                if df['Date'].isna().all():
                    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
                df = df.dropna(subset=['Date'])
                if 'FTHG' in df.columns and 'FTAG' in df.columns:
                    df = df.rename(columns={'FTHG': 'HomeGoals', 'FTAG': 'AwayGoals'})
                elif 'HomeGoals' not in df.columns or 'AwayGoals' not in df.columns:
                    st.warning("⚠️ В файле нет колонок с голами (FTHG/FTAG или HomeGoals/AwayGoals). Форма команд будет рассчитываться без разницы голов.")
                st.session_state.uploaded_csvs[csv_league_to_upload] = df
                st.success(f"✅ Файл загружен для {csv_league_to_upload}! {len(df)} матчей.")
                load_league_data(csv_league_to_upload, force=True)
                st.rerun()
            else:
                st.error("❌ Неверный формат CSV. Убедитесь, что есть колонки: Date, HomeTeam, AwayTeam (и желательно FTHG/FTAG).")
        except Exception as e:
            st.error(f"Ошибка чтения файла: {e}")
    
    if st.session_state.uploaded_csvs:
        st.caption("📂 Загруженные файлы:")
        for league, df in st.session_state.uploaded_csvs.items():
            st.write(f"  - {league} ({len(df)} матчей)")
    
    st.divider()
    if st.session_state.selected_matches:
        st.header("🧩 Моя комбинация")
        selected_list = list(st.session_state.selected_matches.values())
        total_prob = 1.0
        total_odds = 1.0
        odds_available = True
        for m in selected_list:
            max_prob = max(m['Победа хозяев'], m['Ничья'], m['Победа гостей'])
            total_prob *= max_prob
            if m['Кф хозяев'] and m['Кф ничья'] and m['Кф гости']:
                if max_prob == m['Победа хозяев']:
                    odds = m['Кф хозяев']
                elif max_prob == m['Ничья']:
                    odds = m['Кф ничья']
                else:
                    odds = m['Кф гости']
                total_odds *= odds
            else:
                odds_available = False
                total_odds = None
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Событий", len(selected_list))
        with col2:
            st.metric("Общая вероятность", f"{total_prob:.1%}")
        if odds_available and total_odds:
            st.metric("Общий коэффициент", f"{total_odds:.2f}")
        else:
            st.metric("Общий коэффициент", "— (нет всех кф)")
        risk_level = "Низкий" if total_prob > 0.5 else "Средний" if total_prob > 0.25 else "Высокий"
        st.info(f"**Риск:** {risk_level} (вероятность {total_prob:.1%})")
        with st.expander("📋 Выбранные матчи"):
            for idx, m in enumerate(selected_list):
                max_prob = max(m['Победа хозяев'], m['Ничья'], m['Победа гостей'])
                if max_prob == m['Победа хозяев']:
                    outcome = f"Победа {m['Хозяева']}"
                elif max_prob == m['Ничья']:
                    outcome = "Ничья"
                else:
                    outcome = f"Победа {m['Гости']}"
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.write(f"{m['Хозяева']} vs {m['Гости']} → **{outcome}** ({max_prob:.0%})")
                with col_b:
                    if st.button("✖️", key=f"del_{m['id']}"):
                        if m['id'] in st.session_state.selected_matches:
                            del st.session_state.selected_matches[m['id']]
                            st.rerun()
        if st.button("🗑️ Очистить всё", key="clear_comb"):
            st.session_state.selected_matches = {}
            st.rerun()
    else:
        st.info("Выберите матчи чекбоксами «➕ В комбинацию» под карточками.")
    with st.expander("ℹ️ Как это работает"):
        st.markdown(f"""
        **Букмекерская контора:** {st.session_state.selected_bookmaker}
        **🤖 ИИ-прогнозы от Bet Better:** Бесплатный сервис на основе машинного обучения. Доступен для топ-лиг (АПЛ, Ла Лига, Бундеслига, Серия А, Лига 1, Лига Чемпионов).
        **📊 Улучшенная модель:** использует форму команд за последние 5 матчей, личные встречи и сезонный рейтинг. Для работы требуется загрузка CSV-файла (или автоматическая загрузка с football-data.co.uk).
        **📈 Коэффициенты:** Загружаются через TheOddsAPI (если есть ключ и лимит). Если не загрузились, появляются компактные поля для ручного ввода.
        **🧩 Комбинации:** Выбирайте матчи чекбоксом «➕ В комбинацию» под карточкой.
        **🔄 Обновление данных:** Нажмите кнопку «Обновить данные для выбранной лиги».
        **📁 Загрузка CSV:** Скачайте CSV-файл с football-data.co.uk и загрузите его для конкретной лиги. Файлы хранятся отдельно для каждой лиги.
        """)

# =================== ВКЛАДКИ ===================
league_names = list(FLAGS.keys())
tab_names = league_names + ["⭐ Лучшие матчи"]
tabs = st.tabs(tab_names)

# --- Лиги ---
for i, league_name in enumerate(league_names):
    with tabs[i]:
        if league_name not in st.session_state.league_cache:
            load_league_data(league_name)
        league_data = st.session_state.league_cache.get(league_name, None)
        if not league_data or not league_data['matches']:
            st.info(f"Нет предстоящих матчей в {league_name}.")
            continue
        
        matches = league_data['matches']
        team_stats = league_data['team_stats']
        odds_data_api = league_data['odds_data']
        betbetter_picks = league_data['betbetter_picks']
        csv_df = league_data.get('csv_data', None)
        # Проверка, не появился ли CSV в uploaded_csvs после кэширования
        if csv_df is None and league_name in st.session_state.uploaded_csvs and st.session_state.uploaded_csvs[league_name] is not None:
            csv_df = st.session_state.uploaded_csvs[league_name]
            league_data['csv_data'] = csv_df
        
        flag = FLAGS.get(league_name, "⚽")
        csv_team_names = None
        if csv_df is not None and not csv_df.empty:
            csv_team_names = pd.concat([csv_df['HomeTeam'], csv_df['AwayTeam']]).unique()
        
        betbetter_map = {}
        for pick in betbetter_picks or []:
            game = pick.get('game', '')
            if ' @ ' in game:
                away_team, home_team = game.split(' @ ', 1)
                home_team = home_team.strip()
                away_team = away_team.strip()
                betbetter_map[(home_team, away_team)] = pick
                betbetter_map[(clean_team_name(home_team), clean_team_name(away_team))] = pick
        
        results = []
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            matchday = match.get('matchday', '—')
            home_clean = clean_team_name(home)
            away_clean = clean_team_name(away)
            match_id = f"{league_name}_{home}_{away}_{match_date}"
            
            # ---- Ищем прогноз Bet Better ----
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
            
            # ---- Расчёт вероятностей (улучшенный алгоритм) ----
            h_points = 0
            h_played = 1
            a_points = 0
            a_played = 1
            h_gd = 0
            a_gd = 0
            if home in team_stats:
                h_points = team_stats[home].get('points', 0)
                h_played = team_stats[home].get('played', 1)
                if h_played > 0:
                    h_gd = (team_stats[home].get('goals_for', 0) - team_stats[home].get('goals_against', 0)) / h_played
            if away in team_stats:
                a_points = team_stats[away].get('points', 0)
                a_played = team_stats[away].get('played', 1)
                if a_played > 0:
                    a_gd = (team_stats[away].get('goals_for', 0) - team_stats[away].get('goals_against', 0)) / a_played
            
            h_ppg = h_points / h_played if h_played > 0 else 0
            a_ppg = a_points / a_played if a_played > 0 else 0
            
            home_form_points = 0
            away_form_points = 0
            h2h_home = 0.33
            h2h_draw = 0.34
            h2h_away = 0.33
            home_csv_name = None
            away_csv_name = None
            
            if csv_df is not None and not csv_df.empty and csv_team_names is not None:
                home_csv_name = find_team_name_mapping(home, csv_team_names)
                away_csv_name = find_team_name_mapping(away, csv_team_names)
                if home_csv_name and away_csv_name:
                    home_form_points, _ = get_team_form(csv_df, home_csv_name, 5)
                    away_form_points, _ = get_team_form(csv_df, away_csv_name, 5)
                    h2h_home, h2h_draw, h2h_away = get_h2h(csv_df, home_csv_name, away_csv_name, 3)
            
            # ---- Комбинированный рейтинг ----
            home_form_ratio = min(home_form_points / 15.0, 1.0)
            away_form_ratio = min(away_form_points / 15.0, 1.0)
            h_ppg_norm = min(h_ppg / 3.0, 1.0)
            a_ppg_norm = min(a_ppg / 3.0, 1.0)
            
            weight_form = 0.5
            weight_season = 0.3
            weight_h2h = 0.2
            
            home_strength = (home_form_ratio * weight_form) + (h_ppg_norm * weight_season) + (h2h_home * weight_h2h)
            away_strength = (away_form_ratio * weight_form) + (a_ppg_norm * weight_season) + (h2h_away * weight_h2h)
            home_boost = 0.10
            home_strength += home_boost
            
            total_strength = home_strength + away_strength
            if total_strength > 0:
                prob_home = home_strength / total_strength
                prob_away = away_strength / total_strength
            else:
                prob_home = 0.4
                prob_away = 0.4
            prob_draw = 1 - prob_home - prob_away
            
            prob_home = max(0.05, min(0.85, prob_home))
            prob_away = max(0.05, min(0.85, prob_away))
            prob_draw = max(0.05, min(0.50, prob_draw))
            total = prob_home + prob_draw + prob_away
            prob_home /= total
            prob_draw /= total
            prob_away /= total
            
            source = "📊 Улучшенная модель"
            if csv_df is None or csv_df.empty:
                source = "📊 Статистическая модель (без CSV)"
            else:
                source = f"📊 Улучшенная модель (CSV: {len(csv_df)} матчей)"
            
            # ---- Коэффициенты ----
            home_odds = None
            away_odds = None
            draw_odds = None
            bookmaker_name = "Неизвестная БК"
            manual_input_needed = False
            
            api_odds_found = False
            if odds_data_api:
                key = (home, away)
                if key in odds_data_api:
                    home_odds = odds_data_api[key]['home_win']
                    away_odds = odds_data_api[key]['away_win']
                    draw_odds = odds_data_api[key]['draw']
                    bookmaker_name = odds_data_api[key]['bookmaker']
                    api_odds_found = True
                else:
                    for (h, a), val in odds_data_api.items():
                        if clean_team_name(h) == home_clean and clean_team_name(a) == away_clean:
                            home_odds = val['home_win']
                            away_odds = val['away_win']
                            draw_odds = val['draw']
                            bookmaker_name = val['bookmaker']
                            api_odds_found = True
                            break
            
            manual_input_needed = not api_odds_found
            if not api_odds_found:
                if match_id not in st.session_state.odds_data:
                    st.session_state.odds_data[match_id] = {'h': 2.0, 'd': 3.0, 'a': 2.0}
                home_odds = st.session_state.odds_data[match_id]['h']
                away_odds = st.session_state.odds_data[match_id]['a']
                draw_odds = st.session_state.odds_data[match_id]['d']
                bookmaker_name = st.session_state.selected_bookmaker
            
            # ---- Поиск валуйной ставки ----
            best_bet = None
            best_value = 0
            if home_odds and prob_home > 0 and prob_home > 1/home_odds:
                value = prob_home - 1/home_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{home_clean} (кф {home_odds:.2f})"
            if draw_odds and prob_draw > 0 and prob_draw > 1/draw_odds:
                value = prob_draw - 1/draw_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"Ничья (кф {draw_odds:.2f})"
            if away_odds and prob_away > 0 and prob_away > 1/away_odds:
                value = prob_away - 1/away_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{away_clean} (кф {away_odds:.2f})"
            
            if best_bet:
                stars = "⭐" * min(5, int(best_value * 20) + 1)
                recommendation = f"{stars} {best_bet}"
            else:
                max_prob = max(prob_home, prob_draw, prob_away)
                if max_prob == prob_home:
                    rec_text = f"Рекомендуем {home_clean} (вероятность {prob_home:.0%})"
                elif max_prob == prob_draw:
                    rec_text = f"Рекомендуем ничью (вероятность {prob_draw:.0%})"
                else:
                    rec_text = f"Рекомендуем {away_clean} (вероятность {prob_away:.0%})"
                recommendation = f"📈 {rec_text}"
            
            extra_info = ""
            if csv_df is not None and not csv_df.empty and home_csv_name and away_csv_name:
                extra_info = f"Форма: {home_csv_name} {home_form_points} очков за 5 матчей, {away_csv_name} {away_form_points} очков"
            
            results.append({
                "id": match_id,
                "Дата": match_date,
                "Тур": matchday,
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
                "is_value": best_value > 0 and home_odds is not None and draw_odds is not None and away_odds is not None,
                "manual_input_needed": manual_input_needed,
                "match_id": match_id,
                "extra_info": extra_info
            })
        
        update_odds_from_session()
        
        if show_only_value:
            results = [r for r in results if r['is_value']]
        if st.session_state.show_best:
            target_date = st.session_state.filter_date
            filtered_results = []
            for r in results:
                try:
                    r_date = datetime.strptime(r['Дата'], '%Y-%m-%d').date()
                    if r_date == target_date:
                        filtered_results.append(r)
                except:
                    pass
            filtered_results.sort(key=lambda x: x.get('value', 0), reverse=True)
            results = filtered_results
        if not results:
            if st.session_state.show_best:
                st.info(f"Нет матчей с валуйными ставками на {st.session_state.filter_date.strftime('%d.%m.%Y')}.")
            else:
                st.info("Нет матчей, соответствующих текущим фильтрам.")
            continue
        st.success(f"✅ Найдено {len(results)} матчей")
        df = pd.DataFrame(results)
        df['Дата'] = pd.to_datetime(df['Дата'])
        dates = sorted(df['Дата'].unique())
        st.markdown("""
        <style>
            div[data-testid="stNumberInput"] input { width: 60px !important; font-size: 14px !important; padding: 4px !important; }
            div[data-testid="column"] { padding-left: 2px !important; padding-right: 2px !important; }
        </style>
        """, unsafe_allow_html=True)
        num_cols = 2
        for date in dates:
            st.subheader(f"📅 {date.strftime('%d %B %Y')}")
            day_matches = df[df['Дата'] == date].to_dict('records')
            for i in range(0, len(day_matches), num_cols):
                cols = st.columns(num_cols)
                for col_idx, col in enumerate(cols):
                    if i + col_idx < len(day_matches):
                        row = day_matches[i + col_idx]
                        with col:
                            with st.container():
                                st.markdown(f"{flag} **{row['Хозяева']}** vs **{row['Гости']}**")
                                st.caption(f"Тур {row['Тур']} | {row['Источник прогноза']} | Букмекер: {row['Букмекер']}")
                                if row['extra_info']:
                                    st.caption(row['extra_info'])
                                prob_str = f"🏠 {row['Победа хозяев']:.0%}  |  🤝 {row['Ничья']:.0%}  |  🚀 {row['Победа гостей']:.0%}"
                                st.markdown(prob_str)
                                if row['Кф хозяев'] and row['Кф ничья'] and row['Кф гости']:
                                    st.caption(f"Кф: {row['Кф хозяев']:.2f} / {row['Кф ничья']:.2f} / {row['Кф гости']:.2f}")
                                else:
                                    st.caption("Кф: — / — / —")
                                st.markdown(f"**Рекомендация:** {row['Рекомендация']}")
                                
                                is_selected = row['id'] in st.session_state.selected_matches
                                if st.checkbox("➕ В комбинацию", value=is_selected, key=f"sel_{league_name}_{row['id']}"):
                                    if row['id'] not in st.session_state.selected_matches:
                                        st.session_state.selected_matches[row['id']] = row
                                else:
                                    if row['id'] in st.session_state.selected_matches:
                                        del st.session_state.selected_matches[row['id']]
                                
                                if row['manual_input_needed']:
                                    st.markdown("---")
                                    st.caption("Введите коэф. (обновляется автоматически):")
                                    c1, c2, c3 = st.columns(3)
                                    match_id = row['match_id']
                                    with c1:
                                        st.number_input(
                                            "🏠",
                                            min_value=1.0, max_value=20.0,
                                            value=st.session_state.odds_data[match_id]['h'],
                                            step=0.1,
                                            key=f"num_{match_id}_h",
                                            format="%.2f",
                                            label_visibility="collapsed"
                                        )
                                    with c2:
                                        st.number_input(
                                            "🤝",
                                            min_value=1.0, max_value=20.0,
                                            value=st.session_state.odds_data[match_id]['d'],
                                            step=0.1,
                                            key=f"num_{match_id}_d",
                                            format="%.2f",
                                            label_visibility="collapsed"
                                        )
                                    with c3:
                                        st.number_input(
                                            "🚀",
                                            min_value=1.0, max_value=20.0,
                                            value=st.session_state.odds_data[match_id]['a'],
                                            step=0.1,
                                            key=f"num_{match_id}_a",
                                            format="%.2f",
                                            label_visibility="collapsed"
                                        )
                                st.markdown("---")
        if st.checkbox("Показать график сравнения вероятностей", key=f"show_graph_{league_name}"):
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
            fig.update_layout(barmode='group', yaxis_title='Вероятность', xaxis_tickangle=-45, height=400)
            st.plotly_chart(fig, use_container_width=True)

# --- Вкладка "⭐ Лучшие матчи" (только для чтения) ---
with tabs[-1]:
    st.header("⭐ Лучшие матчи по валуйности")
    st.caption("Здесь собраны все матчи из всех лиг, отсортированные по убыванию валуйности (звёзд). Коэффициенты берутся из введённых в лигах и автоматически обновляются.")
    
    for league_name in FLAGS.keys():
        if league_name not in st.session_state.league_cache:
            load_league_data(league_name)
    
    all_results = []
    for league_name in FLAGS.keys():
        league_data = st.session_state.league_cache.get(league_name, None)
        if not league_data or not league_data['matches']:
            continue
        matches = league_data['matches']
        team_stats = league_data['team_stats']
        odds_data_api = league_data['odds_data']
        betbetter_picks = league_data['betbetter_picks']
        csv_df = league_data.get('csv_data', None)
        if csv_df is None and league_name in st.session_state.uploaded_csvs and st.session_state.uploaded_csvs[league_name] is not None:
            csv_df = st.session_state.uploaded_csvs[league_name]
            league_data['csv_data'] = csv_df
        csv_team_names = None
        if csv_df is not None and not csv_df.empty:
            csv_team_names = pd.concat([csv_df['HomeTeam'], csv_df['AwayTeam']]).unique()
        
        betbetter_map = {}
        for pick in betbetter_picks or []:
            game = pick.get('game', '')
            if ' @ ' in game:
                away_team, home_team = game.split(' @ ', 1)
                home_team = home_team.strip()
                away_team = away_team.strip()
                betbetter_map[(home_team, away_team)] = pick
                betbetter_map[(clean_team_name(home_team), clean_team_name(away_team))] = pick
        
        for match in matches:
            home = match['homeTeam']['name']
            away = match['awayTeam']['name']
            match_date = match['utcDate'][:10]
            matchday = match.get('matchday', '—')
            home_clean = clean_team_name(home)
            away_clean = clean_team_name(away)
            match_id = f"{league_name}_{home}_{away}_{match_date}"
            
            h_points = 0
            h_played = 1
            a_points = 0
            a_played = 1
            h_gd = 0
            a_gd = 0
            if home in team_stats:
                h_points = team_stats[home].get('points', 0)
                h_played = team_stats[home].get('played', 1)
                if h_played > 0:
                    h_gd = (team_stats[home].get('goals_for', 0) - team_stats[home].get('goals_against', 0)) / h_played
            if away in team_stats:
                a_points = team_stats[away].get('points', 0)
                a_played = team_stats[away].get('played', 1)
                if a_played > 0:
                    a_gd = (team_stats[away].get('goals_for', 0) - team_stats[away].get('goals_against', 0)) / a_played
            h_ppg = h_points / h_played if h_played > 0 else 0
            a_ppg = a_points / a_played if a_played > 0 else 0
            
            home_form_points = 0
            away_form_points = 0
            h2h_home = 0.33
            h2h_draw = 0.34
            h2h_away = 0.33
            home_csv_name = None
            away_csv_name = None
            if csv_df is not None and not csv_df.empty and csv_team_names is not None:
                home_csv_name = find_team_name_mapping(home, csv_team_names)
                away_csv_name = find_team_name_mapping(away, csv_team_names)
                if home_csv_name and away_csv_name:
                    home_form_points, _ = get_team_form(csv_df, home_csv_name, 5)
                    away_form_points, _ = get_team_form(csv_df, away_csv_name, 5)
                    h2h_home, h2h_draw, h2h_away = get_h2h(csv_df, home_csv_name, away_csv_name, 3)
            
            home_form_ratio = min(home_form_points / 15.0, 1.0)
            away_form_ratio = min(away_form_points / 15.0, 1.0)
            h_ppg_norm = min(h_ppg / 3.0, 1.0)
            a_ppg_norm = min(a_ppg / 3.0, 1.0)
            
            weight_form = 0.5
            weight_season = 0.3
            weight_h2h = 0.2
            
            home_strength = (home_form_ratio * weight_form) + (h_ppg_norm * weight_season) + (h2h_home * weight_h2h)
            away_strength = (away_form_ratio * weight_form) + (a_ppg_norm * weight_season) + (h2h_away * weight_h2h)
            home_boost = 0.10
            home_strength += home_boost
            
            total_strength = home_strength + away_strength
            if total_strength > 0:
                prob_home = home_strength / total_strength
                prob_away = away_strength / total_strength
            else:
                prob_home = 0.4
                prob_away = 0.4
            prob_draw = 1 - prob_home - prob_away
            prob_home = max(0.05, min(0.85, prob_home))
            prob_away = max(0.05, min(0.85, prob_away))
            prob_draw = max(0.05, min(0.50, prob_draw))
            total = prob_home + prob_draw + prob_away
            prob_home /= total
            prob_draw /= total
            prob_away /= total
            
            source = "📊 Улучшенная модель"
            if csv_df is None or csv_df.empty:
                source = "📊 Статистическая модель (без CSV)"
            else:
                source = f"📊 Улучшенная модель (CSV: {len(csv_df)} матчей)"
            
            home_odds = None
            away_odds = None
            draw_odds = None
            bookmaker_name = "Неизвестная БК"
            if match_id in st.session_state.odds_data:
                home_odds = st.session_state.odds_data[match_id]['h']
                away_odds = st.session_state.odds_data[match_id]['a']
                draw_odds = st.session_state.odds_data[match_id]['d']
                bookmaker_name = st.session_state.selected_bookmaker
            else:
                if odds_data_api:
                    key = (home, away)
                    if key in odds_data_api:
                        home_odds = odds_data_api[key]['home_win']
                        away_odds = odds_data_api[key]['away_win']
                        draw_odds = odds_data_api[key]['draw']
                        bookmaker_name = odds_data_api[key]['bookmaker']
                    else:
                        for (h, a), val in odds_data_api.items():
                            if clean_team_name(h) == home_clean and clean_team_name(a) == away_clean:
                                home_odds = val['home_win']
                                away_odds = val['away_win']
                                draw_odds = val['draw']
                                bookmaker_name = val['bookmaker']
                                break
                if not (home_odds and away_odds and draw_odds):
                    home_odds = 2.0
                    away_odds = 2.0
                    draw_odds = 3.0
                    bookmaker_name = "Неизвестная БК"
            
            best_bet = None
            best_value = 0
            if home_odds and prob_home > 0 and prob_home > 1/home_odds:
                value = prob_home - 1/home_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{home_clean} (кф {home_odds:.2f})"
            if draw_odds and prob_draw > 0 and prob_draw > 1/draw_odds:
                value = prob_draw - 1/draw_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"Ничья (кф {draw_odds:.2f})"
            if away_odds and prob_away > 0 and prob_away > 1/away_odds:
                value = prob_away - 1/away_odds
                if value > best_value:
                    best_value = value
                    best_bet = f"{away_clean} (кф {away_odds:.2f})"
            
            if best_bet:
                stars = "⭐" * min(5, int(best_value * 20) + 1)
                recommendation = f"{stars} {best_bet}"
            else:
                max_prob = max(prob_home, prob_draw, prob_away)
                if max_prob == prob_home:
                    rec_text = f"Рекомендуем {home_clean} (вероятность {prob_home:.0%})"
                elif max_prob == prob_draw:
                    rec_text = f"Рекомендуем ничью (вероятность {prob_draw:.0%})"
                else:
                    rec_text = f"Рекомендуем {away_clean} (вероятность {prob_away:.0%})"
                recommendation = f"📈 {rec_text}"
            
            all_results.append({
                "id": match_id,
                "Дата": match_date,
                "Тур": matchday,
                "Лига": league_name,
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
                "is_value": best_value > 0 and home_odds is not None and draw_odds is not None and away_odds is not None,
                "match_id": match_id
            })
    
    if show_only_value:
        all_results = [r for r in all_results if r['is_value']]
    if st.session_state.show_best:
        target_date = st.session_state.filter_date
        filtered = []
        for r in all_results:
            try:
                r_date = datetime.strptime(r['Дата'], '%Y-%m-%d').date()
                if r_date == target_date:
                    filtered.append(r)
            except:
                pass
        all_results = filtered
    all_results.sort(key=lambda x: x.get('value', 0), reverse=True)
    
    if not all_results:
        st.info("Нет матчей с валуйными ставками.")
    else:
        st.success(f"✅ Найдено {len(all_results)} лучших матчей")
        df_all = pd.DataFrame(all_results)
        st.markdown("""
        <style>
            div[data-testid="stNumberInput"] input { width: 60px !important; font-size: 14px !important; padding: 4px !important; }
            div[data-testid="column"] { padding-left: 2px !important; padding-right: 2px !important; }
        </style>
        """, unsafe_allow_html=True)
        num_cols = 2
        df_all['Дата'] = pd.to_datetime(df_all['Дата'])
        dates_sorted = sorted(df_all['Дата'].unique())
        for date in dates_sorted:
            st.subheader(f"📅 {date.strftime('%d %B %Y')}")
            day_items = df_all[df_all['Дата'] == date].to_dict('records')
            for i in range(0, len(day_items), num_cols):
                cols = st.columns(num_cols)
                for col_idx, col in enumerate(cols):
                    if i + col_idx < len(day_items):
                        row = day_items[i + col_idx]
                        with col:
                            with st.container():
                                st.markdown(f"{FLAGS.get(row['Лига'], '⚽')} **{row['Хозяева']}** vs **{row['Гости']}**")
                                st.caption(f"{row['Лига']} | Тур {row['Тур']} | {row['Источник прогноза']} | Букмекер: {row['Букмекер']}")
                                prob_str = f"🏠 {row['Победа хозяев']:.0%}  |  🤝 {row['Ничья']:.0%}  |  🚀 {row['Победа гостей']:.0%}"
                                st.markdown(prob_str)
                                if row['Кф хозяев'] and row['Кф ничья'] and row['Кф гости']:
                                    st.caption(f"Кф: {row['Кф хозяев']:.2f} / {row['Кф ничья']:.2f} / {row['Кф гости']:.2f}")
                                else:
                                    st.caption("Кф: — / — / —")
                                st.markdown(f"**Рекомендация:** {row['Рекомендация']}")
                                
                                is_selected = row['id'] in st.session_state.selected_matches
                                if st.checkbox("➕ В комбинацию", value=is_selected, key=f"best_sel_{row['id']}"):
                                    if row['id'] not in st.session_state.selected_matches:
                                        st.session_state.selected_matches[row['id']] = row
                                else:
                                    if row['id'] in st.session_state.selected_matches:
                                        del st.session_state.selected_matches[row['id']]
                                st.markdown("---")
        
        if st.checkbox("Показать график сравнения вероятностей для лучших матчей", key="show_graph_best"):
            plot_df = df_all.copy()
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
            fig.update_layout(barmode='group', yaxis_title='Вероятность', xaxis_tickangle=-45, height=400)
            st.plotly_chart(fig, use_container_width=True)

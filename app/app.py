import os
import json
import logging
import time
import psycopg2
import psycopg2.extras
import streamlit as st
import pydeck as pdk
import pandas as pd

logger = logging.getLogger(__name__)


st.set_page_config(page_title="A to Z: UK", page_icon="🗺️", layout="wide")

PLACE_COLOURS = {
    "City": [220, 20, 60],
    "Town": [30, 115, 232],
    "Village": [46, 139, 87],
    "Hamlet": [160, 82, 45],
    "Suburban Area": [128, 0, 128],
    "Other Settlement": [105, 105, 105],
}

PLACE_TYPE_META = {
    "City": {"emoji": "\U0001F3D9\uFE0F", "tip": "Royal Charter status — a named centre of business and population vested with City status by the Crown."},
    "Town": {"emoji": "\U0001F3D8\uFE0F", "tip": "Built-up area exceeding 2.5 km\u00b2, or historically recognised (e.g. market / former county towns)."},
    "Village": {"emoji": "\u26EA", "tip": "Settlement smaller than a town but larger than a hamlet."},
    "Hamlet": {"emoji": "\U0001F33E", "tip": "A settlement smaller than a village, typically without a church or shops."},
    "Suburban Area": {"emoji": "\U0001F3E0", "tip": "A separately named urban area within a larger town or city."},
    "Other Settlement": {"emoji": "\U0001F4CD", "tip": "London Borough, Urban Development, Rural Locality, Crofting Locality, or Named Group of Buildings."},
}

COUNTRY_FLAGS = {
    None: "\U0001F1EC\U0001F1E7",
    "England": "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F",
    "Scotland": "\U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F",
    "Wales": "\U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F",
}

COUNTRY_NAMES = {
    None: "UK",
    "England": "England",
    "Scotland": "Scotland",
    "Wales": "Wales",
}

GB_CENTER = {"lat": 54.5, "lon": -2.5}

GAME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap');

[data-testid="stAppViewContainer"] {
    background: linear-gradient(170deg, #0f1923 0%, #1a2332 40%, #0d1b2a 100%);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { display: none !important; }

.game-title {
    font-family: 'Inter', sans-serif;
    font-size: 2.2rem; font-weight: 900;
    margin: 0; padding: 0; line-height: 1.2;
}
.game-title .title-text {
    background: linear-gradient(135deg, #ffd700 0%, #ffaa00 50%, #ff8c00 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.game-title .title-flag {
    -webkit-text-fill-color: initial;
}
.game-subtitle {
    font-family: 'Inter', sans-serif;
    font-size: 1rem; color: #6b8299; margin-top: 2px;
}
.game-sub-subtitle {
    font-family: 'Inter', sans-serif;
    font-size: 0.75rem; color: #4a6274; margin-top: 4px;
}
.game-sub-subtitle a {
    color: #6b8299;
    text-decoration: underline;
    text-decoration-color: #4a6274;
}
.game-sub-subtitle a:hover {
    color: #ffd700;
    text-decoration-color: #ffd700;
}
.game-subtitle .glow-link {
    color: #ffd700;
    text-decoration: none;
    text-shadow: 0 0 8px rgba(255, 215, 0, 0.6), 0 0 16px rgba(255, 215, 0, 0.3);
    cursor: pointer;
    font-style: italic;
    position: relative;
}
.game-subtitle .glow-link:hover {
    text-shadow: 0 0 12px rgba(255, 215, 0, 0.8), 0 0 24px rgba(255, 215, 0, 0.5);
}
.place-tooltip {
    display: none;
    position: absolute;
    top: 130%;
    left: 50%;
    transform: translateX(-50%);
    background: #1e2d3d;
    border: 1px solid #ffd700;
    border-radius: 10px;
    padding: 12px 16px;
    width: 320px;
    color: #c8d6e5;
    font-size: 0.8rem;
    font-style: normal;
    z-index: 9999;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    line-height: 1.4;
}
.glow-link-wrapper { position: relative; display: inline-block; }
.glow-link-wrapper:hover .place-tooltip { display: block; }

.letter-strip { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 16px; }
.letter-box {
    display: inline-flex; align-items: center; justify-content: center;
    width: 36px; height: 36px; border-radius: 8px;
    font-weight: 800; font-size: 15px; font-family: 'Inter', monospace;
    transition: all 0.2s ease;
}
.letter-pending { background: #1e2d3d; color: #4a6274; border: 1px solid #2a3f52; }
.letter-current {
    background: linear-gradient(135deg, #ffd700 0%, #ffaa00 100%);
    color: #1a1a2e; box-shadow: 0 0 16px rgba(255,215,0,0.4);
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 16px rgba(255,215,0,0.4); }
    50% { box-shadow: 0 0 24px rgba(255,215,0,0.7); }
}
.letter-done {
    background: linear-gradient(135deg, #00b894 0%, #00cec9 100%);
    color: white; border: none;
}
.letter-gold {
    background: linear-gradient(135deg, #ffd700 0%, #f39c12 100%);
    color: #1a1a2e; box-shadow: 0 0 12px rgba(255,215,0,0.5);
}
.letter-skipped { background: #1a242f; color: #3a4a5a; border: 1px solid #2a3540; }
.letter-wrong {
    background: linear-gradient(135deg, #8b0000 0%, #b22222 100%);
    color: white; border: none;
}
.letter-invalid { background: #141c26; color: #2a3540; text-decoration: line-through; }

.stat-row { display: flex; gap: 10px; margin-bottom: 16px; }
.stat-card {
    flex: 1; padding: 12px 8px; border-radius: 12px; text-align: center;
    background: linear-gradient(135deg, #1e2d3d 0%, #162032 100%);
    border: 1px solid #2a3f52;
}
.stat-card.highlight {
    background: linear-gradient(135deg, #0a3d2a 0%, #0d4f35 100%);
    border-color: #00b894;
}
.stat-card.streak {
    background: linear-gradient(135deg, #3d2a0a 0%, #4f3500 100%);
    border-color: #f39c12;
}
.stat-label {
    font-family: 'Inter', sans-serif;
    font-size: 10px; font-weight: 700; color: #6b8299;
    text-transform: uppercase; letter-spacing: 1px; margin-bottom: 2px;
}
.stat-value {
    font-family: 'Inter', sans-serif;
    font-size: 28px; font-weight: 900; color: #e8f0fe; line-height: 1.1;
}
.stat-value .fire { font-size: 20px; }

.prompt-card {
    background: linear-gradient(135deg, #1e2d3d 0%, #1a2838 100%);
    border: 1px solid #2a3f52; border-radius: 14px;
    padding: 20px; margin-bottom: 16px;
}
.prompt-letter {
    font-family: 'Inter', sans-serif;
    font-size: 3rem; font-weight: 900;
    background: linear-gradient(135deg, #ffd700, #ffaa00);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    display: inline-block; line-height: 1;
}
.prompt-text {
    font-family: 'Inter', sans-serif;
    font-size: 1rem; color: #8fa8c0; margin-top: 4px;
}

.cross-country-alert {
    background: linear-gradient(135deg, #2a1a00 0%, #3d2800 100%);
    border: 1px solid #b87333; border-radius: 10px;
    padding: 12px 16px; margin: 8px 0;
    color: #ffcc80; font-size: 0.9rem;
}

.distance-challenge {
    background: linear-gradient(135deg, #1a2040 0%, #1e2850 100%);
    border: 1px solid #4a6fa5; border-radius: 14px;
    padding: 18px; margin: 12px 0;
}
.distance-challenge-title {
    font-family: 'Inter', sans-serif; font-size: 1rem; font-weight: 800;
    color: #7eb8ff; margin-bottom: 8px;
}
.distance-challenge-places {
    font-family: 'Inter', sans-serif; font-size: 0.95rem;
    color: #c8d6e5; margin-bottom: 12px; line-height: 1.6;
}
.distance-result-correct {
    background: linear-gradient(135deg, #0a3d2a 0%, #0d4f35 100%);
    border: 1px solid #00b894; border-radius: 10px;
    padding: 12px 16px; margin: 8px 0; color: #a8e6cf;
}
.distance-result-close {
    background: linear-gradient(135deg, #2a3d0a 0%, #354f0d 100%);
    border: 1px solid #b8e600; border-radius: 10px;
    padding: 12px 16px; margin: 8px 0; color: #e6ffa8;
}
.distance-result-miss {
    background: linear-gradient(135deg, #3d0a0a 0%, #4f0d0d 100%);
    border: 1px solid #e74c3c; border-radius: 10px;
    padding: 12px 16px; margin: 8px 0; color: #f0a8a8;
}

div[data-testid="stForm"] {
    background: transparent !important;
    border: none !important; padding: 0 !important;
}

h1, h2, h3, h4, h5, h6, p, span, label, div {
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] .stMarkdown {
    color: #c8d6e5 !important;
}

.stTextInput > div > div > input {
    background: #1e2d3d !important; color: #e8f0fe !important;
    border: 1px solid #2a3f52 !important; border-radius: 10px !important;
    font-size: 1.1rem !important; padding: 10px 14px !important;
}
.stTextInput > div > div > input:focus {
    border-color: #ffd700 !important;
    box-shadow: 0 0 8px rgba(255,215,0,0.3) !important;
}
.stTextInput > div > div > input::placeholder { color: #4a6274 !important; }

.stSelectbox > div > div { background: #1e2d3d !important; border: 1px solid #2a3f52 !important; border-radius: 10px !important; }
.stSelectbox label { color: #8fa8c0 !important; }
.stSelectbox [data-baseweb="select"] * { color: #e8f0fe !important; }
.stSelectbox [data-baseweb="select"] svg { fill: #8fa8c0 !important; }
[data-baseweb="select"] > div { overflow: visible !important; }
[data-baseweb="select"] > div > div { overflow: visible !important; text-overflow: clip !important; }
[data-baseweb="select"] > div > div > div { overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; }
[data-baseweb="select"] span { overflow: visible !important; text-overflow: clip !important; white-space: nowrap !important; }
ul[role="listbox"] li { white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; }
ul[role="listbox"] li span { white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; }
[data-baseweb="menu"] [role="option"] { white-space: nowrap !important; overflow: visible !important; }
[data-baseweb="menu"] [role="option"] span { white-space: nowrap !important; overflow: visible !important; text-overflow: clip !important; }
[data-baseweb="popover"] { background: #1e2d3d !important; border: 1px solid #2a3f52 !important; }
[data-baseweb="popover"] * { background-color: #1e2d3d !important; }
[data-baseweb="popover"] li { color: #e8f0fe !important; background: #1e2d3d !important; }
[data-baseweb="popover"] li:hover { background: #2a3f52 !important; }
[data-baseweb="menu"] { background: #1e2d3d !important; }
[data-baseweb="menu"] * { background-color: #1e2d3d !important; }
[data-baseweb="menu"] [role="option"] { color: #e8f0fe !important; background: #1e2d3d !important; }
[data-baseweb="menu"] [role="option"]:hover { background: #2a3f52 !important; }
[data-baseweb="list"] { background: #1e2d3d !important; }
[data-baseweb="list"] * { background-color: #1e2d3d !important; }
[data-baseweb="list"] li { color: #e8f0fe !important; }
[data-baseweb="list"] li:hover { background: #2a3f52 !important; }
ul[role="listbox"] { background: #1e2d3d !important; }
ul[role="listbox"] li { background: #1e2d3d !important; color: #e8f0fe !important; }
ul[role="listbox"] li:hover { background: #2a3f52 !important; }
ul[role="listbox"] li[aria-selected="true"] { background: #2a3f52 !important; }

button[kind="primary"] {
    background: linear-gradient(135deg, #ffd700, #ffaa00) !important;
    color: #1a1a2e !important; font-weight: 700 !important;
    border: none !important; border-radius: 10px !important;
    text-shadow: none !important;
}
button[kind="primary"]:hover {
    background: linear-gradient(135deg, #ffaa00, #ff8c00) !important;
    box-shadow: 0 4px 16px rgba(255,170,0,0.3) !important;
}
button[kind="primary"] p, button[kind="primary"] span {
    color: #1a1a2e !important;
}
button[kind="secondary"] {
    background: #1e2d3d !important; color: #8fa8c0 !important;
    border: 1px solid #2a3f52 !important; border-radius: 10px !important;
}
button[kind="secondary"]:hover {
    border-color: #ffd700 !important; color: #ffd700 !important;
}
[data-testid="stFormSubmitButton"] button,
div[data-testid="stForm"] button {
    min-height: 42px !important; height: 42px !important;
}
div[data-testid="stForm"] button p {
    white-space: nowrap !important;
}

div[data-testid="stForm"] button[type="submit"] {
    background: linear-gradient(135deg, #ffd700, #ffaa00) !important;
    color: #1a1a2e !important; font-weight: 700 !important;
    border: none !important; border-radius: 10px !important;
}
div[data-testid="stForm"] button[type="submit"]:hover {
    background: linear-gradient(135deg, #ffaa00, #ff8c00) !important;
    box-shadow: 0 4px 16px rgba(255,170,0,0.3) !important;
}
div[data-testid="stForm"] button[type="submit"] p,
div[data-testid="stForm"] button[type="submit"] span {
    color: #1a1a2e !important;
}
button[data-testid="stFormSubmitButton"] {
    background: linear-gradient(135deg, #ffd700, #ffaa00) !important;
    color: #1a1a2e !important; font-weight: 700 !important;
    border: none !important; border-radius: 10px !important;
}
button[data-testid="stFormSubmitButton"] p,
button[data-testid="stFormSubmitButton"] span {
    color: #1a1a2e !important;
}
.stFormSubmitButton > button {
    background: linear-gradient(135deg, #ffd700, #ffaa00) !important;
    color: #1a1a2e !important; font-weight: 700 !important;
    border: none !important; border-radius: 10px !important;
}
.stFormSubmitButton > button p,
.stFormSubmitButton > button span {
    color: #1a1a2e !important;
}

[data-testid="stExpander"] {
    background: #1e2d3d !important; border: 1px solid #2a3f52 !important;
    border-radius: 12px !important;
}
[data-testid="stExpander"] summary span { color: #8fa8c0 !important; }
[data-testid="stExpander"] summary svg { display: none !important; }
[data-testid="stIconMaterial"] {
    font-size: 0 !important;
    width: 0 !important; height: 0 !important;
    overflow: hidden !important;
    display: inline-block !important;
}
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p { color: #c8d6e5 !important; }
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] li { color: #c8d6e5 !important; }
[data-testid="stExpander"] [data-testid="stMarkdownContainer"] strong { color: #ffd700 !important; }

.stDataFrame { border-radius: 10px; overflow: hidden; }

.claimed-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 0.85rem; }
.claimed-table th {
    background: #1a2838; color: #6b8299; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; font-size: 0.7rem; padding: 10px 12px; text-align: left;
    border-bottom: 2px solid #2a3f52;
}
.claimed-table td {
    padding: 8px 12px; color: #c8d6e5; border-bottom: 1px solid #1e2d3d;
}
.claimed-table tr { background: #141c26; }
.claimed-table tr:nth-child(even) { background: #1a2332; }
.claimed-table tr:hover { background: #1e2d3d; }

div[data-testid="stAlert"] {
    border-radius: 10px !important;
}

[data-testid="stDeployButton"] { color: #8fa8c0 !important; }
[data-testid="stDeployButton"] * { color: #8fa8c0 !important; }
[data-testid="stToolbar"] button { color: #8fa8c0 !important; }
[data-testid="stStatusWidget"] * { color: #c8d6e5 !important; }

div.stSuccess > div {
    background: #0a3d2a !important; border: 1px solid #00b894 !important;
    color: #a8e6cf !important; border-radius: 10px !important;
}
div.stWarning > div {
    background: #3d2a0a !important; border: 1px solid #f39c12 !important;
    color: #ffe0a8 !important; border-radius: 10px !important;
}
div.stError > div {
    background: #3d0a0a !important; border: 1px solid #e74c3c !important;
    color: #f0a8a8 !important; border-radius: 10px !important;
}
div.stInfo > div {
    background: #0a2d3d !important; border: 1px solid #1a73e8 !important;
    color: #a8d4f0 !important; border-radius: 10px !important;
}
</style>
"""


@st.cache_resource
def get_connection():
    try:
        if "postgres" in st.secrets:
            cfg = st.secrets["postgres"]
            return psycopg2.connect(
                host=cfg["host"], port=cfg.get("port", 5432),
                dbname=cfg.get("dbname", "postgres"), user=cfg["user"],
                password=cfg.get("password", ""), sslmode=cfg.get("sslmode", "require"),
                connect_timeout=5,
            )
        host = os.getenv("PG_HOST", "localhost")
        port = int(os.getenv("PG_PORT", "5432"))
        dbname = os.getenv("PG_DB", "az_game")
        user = os.getenv("PG_USER", "postgres")
        password = os.getenv("PG_PASSWORD", "")
        return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=5)
    except psycopg2.OperationalError:
        return None


def run_query(sql, params=None, fetch=True):
    try:
        conn = get_connection()
        if conn is None:
            return None
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetch:
                return cur.fetchall()
            conn.commit()
            return None
    except psycopg2.InterfaceError:
        get_connection.clear()
        return run_query(sql, params, fetch)
    except Exception as e:
        logger.exception("Database query failed")
        try:
            get_connection().rollback()
        except Exception:
            get_connection.clear()
        st.error("Something went wrong. Please try again.")
        return None


def call_function(sql, params=None):
    try:
        conn = get_connection()
        if conn is None:
            return None
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.fetchone()[0]
            conn.commit()
            if isinstance(result, str):
                return json.loads(result)
            return result
    except psycopg2.InterfaceError:
        get_connection.clear()
        return call_function(sql, params)
    except Exception as e:
        logger.exception("Database function call failed")
        try:
            get_connection().rollback()
        except Exception:
            get_connection.clear()
        st.error("Something went wrong. Please try again.")
        return None


def init_session_state():
    defaults = {
        "game_active": False,
        "session_id": None,
        "current_letter": "A",
        "valid_letters": [],
        "score": 0,
        "streak": 0,
        "best_streak": 0,
        "classified_count": 0,
        "letters_completed": [],
        "letters_skipped": [],
        "letters_wrong": [],
        "claimed_places": [],
        "last_result": None,
        "game_over": False,
        "answer_submitted": False,
        "awaiting_type_guess": False,
        "pending_place_name": None,
        "pending_result": None,
        "type_bonus_letters": [],
        "country_filter": None,
        "distance_challenge_active": False,
        "distance_challenge_data": None,
        "distance_bonus_total": 0,
        "distance_challenges_won": 0,
        "classification_feedback": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def get_country_flag():
    return COUNTRY_FLAGS.get(st.session_state.country_filter, COUNTRY_FLAGS[None])


def get_country_label():
    return COUNTRY_NAMES.get(st.session_state.country_filter, "Great Britain")


def render_header():
    st.markdown(GAME_CSS, unsafe_allow_html=True)

    flag = get_country_flag() if st.session_state.game_active else "\U0001F1EC\U0001F1E7"
    label = get_country_label() if st.session_state.game_active else "UK"

    st.markdown(f"""
    <div style="margin-bottom: 8px;">
        <div class="game-title"><span class="title-flag">{flag}</span> <span class="title-text">A to Z: {label}</span></div>
        <div class="game-subtitle">Name a <span class="glow-link-wrapper"><span class="glow-link">place</span><span class="place-tooltip"><strong>What counts as a &ldquo;place&rdquo;?</strong><br><br>We use Ordnance Survey Open Names, which defines populated places as: <strong>City</strong>, <strong>Town</strong>, <strong>Village</strong>, <strong>Hamlet</strong>, <strong>Suburban Area</strong>, and <strong>Other Settlement</strong> (London Boroughs, Rural Localities, Crofting Localities, Named Groups of Buildings). ~43K places across Great Britain.</span></span> for each letter of the alphabet (where possible)</div>
        <div class="game-sub-subtitle">Built with Snowflake Postgres/GIS and <a href="https://app.snowflake.com/marketplace/listing/GZ1MOZBWYYX" target="_blank">OS Open Names</a> (Ordnance Survey, OGL v3)</div>
    </div>
    """, unsafe_allow_html=True)


def render_alphabet_strip():
    valid = set(st.session_state.valid_letters)
    done = set(st.session_state.letters_completed)
    skipped = set(st.session_state.letters_skipped)
    wrong = set(st.session_state.letters_wrong)
    gold = set(st.session_state.type_bonus_letters)
    current = st.session_state.current_letter

    html_parts = ['<div class="letter-strip">']
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if c in gold:
            cls = "letter-gold"
        elif c in done:
            cls = "letter-done"
        elif c == current and st.session_state.game_active:
            cls = "letter-current"
        elif c in wrong:
            cls = "letter-wrong"
        elif c in skipped:
            cls = "letter-skipped"
        elif c not in valid:
            cls = "letter-invalid"
        else:
            cls = "letter-pending"
        html_parts.append(f'<span class="letter-box {cls}">{c}</span>')
    html_parts.append('</div>')

    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_score_bar():
    score = st.session_state.score
    streak = st.session_state.streak
    classified = st.session_state.classified_count
    done = len(st.session_state.letters_completed)
    total = len(st.session_state.valid_letters)
    skipped = len(st.session_state.letters_skipped)
    fire = ' <span class="fire">\U0001F525</span>' if streak > 0 else ''
    streak_cls = ' streak' if streak > 0 else ''
    score_cls = ' highlight' if score > 0 else ''
    classified_cls = ' streak' if classified > 0 else ''
    dist_won = st.session_state.distance_challenges_won
    dist_cls = ' highlight' if dist_won > 0 else ''
    st.markdown(f"""
    <div class="stat-row">
        <div class="stat-card{score_cls}"><div class="stat-label">Score</div><div class="stat-value">{score}</div></div>
        <div class="stat-card{streak_cls}"><div class="stat-label">Streak</div><div class="stat-value">{streak}{fire}</div></div>
        <div class="stat-card{classified_cls}"><div class="stat-label">Classified</div><div class="stat-value">{classified}</div></div>
        <div class="stat-card{dist_cls}"><div class="stat-label">Distance</div><div class="stat-value">{dist_won} \U0001F4CF</div></div>
        <div class="stat-card"><div class="stat-label">Completed</div><div class="stat-value">{done} / {total}</div></div>
    </div>
    """, unsafe_allow_html=True)


def render_map():
    claimed = st.session_state.claimed_places
    if not claimed:
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=[],
            get_position="[0,0]",
            get_radius=0,
        )
        view = pdk.ViewState(latitude=GB_CENTER["lat"], longitude=GB_CENTER["lon"], zoom=5, pitch=0)
    else:
        df = pd.DataFrame(claimed)
        df["colour"] = df["place_type"].map(lambda t: PLACE_COLOURS.get(t, [128, 128, 128]))

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position=["lon", "lat"],
            get_radius="points * 800 + 3000",
            get_fill_color="colour",
            pickable=True,
            opacity=0.8,
        )
        view = pdk.ViewState(
            latitude=df["lat"].mean(),
            longitude=df["lon"].mean(),
            zoom=5.5 if len(df) > 1 else 8,
            pitch=20,
        )

    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={"text": "{place_name}\n{place_type} in {county}, {country}\n{points} pts"},
            map_style="dark",
        ),
        use_container_width=True,
        height=500,
    )


def render_start_screen():
    st.markdown("")
    col_spacer_l, col_form, col_spacer_r = st.columns([1, 3, 1])
    with col_form:
        st.markdown("### \U0001F3AE Start a new game")

        col1, col2, col3 = st.columns([2, 3, 2])
        with col1:
            player_name = st.text_input("Your name", value="Player 1")
        with col2:
            difficulty = st.selectbox("Difficulty", [
                ("Any place", "any"),
                ("Cities & Towns", "city_or_town"),
                ("Cities only", "city_only"),
            ], format_func=lambda x: x[0])
        with col3:
            country_options = [
                ("UK \U0001F1EC\U0001F1E7", None),
                ("England \U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F", "England"),
                ("Scotland \U0001F3F4\U000E0067\U000E0062\U000E0073\U000E0063\U000E0074\U000E007F", "Scotland"),
                ("Wales \U0001F3F4\U000E0067\U000E0062\U000E0077\U000E006C\U000E0073\U000E007F", "Wales"),
            ]
            country = st.selectbox("Country", country_options, format_func=lambda x: x[0])

        if st.button("\U0001F680 Start Game", type="primary", use_container_width=True):
            result = call_function(
                "SELECT start_game(%s, %s, %s)",
                (player_name, difficulty[1], country[1])
            )
            if result and result.get("success"):
                st.session_state.game_active = True
                st.session_state.session_id = result["session_id"]
                st.session_state.current_letter = result["current_letter"]
                st.session_state.valid_letters = result["valid_letters"]
                st.session_state.country_filter = country[1]
                st.session_state.score = 0
                st.session_state.streak = 0
                st.session_state.best_streak = 0
                st.session_state.classified_count = 0
                st.session_state.letters_completed = []
                st.session_state.letters_skipped = []
                st.session_state.letters_wrong = []
                st.session_state.claimed_places = []
                st.session_state.last_result = None
                st.session_state.game_over = False
                st.session_state.answer_submitted = False
                st.session_state.awaiting_type_guess = False
                st.session_state.pending_place_name = None
                st.session_state.pending_result = None
                st.session_state.type_bonus_letters = []
                st.session_state.distance_challenge_active = False
                st.session_state.distance_challenge_data = None
                st.session_state.distance_bonus_total = 0
                st.session_state.distance_challenges_won = 0
                st.rerun()
            elif result:
                st.error(result.get("error", "Failed to start game"))

    st.markdown("")
    col_spacer_l2, col_how, col_spacer_r2 = st.columns([1, 3, 1])
    with col_how:
        with st.expander("\U0001F4D6 How to play", expanded=False):
            st.markdown("""
1. For each letter of the alphabet, **name a real place** in the UK
2. Cities are worth **10 pts**, Towns **5 pts**, Villages **3 pts**, Hamlets **2 pts**
3. After a correct name, **classify the place type** for a **+5 bonus**
4. **Distance challenge**: after claiming 2+ places, guess the distance between them **as the crow flies** for **up to +10 bonus** (PostGIS spatial calculation)
5. Build a **streak** by answering consecutive letters correctly
6. Use **hints** if you're stuck — they reveal the county and first two letters
            """)

    st.divider()
    render_leaderboard()


def advance_letter(skip=False):
    if skip:
        st.session_state.letters_skipped.append(st.session_state.current_letter)
        st.session_state.streak = 0
    advance = call_function(
        "SELECT next_letter(%s, %s)",
        (st.session_state.session_id, skip)
    )
    if advance and advance.get("game_over"):
        st.session_state.game_over = True
        st.session_state.game_active = False
    elif advance:
        st.session_state.current_letter = advance["current_letter"]


def handle_correct_answer(result, type_guess):
    letter = result["letter"]
    place = result["matched_place"]
    points = result["points"]
    is_type_bonus = result.get("type_bonus", False)

    st.session_state.score += points
    st.session_state.streak += 1
    st.session_state.best_streak = max(st.session_state.best_streak, st.session_state.streak)
    st.session_state.letters_completed.append(letter)
    if type_guess:
        actual_type = place["type"]
        if is_type_bonus:
            st.session_state.type_bonus_letters.append(letter)
            st.session_state.classified_count += 1
            st.session_state.classification_feedback = {
                "correct": True,
                "place": place["name"],
                "guessed": type_guess,
                "actual": actual_type,
                "points": points,
            }
        else:
            st.session_state.classification_feedback = {
                "correct": False,
                "place": place["name"],
                "guessed": type_guess,
                "actual": actual_type,
                "points": points,
            }
    else:
        st.session_state.classification_feedback = None
    st.session_state.claimed_places.append({
        "place_name": place["name"],
        "place_type": place["type"],
        "country": place["country"],
        "county": place.get("county") or "",
        "lat": place["lat"],
        "lon": place["lon"],
        "letter": letter,
        "points": points,
    })

    claimed = st.session_state.claimed_places
    if len(claimed) >= 2:
        prev = claimed[-2]
        curr = claimed[-1]
        dist_result = call_function(
            "SELECT distance_between_answers(%s, %s, %s)",
            (st.session_state.session_id, prev["letter"], curr["letter"])
        )
        if dist_result and dist_result.get("success"):
            st.session_state.distance_challenge_active = True
            st.session_state.distance_challenge_data = {
                "place1": prev["place_name"],
                "place2": curr["place_name"],
                "letter1": prev["letter"],
                "letter2": curr["letter"],
                "actual_km": dist_result["distance_km"],
                "actual_miles": dist_result["distance_miles"],
            }
            return

    advance_letter(skip=False)


def calculate_distance_bonus(guess, actual):
    if actual == 0:
        return 0, "miss"
    pct_error = abs(guess - actual) / actual * 100
    if pct_error <= 10:
        return 10, "correct"
    elif pct_error <= 25:
        return 5, "close"
    elif pct_error <= 50:
        return 2, "close"
    return 0, "miss"


def render_distance_challenge():
    data = st.session_state.distance_challenge_data
    if not data:
        return

    st.markdown(f"""
    <div class="distance-challenge">
        <div class="distance-challenge-title">\U0001F4CF Distance Challenge — PostGIS Bonus Round!</div>
        <div class="distance-challenge-places">
            How far is it from <strong>{data['place1']}</strong> ({data['letter1']})
            to <strong>{data['place2']}</strong> ({data['letter2']}) <em>as the crow flies</em>?
        </div>
    </div>
    """, unsafe_allow_html=True)

    dc_key = f"dc_{data['letter1']}_{data['letter2']}_{len(st.session_state.letters_completed)}"
    unit_key = f"dc_unit_{dc_key}"
    guess_key = f"dc_guess_{dc_key}"

    col_guess, col_unit = st.columns([3, 1])
    with col_guess:
        guess = st.number_input(
            "Your guess",
            min_value=0.0,
            max_value=2000.0,
            value=50.0,
            step=5.0,
            key=guess_key,
            label_visibility="collapsed",
        )
    with col_unit:
        unit = st.selectbox("Unit", ["miles", "km"], key=unit_key, label_visibility="collapsed")

    col_submit_dc, col_skip_dc = st.columns(2)
    with col_submit_dc:
        if st.button("\U0001F4CF Check Distance", type="primary", use_container_width=True):
            actual = data["actual_miles"] if unit == "miles" else data["actual_km"]
            bonus, tier = calculate_distance_bonus(guess, actual)

            if bonus > 0:
                st.session_state.score += bonus
                st.session_state.distance_bonus_total += bonus
                st.session_state.distance_challenges_won += 1

            actual_mi = data["actual_miles"]
            actual_km = data["actual_km"]
            if tier == "correct":
                st.markdown(f"""<div class="distance-result-correct">
                    \U0001F3AF <strong>Excellent!</strong> The actual distance is <strong>{actual_mi} miles</strong>
                    ({actual_km} km). Your guess of {guess} {unit} was within 10%! <strong>+{bonus} bonus points</strong>
                    <br><em>Calculated using PostGIS ST_Distance (great-circle on WGS84 spheroid)</em>
                </div>""", unsafe_allow_html=True)
            elif tier == "close":
                st.markdown(f"""<div class="distance-result-close">
                    \U0001F44D <strong>Close!</strong> The actual distance is <strong>{actual_mi} miles</strong>
                    ({actual_km} km). <strong>+{bonus} bonus points</strong>
                    <br><em>Calculated using PostGIS ST_Distance (great-circle on WGS84 spheroid)</em>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="distance-result-miss">
                    \U0001F4CD The actual distance is <strong>{actual_mi} miles</strong>
                    ({actual_km} km). No bonus this time.
                    <br><em>Calculated using PostGIS ST_Distance (great-circle on WGS84 spheroid)</em>
                </div>""", unsafe_allow_html=True)

            import time
            time.sleep(2)
            st.session_state.distance_challenge_active = False
            st.session_state.distance_challenge_data = None
            st.session_state.classification_feedback = None
            advance_letter(skip=False)
            st.rerun()

    with col_skip_dc:
        if st.button("\u23ED\uFE0F Skip Challenge", use_container_width=True):
            st.session_state.distance_challenge_active = False
            st.session_state.distance_challenge_data = None
            st.session_state.classification_feedback = None
            advance_letter(skip=False)
            st.rerun()


def render_game_screen():
    render_alphabet_strip()
    render_score_bar()

    col_game, col_map = st.columns([3, 4])

    with col_game:
        letter = st.session_state.current_letter
        flag = get_country_flag()
        label = get_country_label()

        st.markdown(f"""
        <div class="prompt-card">
            <span class="prompt-letter">{letter}</span>
            <div class="prompt-text">{flag} Name a place in <strong>{label}</strong> starting with '{letter}'</div>
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.distance_challenge_active:
            fb = st.session_state.classification_feedback
            if fb:
                if fb["correct"]:
                    st.success(f"\u2705 **Classification correct!** {fb['place']} is a **{fb['actual']}**. +{fb['points']} points (includes **+5 type bonus**)")
                else:
                    st.warning(f"\u274C Not quite — **{fb['place']}** is a **{fb['actual']}**, not a {fb['guessed']}. +{fb['points']} points")
            render_distance_challenge()
        elif st.session_state.awaiting_type_guess:
            pending = st.session_state.pending_result
            st.success(f"\u2705 **{pending['place_name']}** is valid! Now classify it:")

            type_options = ["City", "Town", "Village", "Hamlet", "Suburban Area", "Other Settlement"]
            type_key = f"type_sel_{letter}_{len(st.session_state.letters_completed)}"
            if type_key not in st.session_state:
                st.session_state[type_key] = None

            type_labels = {
                "City": "City",
                "Town": "Town",
                "Village": "Village",
                "Hamlet": "Hamlet",
                "Suburban Area": "Suburb",
                "Other Settlement": "Other",
            }
            btn_cols_t = st.columns(3)
            for i, t in enumerate(type_options):
                meta = PLACE_TYPE_META[t]
                with btn_cols_t[i % 3]:
                    sel = st.session_state[type_key] == t
                    if st.button(
                        f"{meta['emoji']} {type_labels[t]}",
                        key=f"tbtn_{t}_{letter}_{len(st.session_state.letters_completed)}",
                        type="primary" if sel else "secondary",
                        use_container_width=True,
                        help=meta['tip'],
                    ):
                        st.session_state[type_key] = t
                        st.rerun()

            chosen = st.session_state[type_key]
            if chosen:
                st.caption(f"Selected: **{PLACE_TYPE_META[chosen]['emoji']} {chosen}** — {PLACE_TYPE_META[chosen]['tip']}")

            if st.button("\u2705 Confirm", type="primary", use_container_width=True, disabled=chosen is None):
                result = call_function(
                    "SELECT submit_answer(%s, %s, %s)",
                    (st.session_state.session_id, st.session_state.pending_place_name, chosen)
                )
                if result:
                    st.session_state.last_result = result
                    handle_correct_answer(result, chosen)
                    st.session_state.awaiting_type_guess = False
                    st.session_state.pending_place_name = None
                    st.session_state.pending_result = None
                    st.rerun()
        else:
            with st.form(key=f"answer_form_{letter}_{len(st.session_state.letters_completed)}", clear_on_submit=False, border=False):
                answer = st.text_input(
                    f"Place beginning with {letter}",
                    key=f"answer_{letter}_{len(st.session_state.letters_completed)}",
                    placeholder=f"e.g. {'London' if letter == 'L' else letter + '...'}",
                    label_visibility="collapsed",
                )
                btn_cols = st.columns(3)
                with btn_cols[0]:
                    submit = st.form_submit_button("\U0001F50D Submit", type="primary", use_container_width=True)
                with btn_cols[1]:
                    skip = st.form_submit_button("\u23ED\uFE0F Skip", use_container_width=True)
                with btn_cols[2]:
                    hint = st.form_submit_button("\U0001F4A1 Hint", use_container_width=True)

            if submit and answer.strip():
                check = call_function(
                    "SELECT check_place(%s, %s)",
                    (st.session_state.session_id, answer.strip())
                )
                if check:
                    if check.get("is_valid"):
                        st.session_state.awaiting_type_guess = True
                        st.session_state.pending_place_name = answer.strip()
                        st.session_state.pending_result = check
                        st.session_state.last_result = None
                        st.rerun()
                    elif check.get("fuzzy_suggestion") or check.get("cross_country"):
                        st.session_state.last_result = {
                            "is_correct": False,
                            "fuzzy_suggestion": {"name": check["fuzzy_suggestion"]} if check.get("fuzzy_suggestion") else None,
                            "cross_country": check.get("cross_country"),
                        }
                        st.rerun()
                    else:
                        st.session_state.letters_wrong.append(st.session_state.current_letter)
                        st.session_state.streak = 0
                        st.session_state.last_result = {"is_wrong": True, "guess": answer.strip()}
                        advance = call_function(
                            "SELECT next_letter(%s, %s)",
                            (st.session_state.session_id, True)
                        )
                        if advance and advance.get("game_over"):
                            st.session_state.game_over = True
                            st.session_state.game_active = False
                        elif advance:
                            st.session_state.current_letter = advance["current_letter"]
                        st.rerun()

            if skip:
                advance_letter(skip=True)
                st.session_state.last_result = None
                st.rerun()

            if hint:
                hint_result = call_function(
                    "SELECT get_hint(%s)", (st.session_state.session_id,)
                )
                if hint_result:
                    st.info(
                        f"\U0001F4A1 **Hint**: There's a **{hint_result['type']}** in "
                        f"**{hint_result.get('county') or hint_result.get('region', '?')}**, "
                        f"{hint_result['country']}. "
                        f"Name: **{hint_result['masked_name']}** ({hint_result['name_length']} letters)"
                    )

            if st.session_state.last_result:
                res = st.session_state.last_result
                if res.get("is_wrong"):
                    st.error(f"\u274C **\"{res['guess']}\"** — not found. No matching place in our database. Moving on!")
                elif res.get("is_correct"):
                    place = res["matched_place"]
                    if res.get("type_bonus"):
                        msg = f"\u2705 **Classification correct!** +{res['points']} points (includes **+5 type bonus**)"
                    else:
                        msg = f"\u2705 **{place['name']}** claimed — it's a **{place['type']}**. +{res['points']} points"
                    st.success(msg)
                else:
                    cross = res.get("cross_country")
                    if cross:
                        cross_flag = COUNTRY_FLAGS.get(cross["country"], "")
                        cross_county = f", {cross['county']}" if cross.get("county") else ""
                        st.markdown(f"""
                        <div class="cross-country-alert">
                            \u26A0\uFE0F <strong>{cross['name']}</strong> is a {cross['type']} in {cross_flag} <strong>{cross['country']}</strong>{cross_county} — but you're playing the <strong>{get_country_label()}</strong> game! Try a place in {get_country_flag()} {get_country_label()}.
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        msg = "\u274C **Not found** — that place doesn't match any in our database."
                        fuzzy = res.get("fuzzy_suggestion")
                        if fuzzy:
                            name = fuzzy["name"] if isinstance(fuzzy, dict) else fuzzy
                            msg += f" Did you mean **{name}**?"
                        st.warning(msg)

    with col_map:
        render_map()

    if st.session_state.claimed_places:
        with st.expander(f"\U0001F4CD Claimed places ({len(st.session_state.claimed_places)})"):
            claimed = st.session_state.claimed_places
            rows_html = []
            for i, p in enumerate(claimed):
                dist_col = ""
                if i > 0:
                    prev = claimed[i - 1]
                    dist_result = call_function(
                        "SELECT distance_between_answers(%s, %s, %s)",
                        (st.session_state.session_id, prev["letter"], p["letter"])
                    )
                    if dist_result and dist_result.get("success"):
                        dist_col = f"{dist_result['distance_miles']} mi"
                rows_html.append(
                    f"<tr><td>{p['letter']}</td><td>{p['place_name']}</td>"
                    f"<td>{p['place_type']}</td><td>{p.get('county','')}</td>"
                    f"<td>{p['country']}</td><td>{p['points']}</td>"
                    f"<td>{dist_col}</td></tr>"
                )
            table_html = f"""
            <table class="claimed-table">
                <thead><tr>
                    <th>Letter</th><th>Place</th><th>Type</th>
                    <th>County</th><th>Country</th><th>Pts</th><th>Distance</th>
                </tr></thead>
                <tbody>{''.join(rows_html)}</tbody>
            </table>
            """
            st.markdown(table_html, unsafe_allow_html=True)


def render_game_over():
    st.balloons()
    st.markdown("## \U0001F3C6 Game Over!")

    render_alphabet_strip()
    st.markdown("")
    render_score_bar()

    col1, col2 = st.columns([2, 3])
    with col1:
        flag = COUNTRY_FLAGS.get(st.session_state.country_filter, COUNTRY_FLAGS[None])
        label = COUNTRY_NAMES.get(st.session_state.country_filter, "UK")
        st.markdown(f"### {flag} Your journey across {label}")
        if st.session_state.claimed_places:
            df = pd.DataFrame(st.session_state.claimed_places)
            st.dataframe(
                df[["place_name", "place_type", "county", "country", "points"]],
                hide_index=True,
                use_container_width=True,
            )

        if st.button("\U0001F504 Play Again", type="primary", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    with col2:
        render_map()

    st.divider()
    render_leaderboard()


def render_leaderboard():
    rows = run_query("""
        SELECT player_name, difficulty, country_filter,
               total_score, letters_completed, letters_skipped,
               best_streak, duration_secs, completed_at
        FROM leaderboard
        ORDER BY total_score DESC
        LIMIT 20
    """)
    if rows:
        st.markdown("### \U0001F3C5 Leaderboard")
        df = pd.DataFrame(rows)
        df["country_filter"] = df["country_filter"].fillna("All GB")
        df["duration"] = df["duration_secs"].apply(
            lambda s: f"{s // 60}m {s % 60}s" if s else "\u2014"
        )
        st.dataframe(
            df[["player_name", "difficulty", "country_filter", "total_score",
                "letters_completed", "letters_skipped", "best_streak", "duration"]],
            hide_index=True,
            use_container_width=True,
        )


def render_about_tab():
    st.markdown("### \U0001F4E1 About A to Z: UK")
    st.markdown("""A geography quiz game where you name a real place in Great Britain for each letter
of the alphabet, then classify the settlement type for bonus points. Answers are plotted on
an interactive map as you go.""")

    st.markdown("#### Data source")
    st.markdown("""Place data comes from **[OS Open Names](https://app.snowflake.com/marketplace/listing/GZ1MOZBWYYX)**
(Ordnance Survey, OGL v3), available on the Snowflake Marketplace. It covers ~43,254 populated places across
England, Scotland, and Wales, categorised as Cities, Towns, Villages, Hamlets, Suburban Areas, and Other Settlements.""")

    st.markdown("#### Architecture")
    col_data, col_back, col_front = st.columns(3)
    with col_data:
        st.markdown("""**Data Pipeline**
- OS Open Names seeded from Snowflake \u2192 Snowflake Postgres via Python connector
- Filtered to populated-place types only""")
    with col_back:
        st.markdown("""**Backend — Snowflake Postgres**
- PostgreSQL 18 (STANDARD_M)
- **PostGIS** — spatial queries, GIST indexes
- **pg_trgm** — fuzzy text matching
- **h3** / **h3_postgis** — hexagonal spatial indexing
- **PL/pgSQL** — all game logic as DB functions""")
    with col_front:
        st.markdown("""**Frontend — Streamlit**
- **pydeck** for interactive map visualisation
- Custom CSS dark game theme
- Session state for full game lifecycle""")

    st.markdown("#### How PostGIS powers the game")
    st.markdown("""Every answer triggers real PostGIS spatial operations:
- **ST_DWithin** — nearby-place search using GIST-indexed radius queries
- **ST_Distance** — distance challenge bonus round: guess the great-circle distance between claimed places (WGS84 spheroid)
- **ST_MakePoint / ST_SetSRID** — geometry creation from OS Open Names coordinates
- **pg_trgm similarity()** — typo tolerance (e.g. \"Colchster\" \u2192 \"Colchester\")""")

    st.markdown("#### Future plans")
    st.markdown("""- \U0001F4CA **Population bonus round** — guess the population of your claimed place
- \U0001F4C5 **Daily challenges** — pg_cron-generated daily target letter + country + category
- \U0001F6E1\uFE0F **H3 heatmap** — visualise place density using H3 hexagonal cells
- \U0001F3AE **Multi-player mode** — real-time competitive play using PostgreSQL LISTEN/NOTIFY""")

    st.markdown("#### Tech stack")
    st.markdown("""
| Component | Technology |
|-----------|------------|
| Database | Snowflake Postgres (PG18) |
| Spatial | PostGIS + postgis_sfcgal |
| Fuzzy matching | pg_trgm (trigram similarity) |
| Hex indexing | h3 + h3_postgis |
| Data source | OS Open Names via Snowflake Marketplace |
| Frontend | Streamlit + pydeck |
""")


def render_sleeping():
    st.markdown("""
    <div style="text-align: center; padding: 60px 20px;">
        <div style="font-size: 4rem; margin-bottom: 16px;">\U0001F634</div>
        <div style="font-family: 'Inter', sans-serif; font-size: 1.5rem; font-weight: 800; color: #ffd700; margin-bottom: 12px;">The game is sleeping...</div>
        <div style="font-family: 'Inter', sans-serif; font-size: 1rem; color: #8fa8c0; line-height: 1.6;">
            A to Z: UK is available daily from <strong>08:00</strong> to <strong>22:00 UTC</strong>.<br>
            The database is powered by Snowflake Postgres and takes a well-earned rest overnight.<br><br>
            Come back tomorrow morning and test your UK geography knowledge!
        </div>
    </div>
    """, unsafe_allow_html=True)


def main():
    init_session_state()
    render_header()

    conn = get_connection()
    if conn is None:
        get_connection.clear()
        render_sleeping()
        return

    if st.session_state.game_over:
        render_game_over()
    elif st.session_state.game_active:
        tab_game, tab_about = st.tabs(["\U0001F3AE Game", "\U0001F4D6 About"])
        with tab_game:
            render_game_screen()
        with tab_about:
            render_about_tab()
    else:
        tab_start, tab_about = st.tabs(["\U0001F3AE Play", "\U0001F4D6 About"])
        with tab_start:
            render_start_screen()
        with tab_about:
            render_about_tab()


if __name__ == "__main__":
    main()

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cinematch.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER UNIQUE NOT NULL,
        title TEXT NOT NULL,
        year INTEGER,
        genre TEXT DEFAULT '',
        director TEXT DEFAULT '',
        runtime INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        poster_url TEXT DEFAULT '',
        rotten_tomatoes_score INTEGER,
        streaming_services TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id INTEGER NOT NULL,
        watched_date DATE DEFAULT CURRENT_DATE,
        user_rating INTEGER CHECK(user_rating BETWEEN 1 AND 5),
        mood_tag TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        FOREIGN KEY (movie_id) REFERENCES movies(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS watchlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        movie_id INTEGER NOT NULL UNIQUE,
        added_date DATE DEFAULT CURRENT_DATE,
        priority INTEGER DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
        FOREIGN KEY (movie_id) REFERENCES movies(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
        id INTEGER PRIMARY KEY DEFAULT 1,
        favorite_genres TEXT DEFAULT '[]',
        excluded_genres TEXT DEFAULT '[]',
        favorite_moods TEXT DEFAULT '[]',
        preferred_decades TEXT DEFAULT '[]',
        streaming_services TEXT DEFAULT '[]'
    )''')

    c.execute("INSERT OR IGNORE INTO user_preferences (id) VALUES (1)")

    conn.commit()
    conn.close()


def _parse_json(val):
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) if val else []
    except Exception:
        return []


def _row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    if 'streaming_services' in d:
        d['streaming_services'] = _parse_json(d['streaming_services'])
    return d


# ── Movies ──────────────────────────────────────────────────────────────────

def get_movie_by_tmdb_id(tmdb_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM movies WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def get_movie_by_id(movie_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM movies WHERE id = ?", (movie_id,)).fetchone()
    conn.close()
    return _row_to_dict(row)


def upsert_movie(tmdb_id, title, year, genre, director, runtime, description,
                 poster_url, rt_score, streaming_services):
    conn = get_db()
    c = conn.cursor()
    streaming_json = json.dumps(streaming_services) if isinstance(streaming_services, list) else streaming_services

    existing = conn.execute("SELECT id FROM movies WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
    if existing:
        c.execute(
            """UPDATE movies SET title=?, year=?, genre=?, director=?, runtime=?,
               description=?, poster_url=?, rotten_tomatoes_score=?, streaming_services=?
               WHERE tmdb_id=?""",
            (title, year, genre, director, runtime, description, poster_url,
             rt_score, streaming_json, tmdb_id),
        )
        movie_id = existing["id"]
    else:
        c.execute(
            """INSERT INTO movies
               (tmdb_id, title, year, genre, director, runtime, description,
                poster_url, rotten_tomatoes_score, streaming_services)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tmdb_id, title, year, genre, director, runtime, description,
             poster_url, rt_score, streaming_json),
        )
        movie_id = c.lastrowid

    conn.commit()
    conn.close()
    return movie_id


def get_all_movies():
    conn = get_db()
    rows = conn.execute("SELECT * FROM movies ORDER BY title").fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# ── Watch History ────────────────────────────────────────────────────────────

def log_watch(movie_id, user_rating, mood_tag="", notes="", watched_date=None):
    if watched_date is None:
        watched_date = datetime.now().strftime("%Y-%m-%d")
    conn = get_db()
    conn.execute(
        """INSERT INTO watch_history (movie_id, watched_date, user_rating, mood_tag, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (movie_id, watched_date, user_rating, mood_tag, notes),
    )
    conn.commit()
    conn.close()


def get_watch_history(limit=50):
    conn = get_db()
    rows = conn.execute(
        """SELECT wh.id, wh.movie_id, wh.watched_date, wh.user_rating, wh.mood_tag, wh.notes,
                  m.title, m.year, m.poster_url, m.genre, m.director, m.runtime,
                  m.rotten_tomatoes_score, m.streaming_services, m.tmdb_id
           FROM watch_history wh
           JOIN movies m ON wh.movie_id = m.id
           ORDER BY wh.watched_date DESC, wh.id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_watched_movie_ids():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT movie_id FROM watch_history").fetchall()
    conn.close()
    return {r["movie_id"] for r in rows}


def delete_history_entry(entry_id):
    conn = get_db()
    conn.execute("DELETE FROM watch_history WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


# ── Watchlist ────────────────────────────────────────────────────────────────

def add_to_watchlist(movie_id, priority=3):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO watchlist (movie_id, priority, added_date) VALUES (?, ?, ?)",
            (movie_id, priority, datetime.now().strftime("%Y-%m-%d")),
        )
        conn.commit()
        success = True
    except Exception:
        success = False
    conn.close()
    return success


def get_watchlist():
    conn = get_db()
    rows = conn.execute(
        """SELECT wl.id, wl.movie_id, wl.added_date, wl.priority,
                  m.title, m.year, m.poster_url, m.genre, m.director,
                  m.runtime, m.rotten_tomatoes_score, m.streaming_services, m.tmdb_id,
                  m.description
           FROM watchlist wl
           JOIN movies m ON wl.movie_id = m.id
           ORDER BY wl.priority DESC, wl.added_date DESC""",
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_watchlist_movie_ids():
    conn = get_db()
    rows = conn.execute("SELECT movie_id FROM watchlist").fetchall()
    conn.close()
    return {r["movie_id"] for r in rows}


def remove_from_watchlist(watchlist_id):
    conn = get_db()
    conn.execute("DELETE FROM watchlist WHERE id = ?", (watchlist_id,))
    conn.commit()
    conn.close()


def update_watchlist_priority(watchlist_id, priority):
    conn = get_db()
    conn.execute("UPDATE watchlist SET priority = ? WHERE id = ?", (priority, watchlist_id))
    conn.commit()
    conn.close()


# ── Preferences ──────────────────────────────────────────────────────────────

def get_preferences():
    conn = get_db()
    row = conn.execute("SELECT * FROM user_preferences WHERE id = 1").fetchone()
    conn.close()
    if row:
        prefs = dict(row)
        for field in ["favorite_genres", "excluded_genres", "favorite_moods",
                      "preferred_decades", "streaming_services"]:
            prefs[field] = _parse_json(prefs.get(field))
        return prefs
    return {
        "favorite_genres": [], "excluded_genres": [], "favorite_moods": [],
        "preferred_decades": [], "streaming_services": [],
    }


def update_preferences(favorite_genres, excluded_genres, favorite_moods,
                       preferred_decades, streaming_services):
    conn = get_db()
    conn.execute(
        """UPDATE user_preferences SET
           favorite_genres=?, excluded_genres=?, favorite_moods=?,
           preferred_decades=?, streaming_services=?
           WHERE id=1""",
        (json.dumps(favorite_genres), json.dumps(excluded_genres),
         json.dumps(favorite_moods), json.dumps(preferred_decades),
         json.dumps(streaming_services)),
    )
    conn.commit()
    conn.close()


# ── Stats ────────────────────────────────────────────────────────────────────

def get_stats():
    conn = get_db()
    total_watched = conn.execute("SELECT COUNT(*) FROM watch_history").fetchone()[0]
    avg_rating = conn.execute(
        "SELECT AVG(user_rating) FROM watch_history WHERE user_rating IS NOT NULL"
    ).fetchone()[0]
    watchlist_count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    top_genre = conn.execute(
        """SELECT m.genre FROM watch_history wh
           JOIN movies m ON wh.movie_id = m.id
           WHERE m.genre != ''
           GROUP BY m.genre ORDER BY COUNT(*) DESC LIMIT 1"""
    ).fetchone()
    conn.close()
    return {
        "total_watched": total_watched,
        "avg_rating": round(avg_rating, 1) if avg_rating else 0,
        "watchlist_count": watchlist_count,
        "top_genre": top_genre[0].split(",")[0].strip() if top_genre else "—",
    }

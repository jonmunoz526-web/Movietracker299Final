import os
import json
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

from database import (
    init_db, get_movie_by_tmdb_id, get_movie_by_id, upsert_movie,
    log_watch, get_watch_history, get_watched_movie_ids,
    delete_history_entry, add_to_watchlist, get_watchlist,
    get_watchlist_movie_ids, remove_from_watchlist, update_watchlist_priority,
    get_preferences, update_preferences, get_all_movies, get_stats,
)
from recommender import score_movies, ALL_MOODS, ALL_GENRES, ALL_DECADES

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cinematch-dev-key")

init_db()

TMDB_KEY  = os.getenv("TMDB_API_KEY", "")
OMDB_KEY  = os.getenv("OMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "https://www.omdbapi.com"


# ── TMDB / OMDb helpers ──────────────────────────────────────────────────────

def _tmdb_get(path, **params):
    if not TMDB_KEY:
        return None
    try:
        r = requests.get(
            f"{TMDB_BASE}{path}",
            params={"api_key": TMDB_KEY, **params},
            timeout=8,
        )
        return r.json() if r.ok else None
    except Exception:
        return None


def _fetch_rt_score(title, year):
    if not OMDB_KEY:
        return None
    try:
        r = requests.get(
            OMDB_BASE,
            params={"apikey": OMDB_KEY, "t": title, "y": year},
            timeout=6,
        )
        if not r.ok:
            return None
        for rating in r.json().get("Ratings", []):
            if rating["Source"] == "Rotten Tomatoes":
                try:
                    return int(rating["Value"].replace("%", ""))
                except ValueError:
                    return None
    except Exception:
        return None
    return None


def _fetch_streaming(tmdb_id):
    data = _tmdb_get(f"/movie/{tmdb_id}/watch/providers")
    if not data:
        return []
    results = data.get("results", {})
    us = results.get("US", {})
    return [p["provider_name"] for p in us.get("flatrate", [])]


def enrich_and_store(tmdb_id):
    """Fetch full movie details from TMDB + OMDb and persist them. Returns movie_id."""
    details = _tmdb_get(f"/movie/{tmdb_id}", append_to_response="credits")
    if not details:
        return None

    title  = details.get("title", "")
    year   = int(details.get("release_date", "0")[:4]) if details.get("release_date") else None
    genres = ", ".join(g["name"] for g in details.get("genres", []))
    runtime = details.get("runtime") or 0
    desc   = details.get("overview", "")
    poster = details.get("poster_path", "")
    poster_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else ""

    director = ""
    for crew in details.get("credits", {}).get("crew", []):
        if crew.get("job") == "Director":
            director = crew["name"]
            break

    rt_score  = _fetch_rt_score(title, year)
    streaming = _fetch_streaming(tmdb_id)

    return upsert_movie(
        tmdb_id, title, year, genres, director, runtime,
        desc, poster_url, rt_score, streaming,
    )


def _ensure_movie(tmdb_id):
    """Return local movie_id, fetching from TMDB if needed."""
    movie = get_movie_by_tmdb_id(tmdb_id)
    if movie:
        return movie["id"]
    return enrich_and_store(tmdb_id)


# ── Page routes ──────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    history  = get_watch_history(10)
    watchlist = get_watchlist()[:6]
    stats    = get_stats()
    return render_template("dashboard.html", history=history,
                           watchlist=watchlist, stats=stats)


@app.route("/search")
def search_page():
    return render_template("search.html")


@app.route("/recommendations")
def recommendations_page():
    prefs   = get_preferences()
    movie_count = len(get_all_movies())
    return render_template("recommendations.html", preferences=prefs,
                           all_moods=ALL_MOODS, all_genres=ALL_GENRES,
                           movie_count=movie_count)


@app.route("/watchlist")
def watchlist_page():
    wl = get_watchlist()
    return render_template("watchlist.html", watchlist=wl)


@app.route("/profile")
def profile_page():
    prefs = get_preferences()
    return render_template("profile.html", preferences=prefs,
                           all_genres=ALL_GENRES, all_moods=ALL_MOODS,
                           all_decades=ALL_DECADES)


# ── API: Search ──────────────────────────────────────────────────────────────

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    if not TMDB_KEY:
        return jsonify({"error": "TMDB_API_KEY not set in .env"}), 500

    data = _tmdb_get("/search/movie", query=q, include_adult="false")
    if data is None:
        return jsonify({"error": "TMDB search failed"}), 502

    watched_ids    = get_watched_movie_ids()
    watchlist_ids  = get_watchlist_movie_ids()

    # Map local tmdb_id → local id for status lookups
    local_map = {m["tmdb_id"]: m for m in get_all_movies()}

    results = []
    for r in data.get("results", [])[:12]:
        tid = r["id"]
        local = local_map.get(tid)
        results.append({
            "tmdb_id":     tid,
            "title":       r.get("title", ""),
            "year":        (r.get("release_date") or "")[:4],
            "description": r.get("overview", ""),
            "poster_url":  f"https://image.tmdb.org/t/p/w500{r['poster_path']}"
                           if r.get("poster_path") else "",
            "vote_average": round(r.get("vote_average", 0), 1),
            "in_watchlist": bool(local and local["id"] in watchlist_ids),
            "watched":      bool(local and local["id"] in watched_ids),
        })
    return jsonify(results)


# ── API: Enrich (store) ──────────────────────────────────────────────────────

@app.route("/api/enrich", methods=["POST"])
def api_enrich():
    tmdb_id = request.json.get("tmdb_id")
    if not tmdb_id:
        return jsonify({"error": "tmdb_id required"}), 400
    movie_id = _ensure_movie(tmdb_id)
    if not movie_id:
        return jsonify({"error": "Could not fetch movie from TMDB"}), 502
    return jsonify({"success": True, "movie": get_movie_by_id(movie_id)})


# ── API: Log ─────────────────────────────────────────────────────────────────

@app.route("/api/log", methods=["POST"])
def api_log():
    data     = request.json or {}
    tmdb_id  = data.get("tmdb_id")
    rating   = data.get("user_rating", 3)
    mood     = data.get("mood_tag", "")
    notes    = data.get("notes", "")
    date     = data.get("watched_date") or None

    if not tmdb_id:
        return jsonify({"error": "tmdb_id required"}), 400

    movie_id = _ensure_movie(tmdb_id)
    if not movie_id:
        return jsonify({"error": "Could not fetch movie details"}), 502

    log_watch(movie_id, rating, mood, notes, date)
    return jsonify({"success": True, "movie_id": movie_id})


@app.route("/api/history/<int:entry_id>", methods=["DELETE"])
def api_delete_history(entry_id):
    delete_history_entry(entry_id)
    return jsonify({"success": True})


# ── API: Watchlist ───────────────────────────────────────────────────────────

@app.route("/api/watchlist", methods=["GET"])
def api_get_watchlist():
    return jsonify(get_watchlist())


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    data     = request.json or {}
    tmdb_id  = data.get("tmdb_id")
    priority = data.get("priority", 3)
    if not tmdb_id:
        return jsonify({"error": "tmdb_id required"}), 400

    movie_id = _ensure_movie(tmdb_id)
    if not movie_id:
        return jsonify({"error": "Could not fetch movie details"}), 502

    add_to_watchlist(movie_id, priority)
    return jsonify({"success": True})


@app.route("/api/watchlist/<int:wl_id>", methods=["DELETE"])
def api_watchlist_remove(wl_id):
    remove_from_watchlist(wl_id)
    return jsonify({"success": True})


@app.route("/api/watchlist/<int:wl_id>/priority", methods=["PUT"])
def api_watchlist_priority(wl_id):
    priority = (request.json or {}).get("priority", 3)
    update_watchlist_priority(wl_id, priority)
    return jsonify({"success": True})


# ── API: Recommendations ─────────────────────────────────────────────────────

@app.route("/api/recommendations")
def api_recommendations():
    mood  = request.args.get("mood", "")
    genre = request.args.get("genre", "")
    limit = request.args.get("limit", 24, type=int)

    prefs       = get_preferences()
    all_movies  = get_all_movies()
    watched_ids = get_watched_movie_ids()
    history     = get_watch_history(200)

    scored = score_movies(all_movies, watched_ids, history, prefs,
                          mood_filter=mood, genre_filter=genre)
    return jsonify(scored[:limit])


# ── API: History ─────────────────────────────────────────────────────────────

@app.route("/api/history")
def api_history():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(get_watch_history(limit))


# ── API: Preferences ─────────────────────────────────────────────────────────

@app.route("/api/preferences", methods=["GET"])
def api_get_prefs():
    return jsonify(get_preferences())


@app.route("/api/preferences", methods=["POST"])
def api_update_prefs():
    data = request.json or {}
    update_preferences(
        data.get("favorite_genres", []),
        data.get("excluded_genres", []),
        data.get("favorite_moods", []),
        data.get("preferred_decades", []),
        data.get("streaming_services", []),
    )
    return jsonify({"success": True})


# ── API: Stats ───────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


if __name__ == "__main__":
    print("🎬  CineMatch is running at http://localhost:5000")
    app.run(debug=True, port=5000)

import json
from collections import defaultdict

MOOD_GENRE_MAP = {
    "cozy":         ["Drama", "Romance", "Comedy", "Family", "Animation"],
    "thrilling":    ["Thriller", "Action", "Horror", "Mystery", "Crime"],
    "mind-bending": ["Science Fiction", "Mystery", "Thriller", "Fantasy"],
    "heartwarming": ["Drama", "Romance", "Comedy", "Family", "Animation"],
    "dark":         ["Horror", "Thriller", "Crime", "Drama", "Neo-noir"],
    "adventurous":  ["Action", "Adventure", "Science Fiction", "Fantasy"],
    "funny":        ["Comedy", "Animation", "Family"],
    "emotional":    ["Drama", "Romance", "History", "Biography", "Music"],
    "scary":        ["Horror", "Thriller", "Mystery"],
    "action-packed":["Action", "Adventure", "Thriller", "Science Fiction"],
    "thoughtful":   ["Drama", "Documentary", "History", "Biography", "Philosophy"],
    "romantic":     ["Romance", "Comedy", "Drama"],
    "nostalgic":    ["Animation", "Family", "Comedy", "Drama"],
    "epic":         ["Action", "Adventure", "Fantasy", "History", "Science Fiction"],
}

ALL_MOODS = sorted(MOOD_GENRE_MAP.keys())

ALL_GENRES = [
    "Action", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Fantasy", "History", "Horror", "Music",
    "Mystery", "Romance", "Science Fiction", "Thriller", "War", "Western", "Family",
]

ALL_DECADES = ["1950s", "1960s", "1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]


def score_movies(all_movies, watched_ids, history, prefs,
                 mood_filter="", genre_filter=""):
    """
    Score unwatched movies using weighted criteria and return sorted list
    with reason tags attached to each result.
    """
    fav_genres  = [g.lower() for g in prefs.get("favorite_genres", [])]
    excl_genres = [g.lower() for g in prefs.get("excluded_genres", [])]
    fav_moods   = [m.lower() for m in prefs.get("favorite_moods", [])]
    user_svcs   = [s.lower() for s in prefs.get("streaming_services", [])]
    pref_decades = prefs.get("preferred_decades", [])

    # Build per-genre average rating from watch history
    genre_ratings = defaultdict(list)
    for h in history:
        if h.get("user_rating") and h.get("genre"):
            for g in h["genre"].split(","):
                genre_ratings[g.strip().lower()].append(h["user_rating"])
    genre_avg = {g: sum(v) / len(v) for g, v in genre_ratings.items()}

    # Collect mood-genres from active mood filter + user's favourite moods
    mood_genres = set()
    if mood_filter:
        for g in MOOD_GENRE_MAP.get(mood_filter.lower(), []):
            mood_genres.add(g.lower())
    for mood in fav_moods:
        for g in MOOD_GENRE_MAP.get(mood, []):
            mood_genres.add(g.lower())

    results = []
    for movie in all_movies:
        if movie["id"] in watched_ids:
            continue

        movie_genres = [
            g.strip().lower()
            for g in (movie.get("genre") or "").split(",")
            if g.strip()
        ]

        # Hard exclude
        if any(g in excl_genres for g in movie_genres):
            continue

        # Genre hard filter (when user explicitly picks one)
        if genre_filter and genre_filter.lower() not in movie_genres:
            continue

        score = 0.0
        reasons = []

        # ── Genre preference match  (30 pts per matching genre, max 60) ──
        matched = [g for g in movie_genres if g in fav_genres]
        if matched:
            pts = min(len(matched) * 30, 60)
            score += pts
            reasons.append(f"Matches your {', '.join(g.title() for g in matched)} preference")

        # ── Mood match  (20 pts per matching genre, max 40) ──
        mood_hits = [g for g in movie_genres if g in mood_genres]
        if mood_hits:
            pts = min(len(mood_hits) * 20, 40)
            score += pts
            if mood_filter:
                reasons.append(f"Perfect for a {mood_filter.title()} night")
            elif fav_moods:
                reasons.append("Fits your favourite moods")

        # ── Rotten Tomatoes score  (up to 40 pts) ──
        rt = movie.get("rotten_tomatoes_score")
        if rt is not None:
            score += (rt / 100) * 40
            if rt >= 90:
                reasons.append(f"🍅 {rt}% on Rotten Tomatoes — Certified Fresh")
            elif rt >= 75:
                reasons.append(f"🍅 {rt}% on Rotten Tomatoes")
            elif rt >= 60:
                reasons.append(f"{rt}% on Rotten Tomatoes")

        # ── Streaming availability  (20 pts) ──
        streaming = movie.get("streaming_services", [])
        if isinstance(streaming, str):
            try:
                streaming = json.loads(streaming)
            except Exception:
                streaming = []
        matched_svcs = [s for s in streaming if s.lower() in user_svcs]
        if matched_svcs:
            score += 20
            reasons.append(f"Available on {', '.join(matched_svcs)}")

        # ── Historical rating pattern bonus  (up to 15 pts) ──
        pattern_bonus = sum(
            5 for g in movie_genres if genre_avg.get(g, 0) >= 4.0
        )
        if pattern_bonus:
            score += min(pattern_bonus, 15)
            reasons.append("Matches your highly-rated genres")

        # ── Preferred decade bonus  (10 pts) ──
        year = movie.get("year") or 0
        if year and pref_decades:
            decade = f"{(year // 10) * 10}s"
            if decade in pref_decades:
                score += 10
                reasons.append(f"From your preferred era ({decade})")

        # Fallback reason so the card is never completely blank
        if not reasons:
            if rt and rt > 0:
                reasons.append(f"{rt}% on Rotten Tomatoes")
            else:
                reasons.append("In your collection")

        results.append({
            **movie,
            "score": round(score, 1),
            "reasons": reasons,
            "streaming_services": streaming,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

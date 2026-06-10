#!/usr/bin/env python3
"""
CineMatch CLI — terminal client for the CineMatch Flask server.
The server must be running: python app.py
"""
import argparse
import sys
import requests

BASE_URL = "http://localhost:5000"

RED   = "\033[91m"
GREEN = "\033[92m"
GOLD  = "\033[93m"
BLUE  = "\033[94m"
GRAY  = "\033[90m"
BOLD  = "\033[1m"
RESET = "\033[0m"


def _get(path, **params):
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to CineMatch server. Run: python app.py{RESET}")
        sys.exit(1)


def _post(path, payload):
    try:
        r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        print(f"{RED}✗ Cannot connect to CineMatch server. Run: python app.py{RESET}")
        sys.exit(1)


def stars(n):
    return GOLD + "★" * (n or 0) + GRAY + "☆" * (5 - (n or 0)) + RESET


def rt_badge(score):
    if score is None:
        return f"{GRAY}RT: N/A{RESET}"
    color = GREEN if score >= 75 else (GOLD if score >= 60 else RED)
    return f"{color}🍅 {score}%{RESET}"


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_search(args):
    results = _get("/api/search", q=args.query)
    if isinstance(results, dict) and results.get("error"):
        print(f"{RED}Error: {results['error']}{RESET}")
        return
    if not results:
        print(f"{GRAY}No results found for "{args.query}".{RESET}")
        return

    print(f"\n{BOLD}Search results for "{args.query}"{RESET}\n")
    for i, m in enumerate(results, 1):
        status = ""
        if m.get("watched"):
            status = f" {GREEN}[watched]{RESET}"
        elif m.get("in_watchlist"):
            status = f" {BLUE}[in watchlist]{RESET}"
        year = f" ({m['year']})" if m.get("year") else ""
        desc = (m.get("description") or "")[:80]
        if len(m.get("description", "")) > 80:
            desc += "…"
        print(f"  {BOLD}{i}.{RESET} {m['title']}{year}{status}")
        if desc:
            print(f"     {GRAY}{desc}{RESET}")
    print()


def cmd_log(args):
    results = _get("/api/search", q=args.title)
    if isinstance(results, dict) and results.get("error"):
        print(f"{RED}Error: {results['error']}{RESET}")
        return
    if not results:
        print(f"{RED}Movie "{args.title}" not found.{RESET}")
        return

    movie = results[0]
    year  = f" ({movie['year']})" if movie.get("year") else ""
    print(f"Found: {BOLD}{movie['title']}{year}{RESET}")

    resp = _post("/api/log", {
        "tmdb_id":    movie["tmdb_id"],
        "user_rating": args.rating,
        "mood_tag":   args.mood,
        "notes":      args.notes,
    })
    if resp.get("success"):
        print(f"{GREEN}✓ Logged "{movie['title']}" — {stars(args.rating)} mood: {args.mood or '—'}{RESET}")
    else:
        print(f"{RED}Error: {resp}{RESET}")


def cmd_history(args):
    history = _get("/api/history", limit=args.limit)
    if not history:
        print(f"{GRAY}No watch history yet. Use: python cli.py log \"Movie Name\" --rating 4{RESET}")
        return

    print(f"\n{BOLD}Watch History{RESET}\n")
    print(f"{'Title':<36} {'Year':<6} {'Rating':<12} {'Mood':<16} {'Date'}")
    print("─" * 85)
    for h in history:
        title = (h["title"] or "")[:34]
        year  = str(h.get("year") or "")
        rating = stars(h.get("user_rating"))
        mood  = (h.get("mood_tag") or "—")[:14]
        date  = h.get("watched_date", "")
        print(f"{title:<36} {year:<6} {rating:<12} {mood:<16} {date}")
    print()


def cmd_watchlist(args):
    wl = _get("/api/watchlist")
    if not wl:
        print(f"{GRAY}Your watchlist is empty. Use: python cli.py add \"Movie Name\"{RESET}")
        return

    print(f"\n{BOLD}Watchlist ({len(wl)} movies){RESET}\n")
    for item in wl:
        year    = f" ({item['year']})" if item.get("year") else ""
        pri_str = "▮" * item.get("priority", 3) + "▯" * (5 - item.get("priority", 3))
        rt      = rt_badge(item.get("rotten_tomatoes_score"))
        svcs    = ", ".join(item.get("streaming_services") or []) or "—"
        print(f"  {BOLD}{item['title']}{year}{RESET}  {GRAY}priority:{RESET} {GOLD}{pri_str}{RESET}  {rt}  {GRAY}streaming:{RESET} {svcs}")
    print()


def cmd_add(args):
    results = _get("/api/search", q=args.title)
    if isinstance(results, dict) and results.get("error"):
        print(f"{RED}Error: {results['error']}{RESET}")
        return
    if not results:
        print(f"{RED}Movie "{args.title}" not found.{RESET}")
        return

    movie = results[0]
    year  = f" ({movie['year']})" if movie.get("year") else ""
    resp  = _post("/api/watchlist/add", {"tmdb_id": movie["tmdb_id"], "priority": args.priority})
    if resp.get("success"):
        print(f"{GREEN}✓ Added "{movie['title']}{year}" to watchlist (priority {args.priority}/5){RESET}")
    else:
        print(f"{RED}Error: {resp}{RESET}")


def cmd_recommend(args):
    params = {}
    if args.mood:
        params["mood"] = args.mood
    if args.genre:
        params["genre"] = args.genre

    results = _get("/api/recommendations", **params)
    if not results:
        print(
            f"{GRAY}No recommendations yet. Search for movies and add them to your watchlist first.\n"
            f"Then set genre/mood preferences on the web UI (http://localhost:5000/profile).{RESET}"
        )
        return

    filters = []
    if args.mood:
        filters.append(f"mood={args.mood}")
    if args.genre:
        filters.append(f"genre={args.genre}")
    label = f" ({', '.join(filters)})" if filters else ""

    print(f"\n{BOLD}Recommendations{label}{RESET}\n")
    for i, m in enumerate(results[:args.limit], 1):
        year    = f" ({m['year']})" if m.get("year") else ""
        rt      = rt_badge(m.get("rotten_tomatoes_score"))
        score   = f"{BLUE}score: {m['score']:.0f}{RESET}"
        reasons = f"{GRAY}" + " • ".join(m.get("reasons", [])) + RESET
        svcs    = ", ".join(m.get("streaming_services") or [])
        svc_str = f"  {GRAY}streaming: {svcs}{RESET}" if svcs else ""
        print(f"  {BOLD}{i}. {m['title']}{year}{RESET}  {rt}  {score}")
        print(f"     {reasons}")
        if svc_str:
            print(f"    {svc_str}")
        print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🎬  CineMatch CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python cli.py search "Inception"
  python cli.py log "Inception" --rating 5 --mood "mind-bending"
  python cli.py add "The Dark Knight" --priority 5
  python cli.py history
  python cli.py watchlist
  python cli.py recommend --mood cozy --genre Drama
  python cli.py recommend --limit 5
        """,
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    # search
    p = sub.add_parser("search", help="Search TMDB for movies")
    p.add_argument("query", help="Movie title")

    # log
    p = sub.add_parser("log", help="Log a watched movie")
    p.add_argument("title", help="Movie title")
    p.add_argument("--rating", type=int, default=3, choices=range(1, 6), metavar="1-5")
    p.add_argument("--mood", default="", help="Mood tag (e.g. mind-bending, cozy)")
    p.add_argument("--notes", default="", help="Personal notes")

    # add (to watchlist)
    p = sub.add_parser("add", help="Add a movie to your watchlist")
    p.add_argument("title", help="Movie title")
    p.add_argument("--priority", type=int, default=3, choices=range(1, 6), metavar="1-5")

    # history
    p = sub.add_parser("history", help="View watch history")
    p.add_argument("--limit", type=int, default=20)

    # watchlist
    sub.add_parser("watchlist", help="View your watchlist")

    # recommend
    p = sub.add_parser("recommend", help="Get personalised recommendations")
    p.add_argument("--mood",  default="", help="Filter by mood")
    p.add_argument("--genre", default="", help="Filter by genre")
    p.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()

    dispatch = {
        "search":    cmd_search,
        "log":       cmd_log,
        "add":       cmd_add,
        "history":   cmd_history,
        "watchlist": cmd_watchlist,
        "recommend": cmd_recommend,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

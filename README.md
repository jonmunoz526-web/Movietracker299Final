# CineMatch 🎬

CineMatch is a personal movie tracking and recommendation web app. Search for any movie, log what you've watched, rate it, and tag it with a mood. CineMatch then recommends what to watch next based on your taste, with Rotten Tomatoes scores and streaming availability so you know exactly where to watch it.

Built with Python, Flask, and SQLite. Movie data is pulled from the TMDB and OMDb APIs.

## Features
- Search any movie and log it with a rating and mood tag
- Get personalized movie recommendations filtered by mood and genre
- See Rotten Tomatoes scores and which streaming services a movie is on
- Save movies to a watchlist
- Full movie detail pages with cast, description, and watch history
- CLI client for quick terminal access
- Dark cinema-themed UI

## Setup

### 1. Get your free API keys
- **TMDB** (movie data, posters, streaming): https://www.themoviedb.org/settings/api
- **OMDb** (Rotten Tomatoes scores): https://www.omdbapi.com/apikey.aspx

Both are free and just require creating an account.

### 2. Clone the repo
git clone https://github.com/jonmunoz526-web/Movietracker299Final.git
cd Movietracker299Final

### 3. Install dependencies
pip install -r requirements.txt

### 4. Set up your API keys
cp .env.example .env

Open .env and replace the placeholder values with your real keys:
TMDB_API_KEY=your_key_here
OMDB_API_KEY=your_key_here

### 5. Run the app
python app.py

Then open http://localhost:5000 in your browser.

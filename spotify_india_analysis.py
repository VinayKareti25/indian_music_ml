# spotify_india_analysis.py
# Python 3.8+
import os
import time
import math
from typing import List, Dict

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import pandas as pd
import plotly.express as px

# ---------- CONFIG ----------
# Use environment variables (recommended)
CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback")

# Choose mode:
# - client_credentials: read-only public data (artists, public playlists, track basic metadata)
# - oauth_user: for reading a user's private playlists (requires user login & scopes)
USE_OAUTH_FOR_PLAYLISTS = False

# ---------- AUTH ----------
def get_spotify_client(use_oauth: bool = USE_OAUTH_FOR_PLAYLISTS):
    if use_oauth:
        # For user-level data (private playlists). Ensure REDIRECT_URI matches dashboard.
        scope = "playlist-read-private playlist-read-collaborative user-library-read"
        auth_manager = SpotifyOAuth(scope=scope,
                                   redirect_uri=REDIRECT_URI,
                                   client_id=CLIENT_ID,
                                   client_secret=CLIENT_SECRET,
                                   show_dialog=True)
        sp = spotipy.Spotify(auth_manager=auth_manager)
    else:
        # App-level client credentials (no user login). Good for artist search, top tracks, public playlists.
        client_credentials_manager = SpotifyClientCredentials()
        sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    return sp

sp = get_spotify_client()

# ---------- HELPERS ----------
def chunked(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def safe_audio_features(sp: spotipy.Spotify, track_ids: List[str]) -> List[Dict]:
    """
    Request audio_features in batches, handle errors due to API restrictions.
    Returns list (same order as track_ids) or None on failure.
    """
    all_feats = []
    for batch in chunked(track_ids, 100):  # API accepts up to 100 ids
        try:
            feats = sp.audio_features(batch)
            all_feats.extend(feats)
        except spotipy.SpotifyException as e:
            print("audio_features() failed:", e)
            print("This could be due to Spotify restricting the audio-features endpoint for new apps.")
            return None
        time.sleep(0.1)
    return all_feats

# ---------- TASKS ----------
def search_artist(sp, artist_name: str):
    res = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
    items = res.get("artists", {}).get("items", [])
    if not items:
        return None
    return items[0]  # full artist object

def artist_top_tracks_in_market(sp, artist_id: str, market: str = "IN"):
    top = sp.artist_top_tracks(artist_id, market=market)
    return top.get("tracks", [])

def get_playlist_tracks(sp, playlist_id: str):
    results = sp.playlist_items(playlist_id, fields="items(track(id,name,artists,album,popularity)),next", additional_types=['track'])
    tracks = results['items']
    while results.get('next'):
        results = sp.next(results)
        tracks.extend(results['items'])
    return tracks

# ---------- EXAMPLE: Indian artist -> top tracks -> features -> DataFrame ----------
def analyze_artist(artist_name: str, market='IN'):
    artist = search_artist(sp, artist_name)
    if not artist:
        print("Artist not found:", artist_name)
        return None
    artist_id = artist['id']
    print(f"Found artist: {artist['name']} (id={artist_id})")

    top_tracks = artist_top_tracks_in_market(sp, artist_id, market=market)
    if not top_tracks:
        print("No top tracks returned.")
        return None

    # Basic metadata dataframe
    tracks_meta = []
    track_ids = []
    for t in top_tracks:
        artists = ", ".join([a['name'] for a in t['artists']])
        tracks_meta.append({
            'track_name': t['name'],
            'track_id': t['id'],
            'artists': artists,
            'album': t['album']['name'],
            'popularity': t.get('popularity'),
            'duration_ms': t.get('duration_ms'),
        })
        track_ids.append(t['id'])

    df_meta = pd.DataFrame(tracks_meta)

    # Try to fetch audio features (may fail if API endpoint is restricted)
    feats = safe_audio_features(sp, track_ids)
    if feats is None:
        print("Audio features unavailable. Proceeding with metadata-only analysis.")
        return df_meta  # fallback

    df_feats = pd.DataFrame(feats)
    # merge on id
    df = df_meta.merge(df_feats, left_on='track_id', right_on='id', how='left')
    return df

# ---------- RUN AN EXAMPLE ----------
if __name__ == "__main__":
    # Example: Arijit Singh
    df = analyze_artist("Arijit Singh", market="IN")
    if df is None:
        raise SystemExit("No data returned.")
    print(df.head())

    # Simple visualization (if audio features exist)
    if 'danceability' in df.columns:
        fig = px.scatter(df, x='tempo', y='danceability',
                         size='popularity', hover_data=['track_name', 'artists'],
                         title="Tempo vs Danceability (India)")
        fig.show()
    else:
        print("No audio features available; try using a Kaggle audio-features dataset or request extended access from Spotify.")

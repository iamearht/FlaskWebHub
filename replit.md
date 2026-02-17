# Blackjack 1v1

## Overview
A 1v1 competitive Blackjack web application built with Flask. Players register, login, and compete in matches with persistent coin balances.

## Tech Stack
- **Backend**: Flask, Flask-SQLAlchemy
- **Database**: PostgreSQL (via DATABASE_URL)
- **Auth**: werkzeug.security password hashing, Flask sessions
- **Frontend**: Jinja2 templates, vanilla JavaScript, CSS

## Project Structure
- `app.py` - Flask app factory, configuration
- `models.py` - SQLAlchemy models (User, Match)
- `auth.py` - Authentication blueprint (register/login/logout)
- `game.py` - Game routes and API endpoints
- `engine.py` - Core blackjack game engine
- `templates/` - Jinja2 HTML templates
- `static/style.css` - Styling

## Game Rules
- 1v1 matches with coin stakes
- 2 turns per match (each player plays once as Player, once as Dealer)
- Multi-box betting (up to 3 boxes per round)
- Full blackjack: hit, stand, double, split, insurance
- 2 standard decks, cut card at position 65
- 100 chips per turn bankroll
- Winner takes both stakes
- 10-second decision timer (server-side enforced) with auto-fallback actions

## Recent Changes (Feb 2026)
- Simplified from 4 turns to 2 turns per match
- Added 10-second server-side decision timer with auto-fallbacks
- Match model: added decision_started_at, decision_type, is_waiting_decision fields
- Cleaner state machine with explicit phase transitions

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app` where app factory is `create_app()`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

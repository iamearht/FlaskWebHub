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
- Infinite re-splits allowed; double after split allowed
- Hit/double after splitting aces allowed (but split aces + ten = not blackjack, pays 1:1)
- 2 standard decks, cut card at position 65
- 100 chips per turn bankroll
- Winner takes both stakes
- 30-second decision timer (server-side enforced) with auto-fallback actions
- Bank player can see opponent's turn in real-time (spectating)
- Bank player can manually hit on dealer hands 17-20 (DEALER_TURN phase)
- If dealer hits and drops below 17, auto-draws back to 17+ then offers choice again
- Forfeit option available for active matches (opponent gets both stakes)

## Game Phases
- TURN_START → WAITING_BETS → INSURANCE (if dealer ace) → PLAYER_TURN → DEALER_TURN (if 17-20) → ROUND_RESULT → (next round or end turn)
- DEALER_TURN: bank player decides hit/stand on 17-20; auto-draw if hand drops below 17

## State Persistence
- game_state stored as JSON in Match model (MutableDict + flag_modified via _save_match helper)
- All game state mutations go through _save_match(match) to ensure SQLAlchemy detects nested changes

## Recent Changes (Feb 2026)
- Infinite splits, double after split, hit/double on split aces
- Split aces + ten is NOT blackjack (from_split_aces flag)
- DEALER_TURN phase: bank player can hit on 17-20
- Real-time spectating for bank player during opponent's turn
- Forfeit active matches from lobby
- Fixed timeout button disable bug (buttons re-enabled on each render)
- 30-second server-side decision timer with auto-fallbacks

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app` where app factory is `create_app()`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

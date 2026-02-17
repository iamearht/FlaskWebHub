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

## RNG Security
- Uses Python's `secrets` module (CSPRNG) for all deck shuffling
- Fisher-Yates shuffle with `secrets.randbelow()` for cryptographically secure randomness
- No use of `random` module anywhere in game logic

## Game Rules
- 1v1 matches with coin stakes
- **Card Draw**: Match starts with each player drawing a card; higher card chooses role. Tied? Draw again.
- **4 turns** in a **1-2-2-1 structure**: First player goes Player, Bank, Bank, Player
- Multi-box betting (up to 3 boxes per round)
- Full blackjack: hit, stand, double, split, insurance
- Infinite re-splits allowed; double after split allowed
- Hit/double after splitting aces allowed (but split aces + ten = not blackjack, pays 1:1)
- 2 standard decks, cut card at position 65
- **Chip carryover**: 100 chips for first Player turn; second Player turn gets leftover + 100 bonus
- Winner = highest final chip count after all 4 turns
- 30-second decision timer (server-side enforced) with auto-fallback actions
- Bank player can see opponent's turn in real-time (spectating)
- Bank player can manually hit on dealer hands 17-20 (DEALER_TURN phase)
- If dealer hits and drops below 17, auto-draws back to 17+ then offers choice again
- Forfeit option available for active matches (opponent gets both stakes)

## Game Phases
- CARD_DRAW → CHOICE → TURN_START → WAITING_BETS → INSURANCE (if dealer ace) → PLAYER_TURN → DEALER_TURN (if 17-20) → ROUND_RESULT → (next round or end turn)
- CARD_DRAW: both players draw cards, higher rank wins (poker ordering: 2-A)
- CHOICE: draw winner picks Player or Bank first
- DEALER_TURN: bank player decides hit/stand on 17-20; auto-draw if hand drops below 17

## State Persistence
- game_state stored as JSON in Match model (MutableDict + flag_modified via _save_match helper)
- All game state mutations go through _save_match(match) to ensure SQLAlchemy detects nested changes

## Results Tracking
- results: {player1_turn1, player1_turn2, player2_turn1, player2_turn2}
- Final score = player's turn2 chips (which started with turn1 leftover + 100)
- Winner determined by comparing final chip counts

## Recent Changes (Feb 2026)
- Upgraded RNG to use `secrets` module (CSPRNG) instead of `random`
- Card draw phase at match start to determine role choice
- 4-turn 1-2-2-1 structure with chip carryover
- Infinite splits, double after split, hit/double on split aces
- Split aces + ten is NOT blackjack (from_split_aces flag)
- DEALER_TURN phase: bank player can hit on 17-20
- Real-time spectating for bank player during opponent's turn
- Forfeit active matches from lobby
- 30-second server-side decision timer with auto-fallbacks

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app` where app factory is `create_app()`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

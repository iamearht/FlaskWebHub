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
- **Card Draw**: Auto-drawn when 2nd player joins with 3-sec suspense reveal; higher card chooses role. Ties auto-redraw.
- **4 turns** in a **1-2-2-1 structure**: First player goes Player, Bank, Bank, Player
- Multi-box betting (up to 3 boxes per round)
- Full blackjack: hit, stand, double, split, insurance
- Infinite re-splits allowed; double after split allowed
- Hit/double after splitting aces allowed (but split aces + ten = not blackjack, pays 1:1)
- 2 standard decks, cut card at position 65
- **Chip carryover**: 100 chips for first Player turn; second Player turn gets leftover + 100 bonus
- Winner = highest final chip count after all 4 turns
- 30-second decision timer (server-side enforced) with auto-fallback actions
- 5-second round result display before auto-advancing
- Bank player can see opponent's turn in real-time (spectating) with swapped perspective (dealer cards at bottom)
- Bank player can hit or stand on ANY dealer hand value 1-20 (full manual control)
- No auto-draw to 17; dealer makes all decisions manually
- Forfeit option available for active matches (opponent gets both stakes)

## Insurance
- Offered when dealer upcard is an Ace
- Per-hand individual insurance decisions (checkbox for each hand)
- Insurance costs half of each hand's bet
- Pays 2:1 if dealer has blackjack (player gets back insurance amount * 3)
- If dealer doesn't have blackjack, insurance bet is lost

## Game Phases
- CARD_DRAW (auto) → CHOICE → WAITING_BETS → INSURANCE (if dealer ace) → PLAYER_TURN → DEALER_TURN (any value 1-20) → ROUND_RESULT (auto-advance) → (next round or end turn)
- CARD_DRAW: auto-performed at match init; cards shown with 3-sec reveal delay
- CHOICE: draw winner picks Player or Bank first
- TURN_START skipped: turns auto-enter after choice/turn transitions
- DEALER_TURN: bank player decides hit/stand on any value 1-20; no auto-draw
- ROUND_RESULT: auto-advances after 3 seconds client-side; 5-second server timeout

## Perspective
- When you're the Player: dealer cards at top, your boxes at bottom
- When you're the Bank: opponent's boxes at top, your dealer cards at bottom (facing you)

## State Persistence
- game_state stored as JSON in Match model (MutableDict + flag_modified via _save_match helper)
- All game state mutations go through _save_match(match) to ensure SQLAlchemy detects nested changes

## Results Tracking
- results: {player1_turn1, player1_turn2, player2_turn1, player2_turn2}
- Final score = player's turn2 chips (which started with turn1 leftover + 100)
- Winner determined by comparing final chip counts

## Recent Changes (Feb 2026)
- Auto card draw at match start with 3-sec suspense reveal (no Draw Card button)
- Auto turn start (no Start Turn button; turns enter immediately after choice/transitions)
- Per-hand individual insurance decisions
- Round result auto-advances after 3 seconds (5-second server timeout)
- Polling interval reduced to 1.5 seconds for faster updates
- Polling always runs in background for real-time updates
- Bank player can hit/stand on any value 1-20 (full manual control)
- Swapped perspective for bank player
- CSPRNG deck shuffling with secrets module

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app` where app factory is `create_app()`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

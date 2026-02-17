# Blackjack Platform

## Overview
A multiplayer competitive Blackjack web platform built with Flask. Players register, manage wallets, compete in 1v1 matches and tournaments, earn VIP progress, and participate in affiliate referral programs.

## Tech Stack
- **Backend**: Flask, Flask-SQLAlchemy
- **Database**: PostgreSQL (via DATABASE_URL)
- **Auth**: werkzeug.security password hashing, Flask sessions
- **Frontend**: Jinja2 templates, vanilla JavaScript, CSS

## Project Structure
- `app.py` - Flask app factory, configuration, blueprint registration
- `models.py` - SQLAlchemy models (User, Match, WalletTransaction, VIPProgress, AffiliateCommission, Tournament, TournamentEntry, TournamentMatch)
- `auth.py` - Authentication blueprint (register/login/logout)
- `game.py` - Game routes, API endpoints, match lifecycle, spectating
- `engine.py` - Core blackjack game engine (untouched)
- `wallet.py` - Wallet blueprint (deposit/withdraw, transaction history)
- `account.py` - Account blueprint (profile, stats, VIP, game/transaction history)
- `tournament.py` - Tournament blueprint (lobby, join, bracket, advancement)
- `affiliate.py` - Affiliate blueprint (referral tracking, commission dashboard)
- `templates/` - Jinja2 HTML templates
- `static/style.css` - Comprehensive styling for all pages

## Blueprints
- `auth_bp` - /login, /register, /logout
- `game_bp` - /lobby, /match/<id>, /api/match/*, /spectate/<id>
- `wallet_bp` - /wallet, /wallet/deposit, /wallet/withdraw, /wallet/history
- `account_bp` - /account, /account/game-history, /account/transactions
- `tournament_bp` - /tournaments, /tournament/<id>, /tournaments/join/<id>
- `affiliate_bp` - /affiliate

## Database Models
- **User**: username, email, password_hash, coins, affiliate_code, referred_by, vip_tier, created_at
- **Match**: player1_id, player2_id, stake, status, winner_id, game_state (JSON), is_spectatable, tournament_match_id
- **WalletTransaction**: user_id, type (deposit/withdrawal/match_stake/match_win/tournament_entry/tournament_prize/affiliate_commission), amount, status, crypto_address, crypto_network, created_at
- **VIPProgress**: user_id, total_wagered, tier, updated_at
- **AffiliateCommission**: referrer_id, referred_id, match_id, amount, created_at
- **Tournament**: stake, status (waiting/active/completed), prize_pool, bracket (JSON), standings (JSON), created_at, started_at, completed_at
- **TournamentEntry**: tournament_id, user_id, joined_at
- **TournamentMatch**: tournament_id, match_id, round_name

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
- Bank player can see opponent's turn in real-time (spectating) with swapped perspective
- Bank player can hit or stand on ANY dealer hand value 1-20 (full manual control)
- Forfeit option available for active matches

## Tournament System
- 5 stake levels: $5, $10, $25, $50, $100
- 8 players required to start (single elimination)
- Bracket: Quarterfinals → Semifinals → Final + 3rd place match
- Prize distribution: 1st (50%), 2nd (25%), 3rd (15%), 4th (10%)
- Auto-start when 8 players join
- Auto bracket progression when matches complete
- Tournament matches use existing match engine

## VIP System
- 5 tiers: Bronze (0), Silver (500), Gold (2000), Platinum (5000), Diamond (15000)
- Tracked via total wagered amount in VIPProgress model
- Progress bar displayed in lobby
- Tier badge shown on account page

## Affiliate System
- Each user gets unique affiliate code on registration
- 5% commission on match stakes when referred user plays
- Referral link: /register?ref=CODE
- Dashboard shows referral count, total/pending commissions

## Spectating
- Non-participants can watch live games
- Spectator-safe client state (spectator=True flag in get_client_state)
- No action buttons shown to spectators
- Dealer hole card hidden from spectators until revealed

## Wallet System
- Deposit/withdraw with crypto address and network tracking
- Transaction types: deposit, withdrawal, match_stake, match_win, tournament_entry, tournament_prize, affiliate_commission
- User.coins is authoritative balance; WalletTransaction is audit trail
- Status tracking: pending, approved, rejected, completed

## Game Phases
- CARD_DRAW (auto) → CHOICE → WAITING_BETS → INSURANCE (if dealer ace) → PLAYER_TURN → DEALER_TURN → ROUND_RESULT (auto-advance) → (next round or end turn)

## State Persistence
- game_state stored as JSON in Match model (MutableDict + flag_modified via _save_match helper)
- All game state mutations go through _save_match(match)

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

## Recent Changes (Feb 2026)
- Expanded into full multiplayer platform
- Added wallet system with crypto deposit/withdraw
- Added tournament system (5 stakes, 8-player single elimination)
- Added VIP progress system (5 tiers)
- Added affiliate/referral system with 5% commission
- Added live game spectating with spectator-safe state
- Added account page with profile, stats, game/transaction history
- Updated registration with email and referral code support
- Exception handling: tournament advancement raises on failure, affiliate/VIP errors logged
- Comprehensive CSS for all new platform components

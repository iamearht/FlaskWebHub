# Blackjack Platform

## Overview
A multiplayer competitive Blackjack web platform built with Flask. Players register, manage wallets, compete in 1v1 matches and tournaments, earn VIP progress, participate in affiliate referral programs, and earn rakeback rewards.

## Tech Stack
- **Backend**: Flask, Flask-SQLAlchemy
- **Database**: PostgreSQL (via DATABASE_URL)
- **Auth**: werkzeug.security password hashing, Flask sessions
- **Frontend**: Jinja2 templates, vanilla JavaScript, CSS

## Project Structure
- `app.py` - Flask app factory, configuration, blueprint registration
- `models.py` - SQLAlchemy models (User, Match, WalletTransaction, VIPProgress, AffiliateCommission, Tournament, TournamentEntry, TournamentMatch, RakeTransaction, AdminConfig, RakebackProgress, JackpotPool, JackpotEntry)
- `auth.py` - Authentication blueprint (register/login/logout)
- `game.py` - Game routes, API endpoints, match lifecycle, spectating, rake deduction, live watch page
- `engine.py` - Core blackjack game engine (4 game modes, joker support, auto/manual dealer)
- `wallet.py` - Wallet blueprint (deposit/withdraw, transaction history)
- `account.py` - Account blueprint (profile, stats, VIP, game/transaction history)
- `tournament.py` - Tournament blueprint (lobby, join/unregister, bracket, advancement)
- `affiliate.py` - Affiliate blueprint (referral tracking, commission dashboard)
- `admin.py` - Admin blueprint (rake config, coin management, rakeback, payouts, stats, jackpot config)
- `jackpot.py` - Jackpot blueprint (dual leaderboards, jackpot pools, API, countdown)
- `migrate.py` - Database migration script
- `templates/` - Jinja2 HTML templates
- `templates/admin/` - Admin panel templates
- `static/style.css` - Comprehensive styling for all pages

## Blueprints
- `auth_bp` - /login, /register, /logout
- `game_bp` - /lobby, /watch, /match/<id>, /api/match/*, /spectate/<id>
- `wallet_bp` - /wallet, /wallet/deposit, /wallet/withdraw, /wallet/history
- `account_bp` - /account, /account/game-history, /account/transactions
- `tournament_bp` - /tournaments, /tournament/<id>, /tournament/join/<stake>/<size>, /tournament/unregister/<id>
- `affiliate_bp` - /affiliate
- `admin_bp` - /admin/ (dashboard, rake-stats, lobby-rake, tournament-rake, tournament-payouts, coins, rakeback, jackpot)

## Database Models
- **User**: username, email, password_hash, coins, affiliate_code, referred_by, is_admin, created_at
- **Match**: player1_id, player2_id, stake, status, winner_id, game_state (JSON), is_spectatable, tournament_match_id, rake_amount
- **WalletTransaction**: user_id, type, amount, status, crypto_address, crypto_network, created_at
- **VIPProgress**: user_id, total_wagered, tier, updated_at
- **AffiliateCommission**: referrer_id, referred_id, match_id, amount, created_at
- **Tournament**: stake_amount, max_players, status, prize_pool, rake_amount, bracket, created_at
- **TournamentEntry**: tournament_id, user_id, seed, placement
- **TournamentMatch**: tournament_id, round, bracket_position, player1_id, player2_id, match_id, winner_id
- **RakeTransaction**: source_type (match/tournament), source_id, amount, stake_amount, rake_percent
- **AdminConfig**: key/value JSON store for all admin settings
- **RakebackProgress**: user_id, total_rake_paid, tier, period_start
- **JackpotPool**: stake_tier, pool_type (standard/joker), pool_amount, status, period_start
- **JackpotEntry**: jackpot_id, user_id, match_id, score, finishing_chips, match_stake

## Currency System
- $1 = 100 coins
- Tournament stakes: 500/1000/2500/5000/10000 coins ($5/$10/$25/$50/$100)

## Rake System
- **Lobby Matches**: Configurable by stake range (default: <250 coins = 1%, 250-1000 = 2%, 1000-5000 = 3%, 5000+ = 5%)
- **Tournaments**: Configurable per stake x player count (default: 5%)
- Rake deducted from total pot (lobby) or total entries (tournament)
- All rake tracked via RakeTransaction for reporting

## Rakeback System
- 4 tiers: Bronze (0%), Silver (5%), Gold (10%), Platinum (15%)
- Based on total rake paid during period
- Configurable tier thresholds and percentages from admin
- Periodic reset (default: 60 days / 2 months), configurable from admin
- Tier consistency ensured via ensure_consistent() method before display

## Tournament System
- 5 stake levels: $5, $10, $25, $50, $100 (500-10000 coins)
- 5 player sizes: 8, 16, 32, 64, 128
- Single elimination with dynamic bracket generation
- Unregister allowed while tournament is in waiting status
- Auto-start when required players join
- Configurable payout distribution per player count from admin
- Rake deducted from total entries, remainder becomes prize pool

## Admin Panel
- Secured with is_admin flag + admin_required decorator
- Dashboard: platform stats, rake revenue summary
- Rake Stats: filter by period (24h/7d/30d/90d/all), match vs tournament breakdown
- Lobby Rake: configure tiered rake by stake ranges
- Tournament Rake: configure per stake x player count
- Tournament Payouts: configure payout % per placement per player count
- Coin Management: add/remove/set coins for any user
- Rakeback Config: configure tiers, thresholds, percentages, reset period
- Jackpot Config: set rake %, accumulation period, payouts, pay out/reset per pool type

## Game Modes
- **BJ Classic**: Automated dealer (hits below 17, stands on 17+), standard 104-card double deck
- **BJ Interactive**: Manual dealer decisions (player acting as dealer chooses hit/stand), standard deck
- **Classic Joker**: Automated dealer + 4 jokers added to deck (108-card shoe)
- **Interactive Joker**: Manual dealer + 4 jokers in deck
- Jokers: optimal value 1-11, Joker+10-value = blackjack, split jokers prevent blackjack
- Game mode selectable via tabs in lobby and tournaments, stored per match/tournament

## Jackpot System
- Two separate pools: Standard (Classic & Interactive) and Joker (Classic Joker & Interactive Joker)
- Lobby matches only - tournament matches do not contribute to jackpot
- Configurable % of lobby match rake goes to the appropriate jackpot pool (default 20%)
- Score = finishing chips x match stake (higher stakes + better play = higher score)
- Separate leaderboards per pool type showing top 20 players by best score
- Winners decided by leaderboard ranking
- Configurable payout structure (default: 1st 50%, 2nd 25%, 3rd 15%, 4th 10%)
- Configurable accumulation period (default: 7 days) with live countdown timer
- Admin can: set jackpot %, set period, set payouts, pay out per pool, reset per pool
- Jackpot pools displayed on lobby page and dedicated /jackpots page with tabs

## Watch Page
- /watch - Live spectating hub
- Top 5 biggest active lobby games sorted by stake
- Top 5 most important active tournament matches
- Tournament match priority: Finals > 3rd Place > Semifinals > Quarterfinals > Earlier rounds
- Within same round priority, higher stake tournaments shown first
- Links to spectate matches and view tournament brackets

## Lobby Features
- Game mode tabs (Classic, Interactive, Classic Joker, Interactive Joker)
- Filter by min/max stake
- Sort: newest, lowest to highest stake, highest to lowest stake
- Rakeback tier display
- Dual jackpot pool banner with live amounts

## Match-Found Popup System
- Polling every 3 seconds on lobby/tournaments pages for new active matches
- Popup overlay with opponent info and 5-second countdown timer
- Auto-redirect to match page after countdown
- sessionStorage persists seen match IDs to prevent duplicate popups
- Works for both lobby and tournament matches

## Running
- `python app.py` starts Flask dev server on port 5000
- Production: `gunicorn --bind=0.0.0.0:5000 --reuse-port app:app`

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string
- `SESSION_SECRET` - Flask session secret key

## Recent Changes (Feb 2026)
- Dual jackpot pools: Standard (classic/interactive) and Joker (classic_joker/interactive_joker)
- Jackpot countdown timer with configurable accumulation period
- Watch page: top 5 biggest lobby games + top 5 most important tournament matches
- Rakeback display fix: ensure_consistent() prevents tier/percent mismatch
- Match-found popup with auto-redirect and sessionStorage persistence
- 4 game modes: BJ Classic, BJ Interactive, Classic Joker, Interactive Joker
- Joker support in engine: 4 jokers per deck, optimal value 1-11, Joker+10=BJ, split jokers no BJ
- Classic mode auto-dealer (stand 17+), Interactive mode manual dealer choices
- Game mode tabs in lobby and tournaments, mode badges on match cards
- Tournament system expanded: 5 player sizes (8/16/32/64/128), dynamic bracket generation, unregister support
- Rake system: configurable lobby rake by stake tiers, tournament rake per type
- Admin panel: full configuration dashboard for rake, payouts, coins, rakeback, stats, jackpot
- Rakeback system: 4 tiers with configurable thresholds and periodic reset
- Lobby filters: min/max stake, sorting options
- Currency conversion: $1 = 100 coins throughout
- Tactical joker value choice: players pick 1-11 for each joker before acting, permanent per hand
- Case-insensitive login and registration

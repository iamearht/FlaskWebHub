# Two-Circle Royal 21: Free Blackjack Game Mode

A multiplayer hybrid Poker × Blackjack game implemented as a new game mode ("Free Blackjack") in the FlaskWebHub platform.

## Features

### Game Mechanics
- **2–7 players** at a table (default 7)
- **Two Chip Circles per hand:**
  - Normal Circle: Main pot
  - Escrow Circle: Side pot (proportional settlement)
- **Realistic Hand Ranking:** Natural Blackjack (Ace + 10-value) beats 21, with complex tiebreak rules
- **Four Game Phases:**
  1. **Setup:** Antes, deal, first-action reveal
  2. **Preflop:** Two-step betting (escrow, then normal) with pot-limit calculations
  3. **Draw:** Hit, Stand, Double, or Split actions
  4. **River:** Final two-step betting round
  5. **Showdown:** Hand evaluation and pot distribution
- **Deterministic RNG:** Seedable random number generator for reproducible simulations and testing
- **Split Handling:** Full support for splitting pairs with proper hand evaluation

### Architecture
- **Pure Python Game Engine** (`blackjack_game_engine.py`): Card evaluation, hand ranking, pot settlement
- **Flask Integration** (`blackjack_game_bp.py`): REST API for table management and actions
- **Lightweight Frontend** (HTML/JS): Real-time table view with card display
- **Comprehensive Tests** (`test_blackjack_game.py`): 42+ unit tests covering all game rules

---

## Game Rules

### Table Setup
- Players sit clockwise with a **Button** (dealer position)
- Button moves clockwise after each hand
- Minimum stack for play: 10 chips

### Phase 0: Setup & Deal
1. **Escrow Ante:** Every player posts 1 chip to Escrow
2. **Button Post:** Button posts 1 chip to Normal circle
3. **Deal:** Each player receives 2 private cards
4. **Deck Reshuffle:** New deck shuffled each hand

### Phase 1: Preflop Betting
Action order starts **left of button**, proceeds clockwise.

Each player's turn has **two steps:**

**Step 1A: Escrow Phase (optional)**
- Player may add chips to Escrow (up to remaining stack)
- Purpose: Increase pot-limit cap for betting round

**Step 1B: Normal Betting Phase**
- **Fold:** Forfeit all chips in this hand
- **Call:** Match the current bet
- **Check:** Pass if no bet active
- **Bet:** Place initial bet (capped by pot-limit rule)
- **Raise:** Increase current bet (capped by pot-limit rule)

**Pot-Limit Calculation:**
```
TABLE_TOTAL = sum(all players' Normal + Escrow currently in play)
MAX_BET = TABLE_TOTAL
```
Each player's bet cannot exceed TABLE_TOTAL.

### Phase 2: Draw Phase (Hit/Stand/Double/Split)
Action order: Remaining players, left of button clockwise.

Each player chooses **one:**

#### Hit
- Draw cards one at a time
- Decide after each draw to continue or stop
- **Escrow Lock:** Player cannot add to Escrow after hitting

#### Stand
- No additional cards
- Escrow remains unlocked (can be added in River)

#### Double
- Draw exactly 1 additional card and automatically stand
- Match current Normal circle bet with additional chips
- Allowed only on initial 2-card hand

#### Split
- Allowed only if two original cards have **same rank**
- Creates two separate hands, each starting with one card
- Play each split hand following same rules
- Example: Two 7s → Play two 7-x hands independently

**Special Rule: Split Aces**
- If a split Ace receives a 10-value card: **21 but NOT natural blackjack**
- Loses to any natural blackjack

### Phase 3: River (Final Betting)
Again, **two-step turns:**

**Step 3A: Escrow Phase (conditional)**
- Only players who did NOT hit in Draw phase can add to Escrow
- Hit players: **Escrow is locked** (cannot add more)

**Step 3B: Normal Betting**
- Same as Preflop: Check, Bet, Call, Raise, Fold
- Pot-limit rule applies

### Hand Evaluation

#### Blackjack Values
- Ace: 11 (if no bust), else 1
- 2–9: Face value
- 10, J, Q, K: 10

#### Hand Ranking (Highest to Lowest)
1. **Natural Blackjack** (2 cards: Ace + 10-value, not from split)
   - Tiebreak by 10-value rank: K > Q > J > 10
   - Tiebreak by suitedness: Suited (same suit) > Offsuit
   - Both same rank & both suited: Tie (split pot)
2. **21** (non-natural: 3+ cards)
3. **20, 19, 18, ..., 1, 0**
4. **Bust** (>21): Loses to any non-bust

#### Showdown Settlement

**Main Pot (Normal Circles):**
- Best hand wins the sum of all Normal circle contributions

**Escrow Pot (Proportional):**
- Each player can win escrow from opponents only up to amount they contributed
- Layered side-pot calculation:
  - Sort players by escrow contribution
  - Award each layer to best eligible hand among contributors
  - Folded players lose escrow entirely

---

## Implementation Details

### File Structure
```
blackjack_game_engine.py        # Pure game logic (no Flask dependencies)
blackjack_game_bp.py            # Flask blueprint for REST API
test_blackjack_game.py          # 42+ unit tests
templates/
  blackjack_lobby.html          # Lobby UI
  blackjack_table.html          # Table view UI
app.py                          # Register blueprint
```

### Game Engine API

#### Creating a Table
```python
from blackjack_game_engine import BlackjackGameEngine

players = [(user_id, username), (user_id2, username2), ...]
engine = BlackjackGameEngine(seed=42)  # Deterministic for tests
state = engine.create_table(players, initial_stack=1000)
```

#### Starting a Hand
```python
engine.start_hand()
# Engine initializes antes, deals cards, sets phase to PREFLOP
```

#### Taking an Action
```python
from blackjack_game_engine import ActionType

engine.player_action(seat=0, action=ActionType.HIT)
engine.player_action(seat=1, action=ActionType.RAISE, amount=50)
```

#### Exporting State
```python
state_dict = engine.get_state()
# Returns JSON-serializable dict with all game info
```

### API Endpoints (Flask)

#### Table Management
- `POST /blackjack/create_table` → Create new table
- `GET /blackjack/lobby` → View available tables
- `GET /blackjack/table/<id>` → View table UI

#### Game API
- `GET /blackjack/api/table/<id>/state` → Get current game state
- `POST /blackjack/api/table/<id>/start_hand` → Start new hand
- `POST /blackjack/api/table/<id>/action` → Player action
  - Body: `{"seat": 0, "action": "hit", "amount": 0}`
- `POST /blackjack/api/table/<id>/advance_phase` → Force phase advance

---

## Testing

### Running Tests
```bash
python -m pytest test_blackjack_game.py -v
```

### Test Coverage
- ✅ Card representation and deck operations
- ✅ Blackjack value computation (Aces, face cards, bustcomputation)
- ✅ Natural blackjack detection (2-card vs split)
- ✅ Hand ranking and comparison
- ✅ Natural blackjack tiebreaks (rank, suitedness)
- ✅ Split Aces (21 but not natural blackjack)
- ✅ Engine initialization and game state
- ✅ Player actions (hit, stand, double, split, fold)
- ✅ Escrow locking after hit
- ✅ Pot calculations
- ✅ Deterministic RNG with seeding
- ✅ Full hand simulation

### Test Result: 42/42 PASSED ✅

---

## Usage Example

### Minimal Simulation
```python
from blackjack_game_engine import BlackjackGameEngine, ActionType

# Create engine with deterministic seed
engine = BlackjackGameEngine(seed=12345)

# Create 3-player table
players = [(1, 'Alice'), (2, 'Bob'), (3, 'Charlie')]
engine.create_table(players, initial_stack=1000)

# Start hand: antes posted, cards dealt
engine.start_hand()
state = engine.game_state
print(f"Phase: {state.phase.value}")  # preflop
print(f"Normal Pot: {state.normal_pot}")  # 1
print(f"Escrow Pot: {state.escrow_pot}")  # 3

# Player actions
engine.player_action(0, ActionType.FOLD)
engine.player_action(1, ActionType.RAISE, amount=50)
engine.player_action(2, ActionType.CALL, amount=50)

# Export state
state_dict = engine.get_state()
print(state_dict)
```

### Using Seedable RNG for Reproducible Simulations
```python
# Two engines with same seed produce identical card sequences
engine1 = BlackjackGameEngine(seed=99999)
engine1.create_table([(1, 'A'), (2, 'B')])
engine1.start_hand()
cards1 = [str(c) for p in engine1.game_state.players for c in p.hand.original_cards]

engine2 = BlackjackGameEngine(seed=99999)
engine2.create_table([(1, 'A'), (2, 'B')])
engine2.start_hand()
cards2 = [str(c) for p in engine2.game_state.players for c in p.hand.original_cards]

assert cards1 == cards2  # Always true!
```

---

## Configuration Constants

### Game Rules
```python
ESCROW_ANTE = 1              # Chips posted to Escrow each hand
BUTTON_ANTE = 1              # Chips button posts to Normal
TABLE_MIN_PLAYERS = 2
TABLE_MAX_PLAYERS = 7
TABLE_DEFAULT_PLAYERS = 7
```

### Escrow Add Limits
```python
ESCROW_ADD_LIMIT_TYPE = "unlimited"  # Options:
  # "unlimited" - can add up to full stack
  # "match_normal" - can add up to current Normal circle size
  # (or implement custom ratio)
```

All constants are easily configurable at top of `blackjack_game_engine.py`.

---

## Future Enhancements

### Phase 1: Production Ready
- [ ] Database persistence for tables (SQLAlchemy models)
- [ ] WebSocket support for real-time multiplayer
- [ ] AI dealer/bot players for testing
- [ ] Chip stacking and side-pot visualization
- [ ] Hand history and replay system

### Phase 2: Advanced Features
- [ ] Tournament mode (multi-table elimination)
- [ ] Spectator mode (watch live games)
- [ ] Game statistics and leaderboards
- [ ] Rake/commission system
- [ ] Bankroll management and limits

### Phase 3: Polish
- [ ] Animated card dealing
- [ ] Sound effects
- [ ] Mobile responsive design
- [ ] Account integration with main wallet
- [ ] Fairness verification (verifiable RNG)

---

## Architecture Notes

### Separation of Concerns
- **Game Engine:** Pure Python, no framework dependencies
  - Card logic
  - Hand evaluation
  - Pot settlement
  - Phase management
  - Deterministic RNG

- **Flask Blueprint:** Request handling, authentication, session management
  - REST API endpoints
  - User validation
  - State serialization

- **Frontend:** Simple HTML/JS, easy to extend with React/Vue
  - Real-time updates (polling, can be WebSocket)
  - Table visualization
  - Action submission

### Extensibility
1. **Game Rules:** Modify `blackjack_game_engine.py` constants and phase logic
2. **Persistence:** Extend `blackjack_game_bp.py` to use database models instead of in-memory dict
3. **Frontend:** Replace `blackjack_table.html` with React/Vue component
4. **Integration:** Add wallet deductions/payouts via existing User model

---

## Security Considerations

### RNG & Fairness
- Uses Python's `random.Random` with seed injection
- For production, consider:
  - Server-side RNG only (no client-side shuffling)
  - Cryptographic randomness (`secrets` module)
  - Verifiable randomness (blockchain, commitment schemes)

### Input Validation
- All action amounts validated against player stack
- Pot-limit cap enforced server-side
- Folded players cannot take actions
- Invalid phase actions rejected

### Authentication
- `@login_required` on all endpoints
- User ID matched to seat owner before action execution
- No privilege escalation between seats

---

## License & Attribution

Implemented as extension to FlaskWebHub.
Game design: Two-Circle Royal 21 (custom hybrid rules).
Code: Python 3.11+, Flask 3.x, SQLAlchemy.

---

## Support & Testing

### Quick Test
```bash
cd /home/user/FlaskWebHub
python -m pytest test_blackjack_game.py -v
```

### Manual Play
1. Run Flask server: `python app.py`
2. Navigate to: `http://localhost:5000/blackjack/lobby`
3. Create a table
4. Join table and play!

---

**Happy playing! 🎰🃏**

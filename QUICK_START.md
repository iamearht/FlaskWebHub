# Two-Circle Royal 21: Quick Start Guide

## 5-Minute Setup

### 1. Run Tests
```bash
python -m pytest test_blackjack_game.py -v
# Expected: 42 passed ✅
```

### 2. Import Engine
```python
from blackjack_game_engine import BlackjackGameEngine, ActionType

# Create engine with deterministic seed
engine = BlackjackGameEngine(seed=42)

# Create table with 3 players
players = [(1, 'Alice'), (2, 'Bob'), (3, 'Charlie')]
engine.create_table(players, initial_stack=1000)

# Start a hand
engine.start_hand()
print(engine.get_state())
```

### 3. Run Web App
```bash
python app.py
# Visit: http://localhost:5000/blackjack/lobby
```

---

## Game Rules (TL;DR)

### Winning Hands (Ranked)
1. **Natural Blackjack** (Ace + 10-value, 2 cards) — Tie breakers: K > Q > J > 10, then Suited > Offsuit
2. **21** (3+ cards)
3. **20, 19, 18, ..., 1**
4. **Bust** (>21) — Loses

### Phases
| Phase | What Happens | Who Acts |
|-------|------------|----------|
| **Setup** | Post antes (1 escrow each, 1 normal button), deal 2 cards | *No actions* |
| **Preflop** | Two-step turns: (1) add escrow, (2) fold/call/bet/raise | Left of button, clockwise |
| **Draw** | Hit/Stand/Double/Split | Same order |
| **River** | Two-step turns: (1) add escrow (if didn't hit), (2) fold/call/bet/raise | Same order |
| **Showdown** | Compare hands, settle pots | *Automatic* |

### Key Mechanics
- **Escrow Lock:** After hitting, player can't add to escrow in river
- **Pot-Limit:** Max bet = sum of all chips currently on table (Normal + Escrow)
- **Split:** Only if matching rank (both cards same rank)
- **Split Aces + 10:** Makes 21 but NOT natural blackjack (loses to natural)

---

## API Quick Reference

### REST Endpoints

```bash
# Create table (7 seats default)
POST /blackjack/create_table
Body: {"num_seats": 7}
Response: {"table_id": 123, ...}

# Get game state
GET /blackjack/api/table/123/state
Response: {
  "phase": "preflop",
  "normal_pot": 1,
  "escrow_pot": 3,
  "players": [...],
  "current_player_seat": 1
}

# Start new hand
POST /blackjack/api/table/123/start_hand

# Take action
POST /blackjack/api/table/123/action
Body: {
  "seat": 0,
  "action": "hit",  # hit, stand, double, split, fold, call, bet, raise
  "amount": 50      # for bet/raise/call/add_escrow
}

# Advance phase
POST /blackjack/api/table/123/advance_phase
```

---

## Action Types

### During Draw Phase
```python
ActionType.HIT      # Draw 1 card, decide again
ActionType.STAND    # Keep hand as-is
ActionType.DOUBLE   # Double bet, draw 1 card, auto-stand
ActionType.SPLIT    # (if matching rank) Create 2 hands
```

### During Preflop/River
```python
ActionType.ADD_ESCROW  # Add chips to escrow circle
ActionType.FOLD        # Forfeit hand
ActionType.CALL        # Match current bet
ActionType.BET         # Initiate bet
ActionType.RAISE       # Increase bet
ActionType.CHECK       # Pass if no active bet
```

---

## Hand Evaluation Examples

### Natural Blackjack Comparison
```
A♠K♠  vs  A♥K♥     → Tie (both natural, same rank, both suited)
A♠K♠  vs  A♠Q♥     → A♠K♠ wins (K > Q)
A♠K♣  vs  A♠K♠     → A♠K♠ wins (suited > offsuit)
A♠K♣  vs  A♥10♠    → A♠K♣ wins (K > 10)
```

### Hand Value Calculation
```
[7, 7, 7]           → 21 (not natural)
[A, 5]              → 16 (A counts as 11, 5 counts as 5)
[A, 5, 5]           → 21 (A now counts as 1 + 5 + 5 + 10)
[K, Q, 5]           → 25 (BUST - loses to any non-bust)
[A, A, 9]           → 21 (one A as 11, one as 1)
```

---

## Code Snippets

### Simulate a Full Hand
```python
from blackjack_game_engine import BlackjackGameEngine, ActionType

engine = BlackjackGameEngine(seed=42)
engine.create_table([(1, 'Alice'), (2, 'Bob')])
engine.start_hand()

# Preflop: Alice hits, Bob calls
engine.game_state.current_player_seat = 0
engine.player_action(0, ActionType.HIT)

engine.game_state.current_player_seat = 1
engine.player_action(1, ActionType.CALL, amount=50)

# Export final state
final_state = engine.get_state()
print(f"Winner: {final_state['players'][0]['username']}")
```

### Deterministic Simulation
```python
# Same seed = same cards every time
for sim in range(100):
    engine = BlackjackGameEngine(seed=12345)
    engine.create_table(players, initial_stack=1000)
    engine.start_hand()
    # Cards will be identical each simulation
```

### Extract Player Hands
```python
state = engine.get_state()
for player in state['players']:
    print(f"{player['username']}: {player['revealed_card']}")
    print(f"  Stack: {player['stack']}")
    print(f"  Normal: {player['normal_circle']}")
    print(f"  Escrow: {player['escrow_circle']}")
```

---

## Config Constants

Edit at top of `blackjack_game_engine.py`:

```python
ESCROW_ANTE = 1              # Chips each player posts to escrow
BUTTON_ANTE = 1              # Chips button posts to normal
TABLE_MIN_PLAYERS = 2
TABLE_MAX_PLAYERS = 7
TABLE_DEFAULT_PLAYERS = 7
ESCROW_ADD_LIMIT_TYPE = "unlimited"  # How much can be added to escrow
```

---

## Common Patterns

### Check if hand is natural blackjack
```python
from blackjack_game_engine import is_natural_blackjack

cards = [Card('A', '♠'), Card('K', '♥')]
if is_natural_blackjack(cards):
    print("Natural blackjack!")
```

### Get hand value
```python
from blackjack_game_engine import compute_blackjack_value

cards = [Card('A', '♠'), Card('K', '♥')]
value = compute_blackjack_value(cards)
print(f"Value: {value}")  # 21
```

### Compare two hands
```python
from blackjack_game_engine import get_hand_rank_and_value

hand1 = [Card('A', '♠'), Card('K', '♠')]
hand2 = [Card('7', '♠'), Card('7', '♥'), Card('7', '♦')]

rank1, val1 = get_hand_rank_and_value(hand1)
rank2, val2 = get_hand_rank_and_value(hand2)

if rank1.value > rank2.value or (rank1 == rank2 and val1 > val2):
    print("Hand 1 wins!")
else:
    print("Hand 2 wins!")
```

---

## File Reference

| File | Purpose | LOC |
|------|---------|-----|
| `blackjack_game_engine.py` | Core game logic (pure Python) | 619 |
| `blackjack_game_bp.py` | Flask REST API | 175 |
| `test_blackjack_game.py` | Unit tests (42 tests) | 700+ |
| `templates/blackjack_lobby.html` | Table list UI | 285 |
| `templates/blackjack_table.html` | Game table UI | 420 |
| `BLACKJACK_GAME_README.md` | Full rules & docs | 450+ |
| `ARCHITECTURE.md` | System design | 350+ |

---

## Troubleshooting

### Tests fail
```bash
# Make sure pytest is installed
pip install pytest

# Run with verbose output
python -m pytest test_blackjack_game.py -vv
```

### ImportError: No module named 'flask'
```bash
# Flask blueprint requires Flask
pip install flask flask-sqlalchemy flask-login

# But game engine works standalone
python -c "from blackjack_game_engine import BlackjackGameEngine"
```

### State doesn't update in browser
```javascript
// Check browser console for fetch errors
// Check that /blackjack/api/table/123/state endpoint is responsive
// Verify table_id is correct in URL
```

### Actions keep failing
```python
# Verify:
1. Player is at current_player_seat
2. Game is in correct phase
3. Action is legal for that phase
4. Player has sufficient stack
```

---

## Next Steps

1. **Test It:** `python -m pytest test_blackjack_game.py -v`
2. **Read Docs:** Open `BLACKJACK_GAME_README.md`
3. **Play:** `python app.py` then visit `/blackjack/lobby`
4. **Integrate:** Add DB persistence or WebSocket upgrade
5. **Extend:** Add AI players, tournament mode, leaderboards

---

## Resources

- **Rules:** See `BLACKJACK_GAME_README.md` for complete game specification
- **Architecture:** See `ARCHITECTURE.md` for system design and scalability
- **API Docs:** See `blackjack_game_bp.py` route docstrings
- **Tests:** See `test_blackjack_game.py` for usage examples
- **Code:** See `blackjack_game_engine.py` for implementation details

---

**Status:** ✅ Complete and tested
**Tests:** 42/42 passing
**Ready for:** Development, testing, deployment

🎰 Happy playing!

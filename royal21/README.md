# Royal 21 - Poker × Blackjack Hybrid

A real-time multiplayer web game combining poker betting mechanics with blackjack hand evaluation and ranking. Built with Python/FastAPI backend and modern JavaScript frontend with WebSocket support.

## Quick Start

### Prerequisites
- Python 3.11+
- pip

### Installation

```bash
# Clone and enter directory
git clone <repo-url>
cd royal21-game

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

```bash
# Run FastAPI server (development)
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at: `http://localhost:8000`

### Running Tests

```bash
pytest test_engine.py -v

# Run specific test category
pytest test_engine.py::test_hand_total_basic -v
```

## Game Overview

Royal 21 is a 2-7 player game combining:
- **Poker-style betting**: Multiple betting rounds with custom pot-limit sizing
- **Blackjack hand evaluation**: Hands ranked by total (closest to 21 without busting)
- **Two chip circles**: Normal (main pot) and Escrow (side pot)
- **Deterministic engine**: Seedable RNG for reproducible games

### Core Concepts

#### Chip Circles
Each player has two chip circles per hand:
- **Normal Circle**: Main pot chips
- **Escrow Circle**: Side pot chips
- Fold = forfeit BOTH circles

#### TABLE_TOTAL
Custom pot-limit sizing metric:
```
TABLE_TOTAL = sum(all active players' normal circles)
            + sum(all active players' escrow circles)
```

Used for maximum raise calculation:
```
max_raise_to = current_highest_normal_bet + TABLE_TOTAL
```

#### Natural Blackjack
- Exactly 2 cards: one Ace + one 10-value card
- Special ranking even above regular 21
- Tiebreak: K > Q > J > 10 (10-card rank)
- Suited beats offsuit for same rank

#### Split Hands
- Only if original 2 hole cards have same rank
- Each split hand plays separately in draw phase
- Split-ace receiving 10 = 21 but NOT natural blackjack
- Main pot and escrow divided 50/50 between split hands

#### Escrow Lock
- If player HIT during draw phase, they CANNOT add escrow on river
- Double down does NOT trigger escrow lock
- Prevents aggressive escrow betting after drawing

## Game Flow

### Phase 0: SETUP
- Every player posts 1 chip escrow ante
- Button posts 1 chip to normal circle
- Deal 2 private cards to each player

### Phase 1: PREFLOP BETTING
Two-step turns (repeat for each active player):
1. **Escrow Step**: Player may add chips to escrow (optional)
2. **Normal Betting Step**: Fold/Check/Bet/Call/Raise

**Reveal Rule**: On first preflop action, player MUST choose one hole card to reveal publicly.

Betting ends when all active players match current highest or fold.

### Phase 2: DRAW
Player decisions (in turn order):
- **Stand**: Take no more cards
- **Hit**: Draw cards one at a time
- **Double**: Draw exactly 1 card, then stand (counts as escrow-free action)
- **Split**: Split into two hands (if original cards same rank)

### Phase 3: RIVER BETTING
Same as preflop, but with restrictions:
- Players who HIT cannot add escrow
- All other mechanics identical

### Phase 4: SHOWDOWN
1. Evaluate all remaining hands
2. Distribute main pot (with split-hand half-pot logic)
3. Distribute escrow pot (with layered side-pot logic)

### Phase 5: HAND OVER
- Move button clockwise
- Reset all player states
- Return to Phase 0 for next hand

## Hand Ranking

Highest to lowest:
1. **Natural Blackjack** (2 cards: A + 10-value)
   - Tiebreak by 10-card rank (K > Q > J > 10)
   - Tiebreak by suited (beats offsuit)
2. **21** (any card count)
3. **20**
4. **19** ... down to lowest non-bust total
5. **Bust** (any total > 21)

### Special Cases

**Split-Ace Receiving 10**:
- Total = 21 but NOT natural blackjack
- Loses to any actual natural blackjack

**Multiple Natural Blackjacks**:
- Apply ten-card rank tiebreak (K > Q > J > 10)
- If same ten-card rank: suited beats offsuit
- If still tied: split pot equally

## Betting Mechanics

### Custom Raise Cap
During betting rounds, when facing a bet:
```
max_raise_to = current_highest_normal + TABLE_TOTAL
```

Example:
- Current highest normal bet: 10
- Table total (all active players' normal + escrow): 50
- Maximum you can raise to: 10 + 50 = 60

### All-In Mechanics
If player doesn't have enough chips to match/raise, they go all-in with remaining stack.

### Escrow Step
Optional. Player may add 0 to remaining_stack chips to escrow circle. Increases TABLE_TOTAL immediately.

## Pot Settlement

### Main Pot Settlement
- **No splits**: Best hand wins entire pot (ties split equally)
- **With splits**: Divide pot in half (A and B)
  - Split player's Hand A competes in pot_A
  - Split player's Hand B competes in pot_B
  - Non-split hands compete in BOTH halves
  - Determine winner(s) of each half independently

### Escrow Pot Settlement
Layered side-pot logic (capped by each player's escrow contribution):

1. Sort players by escrow amount ascending
2. Create layers: each layer covers players with escrow >= threshold
3. Award each layer to best hand among layer participants
4. If splits: divide escrow into A/B halves using same model as main pot

## Architecture

### Backend (`main.py`)
- **FastAPI**: Modern async Python web framework
- **WebSockets**: Real-time bidirectional communication
- **In-Memory Storage**: Games stored in dictionaries (production would use DB)

### Game Engine (`engine.py`, `game_state.py`, etc.)
- **Deterministic**: Seedable RNG, reproducible games
- **Stateful**: Complete game state maintained per game
- **Validated**: All actions validated before execution
- **Logged**: Hand history tracking via action logs

### Frontend (`frontend/`)
- **Vanilla JavaScript**: No framework dependencies for simplicity
- **Poker-Inspired UI**: Dark theme, clear seat layout, chip display
- **Responsive**: Works on desktop and tablet
- **WebSocket Integration**: Real-time game updates

### Tests (`test_engine.py`)
- Unit tests for all game mechanics
- Deterministic testing with seeded RNG
- Coverage of edge cases and tiebreaker logic

## Implementation Assumptions

### Chip Display
- Chips shown in Normal and Escrow circles at each seat
- Updated in real-time via WebSocket
- "Stack" shows remaining uncommitted chips

### Seat Layout
- Default 7 seats arranged in circle
- Configurable at game creation
- Button position rotates clockwise each hand

### Action Order
- Preflop: starts left of button (seat button+1), clockwise
- Draw: same order as preflop
- River: same order as preflop

### Draw Phase Implementation
- Each player plays sequentially (not simultaneous)
- Split hands played in order (Hand A, then Hand B)
- Server tracks current hand being played

### No Re-Splits
- Players cannot re-split resulting split hands
- Configurable (default OFF)

### No Double After Split
- Cannot double down on split hands
- Configurable (default OFF)

### Minimum Bet
- Configurable, default = 1 chip
- Prevent betting game with no bets

### Blind Structure
- Ante: 1 escrow per player
- Post: 1 normal for button
- Configurable for variants

### Legal Actions Display
- Server provides legal actions per player per phase
- Frontend displays enabled/disabled buttons accordingly
- Player types in bet amounts (no slider)

### Showdown Automation
- Server automatically evaluates hands
- Pots distributed automatically
- Results sent via WebSocket to all players

## API Endpoints

### REST (HTTP)

`POST /api/games/create`
- Create new game
- Body: `{ "players": 2-7, "starting_stack": 50+ }`
- Returns: `{ "game_id": "...", "status": "created" }`

`GET /api/games/{game_id}?player_seat=0`
- Get current game state
- Returns: Full game state object

`POST /api/games/{game_id}/start`
- Start game (begin first hand)
- Returns: `{ "status": "started", "phase": "preflop" }`

### WebSocket (`/ws/{game_id}/{player_seat}`)

**Client → Server** (send action):
```json
{
  "action": "bet",
  "amount": 10
}
```

**Supported Actions**:
- `escrow_add` (param: `amount`)
- `fold`
- `check`
- `call`
- `bet` (param: `amount`)
- `raise` (param: `raise_to`)
- `stand`
- `hit`
- `double`
- `split`
- `get_state`
- `get_legal_actions`
- `start_hand`

**Server → Client** (receive):
```json
{
  "type": "state_update",
  "data": { /* full game state */ }
}
```

or

```json
{
  "type": "legal_actions",
  "data": { /* legal actions for this player */ }
}
```

## Testing

### Key Test Coverage

✓ Natural blackjack detection
✓ Blackjack ranking (K > Q > J > 10)
✓ Suited vs offsuit tiebreaker
✓ Split-ace 21 not natural blackjack
✓ Escrow-lock enforcement
✓ Custom raise cap calculation
✓ Side-pot layering
✓ Split-hand half-pot settlement
✓ Deterministic shuffling with seed
✓ Soft-hand ace handling

### Run Tests

```bash
# All tests
pytest test_engine.py -v

# Specific test
pytest test_engine.py::test_blackjack_suited_beats_offsuit -v

# With coverage
pytest test_engine.py --cov=. --cov-report=html
```

## File Structure

```
royal21-game/
├── card.py                 # Card, Suit, Rank, Deck classes
├── hand.py                 # Hand evaluation and ranking logic
├── game_state.py           # GameState, PlayerState, Phase definitions
├── engine.py               # Main GameEngine orchestrator
├── main.py                 # FastAPI server and WebSocket handlers
├── test_engine.py          # Unit tests (pytest)
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── frontend/
│   ├── index.html          # Main HTML page
│   ├── css/
│   │   └── style.css       # Poker-inspired styling
│   └── js/
│       └── app.js          # WebSocket and UI logic
```

## Known Limitations / Future Improvements

1. **In-Memory Storage**: Games only exist while server running. Use database for persistence.
2. **No Authentication**: All players on same table can play any seat. Add user auth.
3. **Showdown Logic Incomplete**: Escrow layering needs full implementation.
4. **Single Table**: No multi-table support yet.
5. **UI Improvements**:
   - Card hand history/board state
   - Better split hand visualization
   - Chip animations on pot wins
6. **Performance**: In-memory games don't scale; consider Redis or DB for production.

## Example Game Flow

```
1. User clicks "Create Game" → 7 players, $200 stacks
2. Browser loads frontend, connects WebSocket
3. User clicks "Start Game"
4. Server deals cards, broadcasts state
5. Player 1 (left of button) sees legal actions
   - Can add escrow, then must reveal a hole card, then act
6. Player 1 checks/bets
7. Action rotates through other players
8. Betting round ends when all matched or folded
9. Draw phase begins
   - Players choose: stand, hit, double, or split
10. River betting (restricted escrow if hit)
11. Showdown: hands evaluated, pots distributed
12. Hand over → button moves, repeat
```

## Troubleshooting

**WebSocket Connection Fails**:
- Check server is running (`http://localhost:8000`)
- Check browser console for connection errors
- Ensure game was created before connecting

**Legal Actions Don't Show**:
- Press "Get State" to refresh
- Check if it's actually your turn (look at current action)
- Verify game phase

**Tests Fail**:
- Ensure pytest installed: `pip install pytest`
- Run from project root: `pytest test_engine.py -v`

## Contributing

Pull requests welcome. Please include tests for new features.

## License

MIT (example only - adjust as needed)

---

**Questions?** Check the code comments or review test cases for examples.

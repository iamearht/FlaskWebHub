# Royal 21 API Usage Examples

This document shows how to interact with the Royal 21 API programmatically.

## Creating a Game

```bash
curl -X POST http://localhost:8000/api/games/create \
  -H "Content-Type: application/json" \
  -d '{
    "players": 3,
    "starting_stack": 200
  }'
```

Response:
```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created"
}
```

## Starting a Game

```bash
curl -X POST http://localhost:8000/api/games/550e8400-e29b-41d4-a716-446655440000/start
```

Response:
```json
{
  "status": "started",
  "phase": "preflop"
}
```

## Getting Game State

```bash
curl http://localhost:8000/api/games/550e8400-e29b-41d4-a716-446655440000?player_seat=0
```

Response:
```json
{
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "phase": "preflop",
  "players": [
    {
      "seat": 0,
      "username": "Player 1",
      "stack": 199,
      "normal_circle": 1,
      "escrow_circle": 1,
      "in_hand": true,
      "revealed_card": null,
      "card_count": 2
    },
    ...
  ],
  "current_action": 1,
  "table_total": 6,
  "normal_pot": 1,
  "escrow_pot": 3,
  "logs": [
    "Hand started. Preflop betting begins."
  ]
}
```

## WebSocket Interaction

### Python Example

```python
import asyncio
import json
import websockets

async def play_game():
    game_id = "550e8400-e29b-41d4-a716-446655440000"
    player_seat = 0

    uri = f"ws://localhost:8000/ws/{game_id}/{player_seat}"

    async with websockets.connect(uri) as websocket:
        # Get current state
        await websocket.send(json.dumps({"action": "get_state"}))
        response = await websocket.recv()
        state = json.loads(response)
        print(f"Game phase: {state['data']['phase']}")

        # Get legal actions
        await websocket.send(json.dumps({"action": "get_legal_actions"}))
        response = await websocket.recv()
        actions = json.loads(response)
        print(f"Legal actions: {actions['data']}")

        # Bet 10 chips
        await websocket.send(json.dumps({
            "action": "bet",
            "amount": 10
        }))

        # Listen for updates
        while True:
            response = await websocket.recv()
            message = json.loads(response)

            if message.get("type") == "state_update":
                print(f"State update - Phase: {message['data']['phase']}")
            elif message.get("type") == "legal_actions":
                print(f"Legal actions received: {message['data']}")

# Run
asyncio.run(play_game())
```

### JavaScript Example

```javascript
const gameId = "550e8400-e29b-41d4-a716-446655440000";
const playerSeat = 0;

const ws = new WebSocket(`ws://localhost:8000/ws/${gameId}/${playerSeat}`);

ws.onopen = function(event) {
    console.log("Connected");

    // Get state
    ws.send(JSON.stringify({"action": "get_state"}));
};

ws.onmessage = function(event) {
    const message = JSON.parse(event.data);

    if (message.type === "state_update") {
        console.log("Phase:", message.data.phase);
        console.log("Pots:", {
            normal: message.data.normal_pot,
            escrow: message.data.escrow_pot
        });
    } else if (message.type === "legal_actions") {
        console.log("Legal actions:", message.data);
    }
};

// Send a bet action
function sendBet(amount) {
    ws.send(JSON.stringify({
        "action": "bet",
        "amount": amount
    }));
}

// Send escrow addition
function addEscrow(amount) {
    ws.send(JSON.stringify({
        "action": "escrow_add",
        "amount": amount
    }));
}

// Fold
function fold() {
    ws.send(JSON.stringify({
        "action": "fold"
    }));
}

// Hit in draw phase
function hit() {
    ws.send(JSON.stringify({
        "action": "hit"
    }));
}

// Double down
function double() {
    ws.send(JSON.stringify({
        "action": "double"
    }));
}

// Split
function split() {
    ws.send(JSON.stringify({
        "action": "split"
    }));
}
```

## Action Sequences

### Betting Round (Preflop)

1. **Get Legal Actions**
```json
{"action": "get_legal_actions"}
```

Response might include: escrow_add, fold, check, bet, call, raise

2. **Add Escrow (Optional)**
```json
{"action": "escrow_add", "amount": 5}
```

3. **Make Normal Bet**
```json
{"action": "bet", "amount": 20}
```

Or if there's already a bet:
```json
{"action": "raise", "raise_to": 50}
```

### Draw Phase

1. **Get Legal Actions**
```json
{"action": "get_legal_actions"}
```

Response might include: stand, hit, double, split

2. **Hit (Draw 1+ Cards)**
```json
{"action": "hit"}
```

3. **Stand**
```json
{"action": "stand"}
```

Or double:
```json
{"action": "double"}
```

Or split (if applicable):
```json
{"action": "split"}
```

### River Betting (After Draw)

Similar to preflop, but with restrictions:
- Cannot add escrow if player hit in draw phase
- Otherwise, same structure as preflop

## Event Flow Example

```
1. Game created
   ↓
2. User clicks "Start Game"
   ↓ GET /api/games/{game_id}/start
   ↓
3. Server starts hand (SETUP phase)
   ↓ WS broadcast state
   ↓
4. Server transitions to PREFLOP
   ↓ WS state_update (current_action = player 1)
   ↓
5. Player 1 gets legal actions
   ↓ send get_legal_actions
   ↓ receive legal_actions
   ↓
6. Player 1 acts (e.g., adds escrow then bets)
   ↓ send escrow_add
   ↓ send bet
   ↓
7. Server updates game state
   ↓ WS broadcast state_update to all players
   ↓
8. Next player gets legal actions
   ↓ Repeat steps 5-8
   ↓
9. Preflop betting ends
   ↓ WS state_update (phase = DRAW)
   ↓
10. Draw phase begins
    ↓ Players choose stand/hit/double/split
    ↓ WS broadcasts each decision
    ↓
11. Draw phase ends
    ↓ WS state_update (phase = RIVER)
    ↓
12. River betting (same as preflop with restrictions)
    ↓
13. Showdown
    ↓ WS state_update with results
    ↓
14. Hand over
    ↓ WS state_update (phase = HAND_OVER)
    ↓
15. User clicks "Next Hand"
    ↓ back to step 2
```

## Error Handling

If an action is invalid, server sends:

```json
{
  "error": "Invalid bet amount (1 to 50)"
}
```

Common errors:
- "Not player's turn"
- "Player not in hand"
- "Not enough chips"
- "Invalid raise (must be between X and Y)"
- "Cannot add escrow after hitting"
- "Cannot double - already doubled"

## Testing with cURL

Create game:
```bash
GAME_ID=$(curl -s -X POST http://localhost:8000/api/games/create \
  -H "Content-Type: application/json" \
  -d '{"players": 2, "starting_stack": 100}' | jq -r '.game_id')

echo "Created game: $GAME_ID"
```

Start game:
```bash
curl -X POST http://localhost:8000/api/games/$GAME_ID/start
```

Get state:
```bash
curl http://localhost:8000/api/games/$GAME_ID?player_seat=0 | jq '.'
```

## Testing with Postman

1. Import collection (or create manually):
   - **POST** Create Game: `POST localhost:8000/api/games/create`
   - **POST** Start Game: `POST localhost:8000/api/games/{game_id}/start`
   - **GET** Get State: `GET localhost:8000/api/games/{game_id}?player_seat=0`

2. For WebSocket testing, use Postman's WebSocket feature:
   - URL: `ws://localhost:8000/ws/{game_id}/{player_seat}`
   - Send: `{"action": "get_state"}`

---

For more details, see README.md

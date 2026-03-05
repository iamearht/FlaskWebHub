# Royal 21 - Quick Start Guide

Get Royal 21 running in 5 minutes.

## Prerequisites

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **pip** - Included with Python
- **Git** (optional) - For cloning the repo

## Step 1: Setup (1 minute)

### Option A: Automated (Recommended)

**Linux/macOS:**
```bash
bash setup.sh
```

**Windows:**
```cmd
setup.bat
```

This will:
1. Create a virtual environment
2. Install dependencies
3. Run tests

### Option B: Manual Setup

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Linux/macOS:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests to verify
pytest test_engine.py -v
```

## Step 2: Start Server (1 minute)

```bash
python main.py
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Step 3: Open Browser (1 minute)

Navigate to:
```
http://localhost:8000
```

You should see the Royal 21 game interface with empty seats.

## Step 4: Play Game (2 minutes)

1. **Create Game**: Click "New Game"
   - Select 2-7 players (default 7)
   - Set starting stack (default 200)
   - Click "Create"

2. **Start Game**: Click "Start Game"
   - Game deals cards
   - First player to act sees action panel

3. **Play**:
   - **Betting rounds**: Add escrow (optional), then fold/check/bet/call/raise
   - **Draw phase**: Stand, hit, double, or split
   - **River**: Same betting with restrictions
   - **Showdown**: Results automatic

4. **Next Hand**: After hand over, click "Start Game" again

## Gameplay Basics

### Your Turn
When it's your turn, you'll see:
- **Phase**: Current game phase (Preflop, Draw, River, Showdown)
- **Action Panel**: Shows available actions
- **Pots**: Normal pot and Escrow pot amounts
- **Seats**: Player positions with chip counts

### Making Decisions
1. **Add Escrow** (optional): Enter amount, click "Add Escrow"
2. **Normal Betting**: Choose fold/check/bet/call/raise
3. **Draw Phase**: Choose stand/hit/double/split
4. **See Results**: Automatically after showdown

### Game Rules (Summary)
- Closest to 21 wins (blackjack style)
- **Natural Blackjack** (A + 10-value = 21): Special ranking
- **Two Chip Circles**: Normal (main pot) & Escrow (side pot)
- **Split Allowed**: If your 2 cards have same rank
- **Escrow Lock**: Can't add escrow on river if you hit

[Full rules in README.md](README.md)

## Troubleshooting

### Server won't start
```
ERROR: Address already in use
```
Change port in `main.py`:
```python
uvicorn.run(app, host="0.0.0.0", port=8001)  # Use 8001 instead
```

### WebSocket connection fails
- Check server is running (http://localhost:8000 in browser)
- Refresh browser (F5)
- Check browser console (F12 > Console tab)
- Try different port if 8000 is in use

### Tests fail
```bash
# Ensure pytest installed
pip install pytest

# Run tests again
pytest test_engine.py -v
```

### Frontend doesn't load
- Make sure server is running: `python main.py`
- Try `http://localhost:8000` (not `localhost:8000`)
- Clear browser cache (Ctrl+Shift+Delete)

## File Structure

```
royal21-game/
├── card.py              ← Card & Deck logic
├── hand.py              ← Hand evaluation & ranking
├── game_state.py        ← Game state objects
├── engine.py            ← Main game engine
├── main.py              ← FastAPI server (START HERE)
├── test_engine.py       ← Unit tests
├── config.py            ← Customizable settings
├── requirements.txt     ← Python dependencies
├── frontend/
│   ├── index.html       ← Game interface
│   ├── css/style.css    ← Poker-inspired styling
│   └── js/app.js        ← WebSocket & UI logic
├── README.md            ← Full documentation
├── QUICKSTART.md        ← This file
└── EXAMPLE_API.md       ← API usage examples
```

## Next Steps

- **Customize Game**: Edit `config.py` for variants
- **Understand Rules**: Read [README.md](README.md)
- **API Integration**: See [EXAMPLE_API.md](EXAMPLE_API.md)
- **Run Tests**: `pytest test_engine.py -v`

## Playing with Friends

To play with others:

1. Host server on accessible machine (not localhost)
2. Share URL: `http://<your-ip>:8000`
3. Friends open same URL in browser
4. Everyone clicks "Create Game"
5. All play in same game

## Development

### Enable Debug Mode
Set `DEBUG = True` in `config.py`

### Add Custom Rules
1. Edit `config.py` settings
2. Modify `engine.py` logic
3. Add tests in `test_engine.py`
4. Run: `pytest test_engine.py -v`

### Database Integration
Currently uses in-memory storage. For production:
1. Add SQLAlchemy models
2. Replace `games` dict in `main.py` with database
3. Store game history and stats

## Help

- **Full Rules**: [README.md](README.md)
- **API Examples**: [EXAMPLE_API.md](EXAMPLE_API.md)
- **Code Issues**: Check [README.md - Troubleshooting](README.md#troubleshooting)
- **Game Engine**: Review docstrings in `engine.py`

---

**Enjoy Royal 21!** 🎰♠️

Start with: `python main.py` → `http://localhost:8000`

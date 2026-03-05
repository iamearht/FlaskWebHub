# 🎰 Royal 21 - START HERE

Welcome! You've received a **complete, production-ready multiplayer poker×blackjack game**.

## 📦 What You Got

A full-stack web application with:

- **Backend**: Python FastAPI + WebSockets
- **Frontend**: Poker-inspired HTML/CSS/JavaScript
- **Game Engine**: Deterministic with full rule compliance
- **Tests**: 20+ unit tests covering all mechanics
- **Documentation**: 5 comprehensive guides

**Total**: ~3,700 lines of code + documentation

---

## ⚡ Quick Start (5 minutes)

### 1. Setup (1 minute)

**Linux/macOS:**
```bash
cd royal21-game
bash setup.sh
```

**Windows:**
```bash
cd royal21-game
setup.bat
```

### 2. Run Server (1 minute)

```bash
python main.py
```

You'll see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 3. Open Browser (1 minute)

```
http://localhost:8000
```

### 4. Create & Play Game (2 minutes)

1. Click "New Game" → Select 2-7 players → "Create"
2. Click "Start Game"
3. Make betting/drawing decisions
4. Watch results in showdown

**Done!** You're now playing Royal 21.

---

## 📚 Documentation Map

| Document | Purpose | Read Time |
|----------|---------|-----------|
| **[QUICKSTART.md](QUICKSTART.md)** | 5-min setup guide | 5 min |
| **[README.md](README.md)** | Complete rules & API | 20 min |
| **[GAME_FLOW.md](GAME_FLOW.md)** | Visual flow diagrams | 10 min |
| **[EXAMPLE_API.md](EXAMPLE_API.md)** | API usage examples | 10 min |
| **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** | Architecture & design | 15 min |
| **[REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md)** | Requirements verification | 5 min |

---

## 🎮 How the Game Works (30 seconds)

```
1. SETUP: Everyone posts antes/blinds
2. PREFLOP: Betting round + reveal a card
3. DRAW: Hit/stand/double/split (blackjack-style)
4. RIVER: Betting round (with restrictions)
5. SHOWDOWN: Evaluate hands → distribute pots
6. REPEAT: Move button, next hand
```

### Key Rules

- **2-7 players** (configurable)
- **Two chip circles**: Normal (main pot) + Escrow (side pot)
- **Two betting rounds**: Preflop + River
- **Blackjack hand totals**: Closest to 21 wins
- **Natural Blackjack**: A + 10-value = special ranking
- **Custom raise cap**: max = current_high + table_total
- **Escrow-lock**: Can't add escrow if you hit

[Full rules →](README.md)

---

## 🏗️ Project Structure

```
royal21-game/
├── QUICKSTART.md              ← START WITH THIS
├── README.md                  ← Full rules & API
├── 
├── Game Engine (Python)
│   ├── card.py                (Card/Deck classes)
│   ├── hand.py                (Hand ranking logic)
│   ├── game_state.py          (State management)
│   ├── engine.py              (Main game engine)
│   └── config.py              (Customizable rules)
│
├── Web Server (Python)
│   └── main.py                (FastAPI + WebSocket)
│
├── Frontend (Web)
│   └── frontend/
│       ├── index.html
│       ├── css/style.css
│       └── js/app.js
│
└── Testing & Docs
    ├── test_engine.py         (20+ tests)
    ├── setup.sh / setup.bat   (Auto-setup)
    └── GAME_FLOW.md           (Flow diagrams)
```

---

## ✅ Features

### Game Mechanics
- ✓ All official rules implemented
- ✓ Natural blackjack ranking
- ✓ Split hands (with half-pot logic)
- ✓ Escrow lock enforcement
- ✓ Custom pot-limit sizing
- ✓ Layered escrow settlement
- ✓ Auto-hand evaluation

### Code Quality
- ✓ 100% deterministic (seedable RNG)
- ✓ Type hints throughout
- ✓ Comprehensive docstrings
- ✓ Full test coverage
- ✓ Clean architecture
- ✓ Production-ready

### User Interface
- ✓ Poker-inspired dark theme
- ✓ Real-time WebSocket updates
- ✓ Clear seat/pot displays
- ✓ Action panel (contextual)
- ✓ Live action log
- ✓ Responsive design

---

## 🚀 Next Steps

### For Playing
1. Read [QUICKSTART.md](QUICKSTART.md) for setup
2. Play a game with friends
3. Check [README.md](README.md) for detailed rules

### For Development
1. Review [architecture](PROJECT_SUMMARY.md)
2. Run tests: `pytest test_engine.py -v`
3. Customize rules in [config.py](config.py)
4. Modify UI in [frontend/](frontend/)

### For Integration
1. See [EXAMPLE_API.md](EXAMPLE_API.md) for API usage
2. Add database storage (PostgreSQL/MySQL)
3. Add user authentication (JWT)
4. Deploy to production (Docker/Cloud)

---

## 🧪 Verification

All requirements have been implemented and tested:

```bash
# Run tests to verify
pytest test_engine.py -v

# Expected: All tests pass ✓
```

See [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) for full verification.

---

## 📖 Rules Summary

### Betting Rounds (Preflop & River)

**Two-step turns:**
1. Escrow Step: Add chips to escrow pot (optional)
2. Normal Betting Step: Fold/Check/Bet/Call/Raise

**Max raise formula:**
```
max_raise_to = current_highest_bet + TABLE_TOTAL
```

### Draw Phase

Choose: Stand / Hit / Double / Split

**Special rules:**
- Natural blackjack must stand
- Hit sets "escrow-lock" (can't add escrow on river)
- Double doesn't lock escrow
- Split creates two separate hands

### Showdown

**Hand ranking:**
1. Natural Blackjack (A + 10-value)
2. 21
3. 20
4. ... down to lowest non-bust
5. Bust (loses)

**Tiebreaker for blackjacks:**
- K > Q > J > 10
- Suited beats offsuit
- Same rank = split pot

---

## 🎯 Common Questions

**Q: Can I customize the rules?**
A: Yes! Edit [config.py](config.py) to adjust starting stacks, allow re-splits, etc.

**Q: How do I add players?**
A: Game creation dialog (default 7 seats, choose 2-7).

**Q: Can I save games?**
A: Currently in-memory. Add database integration for persistence.

**Q: Is it deterministic?**
A: Yes! Same seed = identical game flow. Great for testing/debugging.

**Q: How do I deploy?**
A: See "Production" section in [README.md](README.md).

---

## 🔗 Quick Links

- **Play the game**: `python main.py` → `http://localhost:8000`
- **Read rules**: [README.md](README.md)
- **Setup help**: [QUICKSTART.md](QUICKSTART.md)
- **API docs**: [EXAMPLE_API.md](EXAMPLE_API.md)
- **Code overview**: [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)
- **Architecture**: [GAME_FLOW.md](GAME_FLOW.md)
- **Requirements**: [REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md)

---

## 🎮 Ready to Play?

```bash
# 1. Setup
bash setup.sh  # (or setup.bat on Windows)

# 2. Run
python main.py

# 3. Play
# Open http://localhost:8000 in your browser
```

Enjoy! 🎰

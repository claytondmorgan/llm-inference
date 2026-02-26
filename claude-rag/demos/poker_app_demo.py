#!/usr/bin/env python3
"""Live demo: Simulated Claude Code session building a poker app.

Simulates a realistic multi-turn conversation where a user asks Claude Code
to build a Texas Hold'em poker app.  Each turn generates a CLAUDE.md-style
memory file that is ingested into the RAG pipeline.  At the end, the demo
runs hybrid search queries to show how RAG retrieves relevant context.

Usage:
    cd claude-rag
    PGPASSWORD=postgres PYTHONPATH=src python demos/poker_app_demo.py
"""

from __future__ import annotations

import atexit
import io
import logging
import sys
import time
import textwrap
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Suppress noisy third-party loggers that cause shutdown errors
# (huggingface_hub/httpcore try to log after stderr is closed)
for _logger_name in (
    "httpcore", "httpx", "huggingface_hub", "transformers",
    "sentence_transformers", "torch", "urllib3",
):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def _quiet_shutdown() -> None:
    """Disable all logging before interpreter shutdown to avoid I/O errors."""
    logging.disable(logging.CRITICAL)


atexit.register(_quiet_shutdown)

# ---------------------------------------------------------------------------
# Path setup — ensure our src/ is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from claude_rag.config import Config
from claude_rag.db.manager import DatabaseManager
from claude_rag.embeddings.local import LocalEmbeddingProvider
from claude_rag.ingestion.pipeline import IngestionPipeline
from claude_rag.search.hybrid import hybrid_search, build_filters
from claude_rag.search.formatter import format_context, deduplicate_results

# ---------------------------------------------------------------------------
# Terminal formatting helpers
# ---------------------------------------------------------------------------

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

DIVIDER = f"{DIM}{'─' * 78}{RESET}"


def banner(text: str) -> None:
    print(f"\n{BOLD}{MAGENTA}{'═' * 78}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * 78}{RESET}\n")


def phase_header(phase: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}[Phase {phase}] {title}{RESET}")
    print(DIVIDER)


def user_prompt(text: str) -> None:
    print(f"\n  {BOLD}{GREEN}> User:{RESET}  {text}")


def claude_response(text: str) -> None:
    wrapped = textwrap.fill(text, width=72, initial_indent="           ",
                            subsequent_indent="           ")
    print(f"  {BOLD}{YELLOW}Claude:{RESET}{wrapped[10:]}")


def agent_action(text: str) -> None:
    print(f"  {DIM}  [agent] {text}{RESET}")


def system_note(text: str) -> None:
    print(f"  {DIM}{text}{RESET}")


def search_header(query: str) -> None:
    print(f"\n  {BOLD}{RED}RAG Search:{RESET} \"{query}\"")
    print(f"  {DIM}{'─' * 60}{RESET}")


# ---------------------------------------------------------------------------
# Simulated conversation turns
# ---------------------------------------------------------------------------

CONVERSATION: list[dict] = [
    # ── Turn 1: User kicks off the project ──────────────────────────
    {
        "turn": 1,
        "user": "I want to build a multiplayer Texas Hold'em poker app. It should support 2-8 players, have a lobby system, and real-time gameplay with WebSockets.",
        "claude": (
            "Great project! Let me ask a few questions to nail down the architecture. "
            "What tech stack are you thinking — web-based or native? "
            "And do you want real money or play-money chips?"
        ),
        "memory_file": "CLAUDE_poker_t1.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Project Kickoff

            ## User Requirements
            - Build a multiplayer Texas Hold'em poker app
            - Support 2-8 players per table
            - Lobby system for finding and creating tables
            - Real-time gameplay using WebSockets
            - Need to clarify: web vs native, real vs play money

            ## Architecture Decisions (Pending)
            - Stack TBD — user needs to confirm frontend/backend preferences
            - Real-time communication confirmed: WebSockets
            - Player count: 2-8 per table

            ## Open Questions
            - Use React/Next.js or mobile-native (Flutter/React Native)?
            - Play money only, or real currency with payment processing?
            - Authentication provider preference (OAuth, email/password)?
            - Deployment target (AWS, Vercel, self-hosted)?
        """),
    },
    # ── Turn 2: User answers architecture questions ─────────────────
    {
        "turn": 2,
        "user": "Let's go with React + Next.js frontend and Python FastAPI backend. Play money only. Use PostgreSQL for the database and Redis for pub/sub. Deploy on AWS with Docker.",
        "claude": (
            "Perfect — a solid modern stack. I'll scaffold the project with a monorepo: "
            "frontend/ for Next.js, backend/ for FastAPI, and shared types. "
            "Let me set up the initial structure."
        ),
        "memory_file": "CLAUDE_poker_t2.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Architecture Decisions

            ## Confirmed Stack
            - **Frontend**: React + Next.js (TypeScript)
            - **Backend**: Python FastAPI with async support
            - **Database**: PostgreSQL (player accounts, game history, leaderboards)
            - **Cache/PubSub**: Redis (real-time game state, WebSocket pub/sub)
            - **Real-time**: WebSockets via FastAPI + Redis pub/sub fan-out
            - **Deployment**: AWS with Docker containers (ECS or EKS)
            - **Currency**: Play money only — no payment processing needed

            ## Project Structure
            ```
            poker-app/
            ├── frontend/          # Next.js React app
            │   ├── src/
            │   │   ├── components/  # UI components (Table, Cards, Lobby)
            │   │   ├── hooks/       # WebSocket hooks, game state
            │   │   └── pages/       # Next.js routes
            │   └── package.json
            ├── backend/           # FastAPI Python server
            │   ├── app/
            │   │   ├── api/         # REST endpoints
            │   │   ├── ws/          # WebSocket handlers
            │   │   ├── game/        # Game engine (deck, hand eval, betting)
            │   │   ├── models/      # SQLAlchemy ORM models
            │   │   └── config.py
            │   └── pyproject.toml
            ├── docker-compose.yml
            └── README.md
            ```

            ## Key Design Decisions
            - Use SQLAlchemy async ORM for database operations
            - Redis pub/sub channels per table: `table:{table_id}:events`
            - JWT authentication with refresh tokens
            - Game state machine managed server-side to prevent cheating
        """),
    },
    # ── Turn 3: Building the game engine ────────────────────────────
    {
        "turn": 3,
        "user": "Start with the game engine — I need a deck, hand evaluator, and the betting round logic. Make sure the hand evaluator handles all standard rankings from high card to royal flush.",
        "claude": (
            "I'll build the game engine module in backend/app/game/. Starting with "
            "three core files: deck.py for card representation and shuffling, "
            "evaluator.py for hand ranking, and betting.py for round management. "
            "Let me write the hand evaluator first since it's the most complex piece."
        ),
        "memory_file": "CLAUDE_poker_t3.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Game Engine Implementation

            ## Hand Evaluator — backend/app/game/evaluator.py
            Implemented a Texas Hold'em hand evaluator supporting all 10 standard rankings:
            1. Royal Flush
            2. Straight Flush
            3. Four of a Kind
            4. Full House
            5. Flush
            6. Straight
            7. Three of a Kind
            8. Two Pair
            9. One Pair
            10. High Card

            ```python
            from enum import IntEnum
            from itertools import combinations
            from collections import Counter

            class HandRank(IntEnum):
                HIGH_CARD = 1
                ONE_PAIR = 2
                TWO_PAIR = 3
                THREE_OF_A_KIND = 4
                STRAIGHT = 5
                FLUSH = 6
                FULL_HOUSE = 7
                FOUR_OF_A_KIND = 8
                STRAIGHT_FLUSH = 9
                ROYAL_FLUSH = 10

            class Card:
                RANKS = '23456789TJQKA'
                SUITS = 'shdc'
                def __init__(self, rank: int, suit: int):
                    self.rank = rank  # 2-14 (Ace=14)
                    self.suit = suit  # 0-3

            def evaluate_hand(cards: list[Card]) -> tuple[HandRank, list[int]]:
                \"\"\"Evaluate best 5-card hand from 7 cards. Returns (rank, tiebreakers).\"\"\"
                best = None
                for combo in combinations(cards, 5):
                    score = _score_five(list(combo))
                    if best is None or score > best:
                        best = score
                return best
            ```

            ## Deck — backend/app/game/deck.py
            - Uses `secrets.SystemRandom()` for cryptographically secure shuffling
            - 52-card standard deck with Card dataclass
            - `deal(n)` method returns n cards and removes from deck

            ## Betting Rounds — backend/app/game/betting.py
            - State machine: PREFLOP → FLOP → TURN → RIVER → SHOWDOWN
            - Actions: fold, check, call, raise, all-in
            - Tracks pot, side pots for all-in scenarios
            - Enforces minimum raise rules (must raise >= previous raise amount)
            - Big blind / small blind rotation with dealer button

            ## Bug Fix
            Fixed edge case where Ace-low straight (A-2-3-4-5 / "wheel") was not
            detected because the evaluator only checked for consecutive ranks
            without handling Ace wrapping to rank 1.

            ## Testing
            - Use pytest for unit tests in tests/test_evaluator.py
            - Always test edge cases: wheel straight, split pots, kicker comparison
            - Run with: `cd backend && python -m pytest tests/ -v`
        """),
    },
    # ── Turn 4: WebSocket and lobby ─────────────────────────────────
    {
        "turn": 4,
        "user": "Now build the WebSocket layer and the lobby system. Players need to see available tables, create new ones, and join games. Use Redis pub/sub to broadcast game events.",
        "claude": (
            "Building the real-time layer. I'll create a WebSocket manager that handles "
            "connection lifecycle, Redis pub/sub integration for cross-instance broadcasting, "
            "and the lobby REST + WebSocket endpoints. Each table gets its own Redis channel."
        ),
        "memory_file": "CLAUDE_poker_t4.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — WebSocket & Lobby System

            ## WebSocket Architecture — backend/app/ws/
            Implemented a connection manager pattern for handling WebSocket lifecycle:

            ```python
            import asyncio
            import json
            from fastapi import WebSocket
            import redis.asyncio as aioredis

            class ConnectionManager:
                def __init__(self, redis_url: str = "redis://localhost:6379"):
                    self._connections: dict[str, dict[str, WebSocket]] = {}
                    self._redis = aioredis.from_url(redis_url)

                async def connect(self, table_id: str, player_id: str, ws: WebSocket):
                    await ws.accept()
                    self._connections.setdefault(table_id, {})[player_id] = ws
                    await self._subscribe(table_id)

                async def broadcast(self, table_id: str, event: dict):
                    message = json.dumps(event)
                    await self._redis.publish(f"table:{table_id}:events", message)

                async def _subscribe(self, table_id: str):
                    pubsub = self._redis.pubsub()
                    await pubsub.subscribe(f"table:{table_id}:events")
                    asyncio.create_task(self._listener(table_id, pubsub))
            ```

            ## Game Events Protocol
            All events follow a standard schema:
            - `type`: Event type string
            - `data`: Event-specific payload
            - `timestamp`: ISO 8601 timestamp

            Event types:
            - `player_joined` / `player_left`
            - `game_started` / `game_ended`
            - `cards_dealt` (private — sent only to target player)
            - `community_cards` (public — broadcast to all)
            - `player_action` (fold, check, call, raise)
            - `pot_updated`
            - `showdown_result`
            - `turn_timer` (15-second countdown)

            ## Lobby System — backend/app/api/lobby.py
            REST endpoints for table management:
            - `GET  /api/lobby/tables` — list active tables with player counts
            - `POST /api/lobby/tables` — create new table (params: name, max_players, blinds)
            - `POST /api/lobby/tables/{id}/join` — join a table (returns WebSocket URL)
            - `DELETE /api/lobby/tables/{id}` — close table (owner only)

            ## Redis Channel Design
            - `lobby:updates` — broadcast table creation/deletion to lobby viewers
            - `table:{id}:events` — per-table game events
            - `table:{id}:state` — cached game state (JSON) for reconnection

            ## Configuration — backend/app/config.py
            - `REDIS_URL=redis://localhost:6379`
            - `WS_HEARTBEAT_INTERVAL=30` (seconds)
            - `TURN_TIMER=15` (seconds per action)
            - `MAX_TABLES=100`
        """),
    },
    # ── Turn 5: Frontend and React components ───────────────────────
    {
        "turn": 5,
        "user": "Build the frontend React components — I need the poker table view with card animations, the lobby page, and a player HUD showing chips and actions. Use Tailwind CSS for styling.",
        "claude": (
            "I'll build the core UI components: PokerTable with seat positions, "
            "Card with flip animations, PlayerHUD with action buttons, and the "
            "Lobby page with table list. Using Tailwind CSS and Framer Motion for "
            "smooth card dealing animations."
        ),
        "memory_file": "CLAUDE_poker_t5.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Frontend Implementation

            ## Component Architecture — frontend/src/components/

            ### PokerTable — components/table/PokerTable.tsx
            - Renders an oval table with 8 seat positions using absolute positioning
            - Seats arranged in elliptical pattern using CSS transforms
            - Community cards centered on table with staggered deal animation
            - Pot display in center with animated chip count

            ### Card — components/cards/Card.tsx
            ```typescript
            interface CardProps {
              rank: string;   // '2'-'A'
              suit: 'h' | 'd' | 'c' | 's';
              faceUp: boolean;
              animate?: 'deal' | 'flip' | 'none';
            }

            export function Card({ rank, suit, faceUp, animate = 'none' }: CardProps) {
              return (
                <motion.div
                  className="w-16 h-24 rounded-lg shadow-xl"
                  initial={animate === 'deal' ? { y: -200, opacity: 0 } : {}}
                  animate={{ y: 0, opacity: 1, rotateY: faceUp ? 0 : 180 }}
                  transition={{ duration: 0.4, ease: 'easeOut' }}
                >
                  {faceUp ? <CardFace rank={rank} suit={suit} /> : <CardBack />}
                </motion.div>
              );
            }
            ```

            ### PlayerHUD — components/player/PlayerHUD.tsx
            - Displays: avatar, username, chip count, current bet, timer bar
            - Action buttons: Fold, Check, Call ($X), Raise (slider), All-In
            - Raise slider with min/max bounds and preset buttons (2x, 3x, pot)
            - Disabled state when not player's turn
            - Timer bar with 15-second countdown (red warning under 5s)

            ### Lobby — pages/lobby.tsx
            - Table list with columns: name, players, blinds, avg stack
            - Create Table modal with form validation
            - Auto-refresh via WebSocket subscription to `lobby:updates`
            - Quick-join button for tables with open seats

            ## Styling
            - Tailwind CSS with custom poker-green theme: `bg-emerald-800`
            - Card faces use Unicode suit symbols with red/black coloring
            - Responsive layout — works on desktop and tablet

            ## WebSocket Hook — hooks/usePokerSocket.ts
            ```typescript
            export function usePokerSocket(tableId: string) {
              const [gameState, setGameState] = useState<GameState | null>(null);
              const ws = useRef<WebSocket | null>(null);

              useEffect(() => {
                ws.current = new WebSocket(
                  `${process.env.NEXT_PUBLIC_WS_URL}/ws/table/${tableId}`
                );
                ws.current.onmessage = (event) => {
                  const msg = JSON.parse(event.data);
                  setGameState(prev => applyEvent(prev, msg));
                };
                return () => ws.current?.close();
              }, [tableId]);

              const sendAction = (action: PlayerAction) => {
                ws.current?.send(JSON.stringify(action));
              };

              return { gameState, sendAction };
            }
            ```

            ## Dependencies Added
            - `framer-motion` — card deal/flip animations
            - `@headlessui/react` — accessible modals and dropdowns
            - `tailwindcss` — utility-first CSS framework
            - `zustand` — lightweight state management for game state
        """),
    },
    # ── Turn 6: Database schema and auth ────────────────────────────
    {
        "turn": 6,
        "user": "Set up the database schema for players, games, and hand history. Add JWT authentication with bcrypt password hashing. I want a leaderboard based on total winnings.",
        "claude": (
            "I'll create the SQLAlchemy models and Alembic migrations for the full "
            "data model. For auth, I'll use python-jose for JWT tokens and passlib "
            "with bcrypt for password hashing. The leaderboard query will use a "
            "materialized view for performance."
        ),
        "memory_file": "CLAUDE_poker_t6.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Database & Authentication

            ## Database Schema — backend/app/models/

            ### Players Table
            ```sql
            CREATE TABLE players (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                chips BIGINT DEFAULT 10000,
                games_played INTEGER DEFAULT 0,
                total_winnings BIGINT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                last_login TIMESTAMPTZ
            );
            CREATE INDEX idx_players_username ON players(username);
            CREATE INDEX idx_players_winnings ON players(total_winnings DESC);
            ```

            ### Games Table
            ```sql
            CREATE TABLE games (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                table_name VARCHAR(100) NOT NULL,
                small_blind INTEGER NOT NULL,
                big_blind INTEGER NOT NULL,
                max_players INTEGER DEFAULT 8,
                status VARCHAR(20) DEFAULT 'waiting',  -- waiting/active/finished
                created_at TIMESTAMPTZ DEFAULT NOW(),
                finished_at TIMESTAMPTZ
            );
            ```

            ### Hand History
            ```sql
            CREATE TABLE hand_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                game_id UUID REFERENCES games(id),
                hand_number INTEGER NOT NULL,
                community_cards VARCHAR(20),
                pot_total BIGINT,
                winner_id UUID REFERENCES players(id),
                winning_hand VARCHAR(50),
                played_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE hand_actions (
                id SERIAL PRIMARY KEY,
                hand_id UUID REFERENCES hand_history(id),
                player_id UUID REFERENCES players(id),
                action VARCHAR(20) NOT NULL,  -- fold/check/call/raise/all-in
                amount BIGINT DEFAULT 0,
                round VARCHAR(10) NOT NULL,    -- preflop/flop/turn/river
                sequence INTEGER NOT NULL
            );
            ```

            ### Leaderboard Materialized View
            ```sql
            CREATE MATERIALIZED VIEW leaderboard AS
            SELECT
                p.id, p.username, p.chips, p.total_winnings,
                p.games_played,
                RANK() OVER (ORDER BY p.total_winnings DESC) as rank
            FROM players p
            WHERE p.games_played > 0
            ORDER BY p.total_winnings DESC;

            CREATE UNIQUE INDEX idx_leaderboard_id ON leaderboard(id);
            ```
            - Refresh with: `REFRESH MATERIALIZED VIEW CONCURRENTLY leaderboard;`

            ## Authentication — backend/app/auth/
            - **Password hashing**: passlib with bcrypt (12 rounds)
            - **JWT tokens**: python-jose with HS256, 30-min access + 7-day refresh
            - **Endpoints**:
              - `POST /api/auth/register` — create account (username, email, password)
              - `POST /api/auth/login` — returns access + refresh tokens
              - `POST /api/auth/refresh` — rotate refresh token
            - **Middleware**: `get_current_user` dependency extracts player from JWT

            ## Configuration
            - `SECRET_KEY` — JWT signing key (from env var, never hardcoded)
            - `ACCESS_TOKEN_EXPIRE_MINUTES=30`
            - `REFRESH_TOKEN_EXPIRE_DAYS=7`
            - `INITIAL_CHIPS=10000` — starting chips for new players
            - Never store SECRET_KEY in code or version control
        """),
    },
    # ── Turn 7: Bug fix + testing ───────────────────────────────────
    {
        "turn": 7,
        "user": "I found a bug — when two players go all-in with different stack sizes, the side pot calculation is wrong. The smaller stack player should only be eligible for the main pot. Also add comprehensive tests for the game engine.",
        "claude": (
            "Found the issue — the pot manager was treating all-in bets as regular bets "
            "instead of capping each player's contribution. I'll fix the side pot logic "
            "and add exhaustive tests for multi-way all-in scenarios."
        ),
        "memory_file": "CLAUDE_poker_t7.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Side Pot Bug Fix & Testing

            ## Bug Report
            When two players go all-in with different stack sizes, the side pot
            calculation was incorrect. Player with smaller stack was being made
            eligible for the full pot instead of only the main pot.

            ## Root Cause — backend/app/game/betting.py
            The `PotManager.calculate_pots()` method was not sorting all-in
            amounts and iterating to create layered side pots.

            ## Fix Applied
            ```python
            def calculate_pots(self) -> list[Pot]:
                \"\"\"Calculate main pot and side pots for all-in scenarios.\"\"\"
                all_in_amounts = sorted(set(
                    p.total_bet for p in self.players if p.is_all_in
                ))

                pots = []
                prev_level = 0
                remaining_players = [p for p in self.players if not p.has_folded]

                for level in all_in_amounts:
                    increment = level - prev_level
                    pot_amount = sum(
                        min(p.total_bet - prev_level, increment)
                        for p in remaining_players
                        if p.total_bet > prev_level
                    )
                    eligible = [p for p in remaining_players if p.total_bet >= level]
                    pots.append(Pot(amount=pot_amount, eligible_players=eligible))
                    remaining_players = [p for p in remaining_players if p.total_bet > level]
                    prev_level = level

                # Remaining bets go to final side pot
                if remaining_players:
                    final = sum(p.total_bet - prev_level for p in remaining_players)
                    if final > 0:
                        pots.append(Pot(amount=final, eligible_players=remaining_players))

                return pots
            ```

            ## Test Coverage Added — backend/tests/test_game_engine.py
            - `test_side_pot_two_players_different_stacks` — verifies main pot and side pot
            - `test_side_pot_three_players_all_in` — three-way split with cascading pots
            - `test_hand_eval_royal_flush` — strongest hand
            - `test_hand_eval_wheel_straight` — A-2-3-4-5 edge case
            - `test_hand_eval_kicker_comparison` — same pair, different kicker
            - `test_betting_round_flow` — preflop → flop → turn → river
            - `test_fold_ends_hand_for_player` — folded player excluded from pot
            - `test_all_in_caps_bet` — player can't bet more than their stack

            ## Lessons Learned
            - Always sort all-in amounts when calculating side pots
            - Side pot eligibility must cap at each player's maximum contribution
            - Test multi-way all-in scenarios (3+ players) — edge cases multiply
            - Run tests with: `cd backend && python -m pytest tests/test_game_engine.py -v`
        """),
    },
    # ── Turn 8: Deployment & CI/CD ──────────────────────────────────
    {
        "turn": 8,
        "user": "Finally, set up Docker Compose for local dev, write the Dockerfile for the backend, and create a GitHub Actions CI pipeline that runs tests on every PR.",
        "claude": (
            "Setting up the full deployment pipeline. Docker Compose will orchestrate "
            "the backend, frontend, PostgreSQL, and Redis. The CI pipeline will lint, "
            "test, and build Docker images on every push."
        ),
        "memory_file": "CLAUDE_poker_t8.md",
        "memory_content": textwrap.dedent("""\
            # Poker App — Deployment & CI/CD

            ## Docker Compose — docker-compose.yml
            ```yaml
            version: '3.8'
            services:
              backend:
                build: ./backend
                ports: ["8000:8000"]
                env_file: .env
                depends_on: [postgres, redis]

              frontend:
                build: ./frontend
                ports: ["3000:3000"]
                env_file: .env
                depends_on: [backend]

              postgres:
                image: postgres:16
                environment:
                  POSTGRES_DB: poker_db
                  POSTGRES_USER: poker
                  POSTGRES_PASSWORD: ${DB_PASSWORD}
                volumes: ["pgdata:/var/lib/postgresql/data"]
                ports: ["5432:5432"]

              redis:
                image: redis:7-alpine
                ports: ["6379:6379"]

            volumes:
              pgdata:
            ```

            ## Backend Dockerfile — backend/Dockerfile
            ```dockerfile
            FROM python:3.12-slim
            WORKDIR /app
            COPY pyproject.toml .
            RUN pip install --no-cache-dir -e .
            COPY app/ app/
            EXPOSE 8000
            CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
            ```

            ## GitHub Actions CI — .github/workflows/ci.yml
            ```yaml
            name: CI
            on: [push, pull_request]
            jobs:
              test-backend:
                runs-on: ubuntu-latest
                services:
                  postgres:
                    image: postgres:16
                    env:
                      POSTGRES_DB: test_db
                      POSTGRES_PASSWORD: test
                    ports: ["5432:5432"]
                  redis:
                    image: redis:7-alpine
                    ports: ["6379:6379"]
                steps:
                  - uses: actions/checkout@v4
                  - uses: actions/setup-python@v5
                    with: { python-version: '3.12' }
                  - run: cd backend && pip install -e ".[dev]"
                  - run: cd backend && python -m pytest tests/ -v --cov=app

              test-frontend:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - uses: actions/setup-node@v4
                    with: { node-version: '20' }
                  - run: cd frontend && npm ci && npm test

              lint:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - run: cd backend && pip install ruff && ruff check app/
                  - run: cd frontend && npm ci && npm run lint
            ```

            ## Environment Variables (.env.example)
            ```
            # Database
            DB_PASSWORD=your_secure_password
            DATABASE_URL=postgresql://poker:${DB_PASSWORD}@postgres:5432/poker_db

            # Redis
            REDIS_URL=redis://redis:6379

            # Auth
            SECRET_KEY=generate-a-random-key-here
            ACCESS_TOKEN_EXPIRE_MINUTES=30

            # Frontend
            NEXT_PUBLIC_API_URL=http://localhost:8000
            NEXT_PUBLIC_WS_URL=ws://localhost:8000
            ```
            - Never commit .env files — only .env.example with placeholder values
            - Use `openssl rand -hex 32` to generate SECRET_KEY

            ## Deployment Notes
            - AWS ECS Fargate for production containers
            - RDS PostgreSQL for managed database
            - ElastiCache Redis for managed pub/sub
            - CloudFront CDN for frontend static assets
            - Use ALB with WebSocket sticky sessions enabled
        """),
    },
]


# ---------------------------------------------------------------------------
# Demo queries to run after ingestion
# ---------------------------------------------------------------------------

RAG_QUERIES: list[dict] = [
    {
        "query": "How does the hand evaluator work and what rankings does it support?",
        "description": "Retrieve game engine implementation details",
    },
    {
        "query": "WebSocket architecture and Redis pub/sub channel design",
        "description": "Find real-time communication patterns",
    },
    {
        "query": "side pot bug fix all-in calculation",
        "description": "Locate the bug fix and its solution",
    },
    {
        "query": "database schema players authentication JWT",
        "description": "Retrieve auth and data model decisions",
    },
    {
        "query": "React components poker table Card animation Tailwind",
        "description": "Find frontend implementation details",
    },
    {
        "query": "Docker deployment CI/CD GitHub Actions",
        "description": "Retrieve deployment configuration",
    },
]


# ---------------------------------------------------------------------------
# Main demo runner
# ---------------------------------------------------------------------------

def run_demo() -> None:
    """Execute the full live demo."""

    banner("CLAUDE CODE RAG DEMO — Building a Poker App")

    print(f"  This demo simulates a multi-turn Claude Code session where a user")
    print(f"  builds a Texas Hold'em poker app. Each turn generates a memory file")
    print(f"  that is ingested into the RAG pipeline. At the end, hybrid search")
    print(f"  queries demonstrate context retrieval.\n")

    # ── Setup ───────────────────────────────────────────────────────
    phase_header(0, "Initializing RAG Pipeline")

    config = Config()
    config.PGPASSWORD = "postgres"

    db = DatabaseManager(config)
    assert db.test_connection(), "Database connection failed — is Docker running?"
    system_note("Database connection OK")

    embedder = LocalEmbeddingProvider()
    system_note(f"Embedding model loaded (dim={embedder.dimension})")

    pipeline = IngestionPipeline(config=config, embedding_provider=embedder, db=db)
    system_note("Pipeline ready\n")

    # Track source IDs for cleanup
    source_ids: list[int] = []

    # Staging directory for memory files
    staging_dir = Path(__file__).resolve().parent / "_demo_staging"
    staging_dir.mkdir(exist_ok=True)

    try:
        # ── Simulated Conversation ──────────────────────────────────
        phase_header(1, "Simulated Claude Code Session (8 turns)")

        for turn in CONVERSATION:
            t_num = turn["turn"]
            print(f"\n  {BOLD}── Turn {t_num} of {len(CONVERSATION)} ──{RESET}")
            user_prompt(turn["user"])
            claude_response(turn["claude"])

            # Write memory file
            mem_path = staging_dir / turn["memory_file"]
            mem_path.write_text(turn["memory_content"], encoding="utf-8")
            agent_action(f"Writing memory → {turn['memory_file']}")

            # Ingest into pipeline
            t0 = time.perf_counter()
            result = pipeline.ingest_file(str(mem_path))
            elapsed = (time.perf_counter() - t0) * 1000

            source_ids.append(result.source_id)
            agent_action(
                f"Ingested: {result.chunks_created} chunks, "
                f"{elapsed:.0f}ms (source_id={result.source_id})"
            )

        # ── Summary Stats ───────────────────────────────────────────
        phase_header(2, "Ingestion Summary")

        total_chunks = db.get_chunk_count()
        total_sources = db.get_source_count()
        print(f"  Total sources in DB:  {BOLD}{total_sources}{RESET}")
        print(f"  Total chunks in DB:   {BOLD}{total_chunks}{RESET}")

        # Count chunks per turn
        conn = db._get_connection()
        cur = conn.cursor()
        for sid in source_ids:
            cur.execute(
                "SELECT COUNT(*), ms.file_path FROM memory_chunks mc "
                "JOIN memory_sources ms ON ms.id = mc.source_id "
                "WHERE mc.source_id = %s GROUP BY ms.file_path",
                (sid,),
            )
            row = cur.fetchone()
            if row:
                fname = Path(row[1]).name
                print(f"    {DIM}{fname}: {row[0]} chunks{RESET}")
        cur.close()
        conn.close()

        # ── RAG Search Queries ──────────────────────────────────────
        phase_header(3, "Hybrid RAG Search Queries")

        print(f"  Running {len(RAG_QUERIES)} search queries to demonstrate retrieval...\n")

        conn = db._get_connection()
        try:
            for i, q in enumerate(RAG_QUERIES, 1):
                print(f"  {BOLD}Query {i}/{len(RAG_QUERIES)}:{RESET} {q['description']}")
                search_header(q["query"])

                # Embed the query
                query_embedding = embedder.embed_single(q["query"])

                # Run hybrid search
                results = hybrid_search(
                    query_embedding=query_embedding,
                    query_text=q["query"],
                    top_k=5,
                    db_conn=conn,
                    rrf_k=config.RRF_K,
                )

                # Filter and deduplicate
                results = [r for r in results if r.similarity >= config.RELEVANCE_THRESHOLD]
                results = deduplicate_results(results)

                if not results:
                    print(f"    {DIM}No results found.{RESET}")
                    continue

                # Display results
                for j, r in enumerate(results[:3], 1):
                    source = Path(r.source_path).name if r.source_path else "unknown"
                    method_color = GREEN if r.search_method == "hybrid" else YELLOW
                    print(
                        f"    {BOLD}{j}.{RESET} [{method_color}{r.search_method}{RESET}] "
                        f"score={r.similarity:.4f}  source={DIM}{source}{RESET}  "
                        f"type={r.block_type or '?'}"
                    )
                    # Show first 120 chars of content
                    preview = r.content.replace("\n", " ")[:120].strip()
                    print(f"       {DIM}\"{preview}...\" {RESET}")

                    # Show enriched metadata
                    meta_parts = []
                    if r.metadata.get("language"):
                        meta_parts.append(f"lang={r.metadata['language']}")
                    if r.metadata.get("intent"):
                        meta_parts.append(f"intent={r.metadata['intent']}")
                    if r.metadata.get("files"):
                        meta_parts.append(f"files={r.metadata['files'][:2]}")
                    if meta_parts:
                        print(f"       {DIM}metadata: {', '.join(meta_parts)}{RESET}")

                print()

        finally:
            conn.close()

        # ── RAG Context Assembly ────────────────────────────────────
        phase_header(4, "RAG Context Assembly (what Claude would receive)")

        demo_query = "I need to understand the poker game engine, hand evaluation, and side pot logic to fix a new bug"
        print(f"  Simulating an MCP rag_search call for a follow-up task:")
        print(f"  {BOLD}\"{demo_query}\"{RESET}\n")

        query_embedding = embedder.embed_single(demo_query)
        conn = db._get_connection()
        try:
            results = hybrid_search(
                query_embedding=query_embedding,
                query_text=demo_query,
                top_k=10,
                db_conn=conn,
                rrf_k=config.RRF_K,
            )
            results = [r for r in results if r.similarity >= config.RELEVANCE_THRESHOLD]
            results = deduplicate_results(results)

            context = format_context(results, token_budget=2048)
        finally:
            conn.close()

        print(f"  {BOLD}Formatted RAG context ({len(results)} results, budget=2048 tokens):{RESET}")
        print(f"  {DIM}{'─' * 60}{RESET}")
        # Print context with indentation
        for line in context.split("\n"):
            print(f"  {line}")
        print(f"  {DIM}{'─' * 60}{RESET}")

        # ── Filtered Search Demo ────────────────────────────────────
        phase_header(5, "Filtered Search (metadata-enriched queries)")

        conn = db._get_connection()
        try:
            # Search only code blocks
            print(f"  {BOLD}Filter: block_type='code'{RESET}")
            clause, params = build_filters(block_type_filter="code")
            query_embedding = embedder.embed_single("poker hand evaluation")
            results = hybrid_search(
                query_embedding=query_embedding,
                query_text="poker hand evaluation",
                top_k=5,
                db_conn=conn,
                rrf_k=config.RRF_K,
                filter_clause=clause,
                filter_params=params,
            )
            print(f"    Found {len(results)} code chunks")
            for r in results[:3]:
                lang = r.metadata.get("language", "?")
                preview = r.content.replace("\n", " ")[:80]
                print(f"    {DIM}[{lang}] {preview}...{RESET}")

            print()

            # Search for bug-fix intent
            print(f"  {BOLD}Filter: intent='bug-fix'{RESET}")
            clause, params = build_filters(intent_filter="bug-fix")
            query_embedding = embedder.embed_single("bug fix")
            results = hybrid_search(
                query_embedding=query_embedding,
                query_text="bug fix",
                top_k=5,
                db_conn=conn,
                rrf_k=config.RRF_K,
                filter_clause=clause,
                filter_params=params,
            )
            print(f"    Found {len(results)} bug-fix chunks")
            for r in results[:3]:
                preview = r.content.replace("\n", " ")[:100]
                print(f"    {DIM}\"{preview}...\" {RESET}")

        finally:
            conn.close()

        # ── Done ────────────────────────────────────────────────────
        banner("DEMO COMPLETE")
        print(f"  The poker app conversation generated {len(CONVERSATION)} memory files")
        print(f"  containing {db.get_chunk_count()} searchable chunks in PostgreSQL.")
        print(f"  Hybrid RRF search combines semantic + keyword matching to retrieve")
        print(f"  the most relevant context for any follow-up query.\n")
        print(f"  In production, the MCP server exposes this as the `rag_search` tool")
        print(f"  that Claude Code calls automatically before every task.\n")

    finally:
        # ── Cleanup ─────────────────────────────────────────────────
        system_note("Cleaning up demo data...")
        for sid in source_ids:
            try:
                db.delete_source(sid)
            except Exception:
                pass

        # Remove staging files
        for f in staging_dir.glob("CLAUDE_poker_*.md"):
            f.unlink()
        try:
            staging_dir.rmdir()
        except OSError:
            pass

        system_note("Cleanup complete — demo data removed from database.")


if __name__ == "__main__":
    run_demo()

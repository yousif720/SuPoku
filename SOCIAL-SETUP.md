# Accounts and community

Run `python server.py 8765` and open `http://localhost:8765/`. No third-party account is needed for local username/password login. The Friends & scores button opens the community notebook.

Implemented: register, sign in/out, persistent daily progress, one-way friends by username, private game history, public score statistics, current/best winning streaks, 12-week activity calendar, spoiler-free result copying, daily/friends/personal-best/streak leaderboards, account deletion, and JSON APIs. Like the inspected Typedle implementation, friends are followed without requests or messages. Google/Discord sign-in and email recovery are not configured.

## Ranked rules

Sign in before playing to start/resume the account's daily grid. Guest games are not imported. Each account gets one ranked game per UTC day. Random games are unranked. The server owns the categories, validates Pokémon and duplicates, counts guesses and retries, enforces one undo and locks the final result before revealing answers. Every filled square earns 100 points; every wrong guess deducts 10 (including the free retry), down to zero. Undo refunds guesses but never erases wrong-guess penalties. A 9/9 result is a win; consecutive winning UTC dates form a streak. Personal best ranks each player's highest individual result. Tied point totals share a rank. Rarity is separate from leaderboard points.

The bundled Pokédex is public; this is casual competition, not a cheat-proof tournament. Multiple accounts and external answer tools cannot be prevented by score validation alone.

## Storage and hosting

`data/social.sqlite3` stores accounts, scrypt password hashes, hashed session tokens, friend links and daily games. It is excluded from source control and cannot be served through the Python HTTP handler. Session cookies are HttpOnly and SameSite=Lax, valid for 30 days, revoked on logout. JSON writes require a custom header and reject cross-site origins; no CORS access is enabled. Auth requests are rate limited per connecting IP in this single process. Back up SQLite using its backup API, or stop the service before copying the database; do not copy a live database without its WAL.

Before public launch, host this Python backend on persistent storage behind an HTTPS reverse proxy, keeping the backend bound to localhost. Set `SUPOKU_ORIGIN=https://your-real-domain` to enforce your origin and Secure cookies. Optionally set `SUPOKU_DB` to a persistent database path outside the checkout. Do not expose this development HTTP server directly to the internet or use static-only hosting for account features. Configure proxy request limits and login throttling; the current app does not trust forwarded IP headers, so behind a proxy its in-memory auth limit is shared. Use one app process for these in-memory rate limits, and configure monitoring, backups and retention. Domain, production hosting, operator privacy details and email recovery remain deployment work.

## API

All paths below start with `/api/social/`. Responses are JSON. Authenticated calls use the session cookie; user identity comes from that session, never a client-supplied user ID. Write requests require `Content-Type: application/json`, `X-SuPoku-Request: 1` and a same-origin browser request. Errors return `{ "error": "message" }` with 400/401/403/404/429/503.

| Method | Path | Body / result |
| --- | --- | --- |
| POST | register, login | `{username,password}` → `{user:{username}}`, session cookie |
| GET | me | `{user:{username}}` or `{user:null}` |
| POST | logout | `{}` → revoke current session |
| DELETE | account | `{password}` → permanently delete current account and related records |
| GET | friends | current user's followed players and public summary stats |
| POST / DELETE | friends | `{username}` → add/remove followed player |
| GET | stats | played, wins, currentStreak, bestStreak, bestScore, private history |
| GET | game | current UTC daily state; creates/resumes a board |
| POST | game | `{day,revision,action:"guess",cell:0,pokemon:1}`; actions `undo` (cell) and `giveup` also supported |
| GET | leaderboard?scope=today | `today`, `all` (personal best), `friends` (signed in), `streaks`; top 100 |

Each game action must use the last returned revision, preventing duplicate requests or stale tabs from spending extra guesses. On an uncertain response, reload the daily board to recover authoritative state. No endpoint accepts a claimed score, win count, date override or arbitrary user progress.

## Checks

`python -m unittest test_social` uses an isolated temporary SQLite database and local HTTP server. It covers auth, case-insensitive uniqueness, access controls, friends, score forgery rejection, game completion, immutable results, reload/login persistence, deletion, static database protection, CSRF checks, retries and undo. `node test_daily_parity.cjs` compares Python and browser generation for 30 dates (set `PYTHON` if needed). No real accounts are created by these tests.

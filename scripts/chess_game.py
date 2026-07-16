#!/usr/bin/env python3
"""Community chess for the profile README, driven by GitHub issues.

Visitors click a move link in the README, which opens a pre-filled issue
titled ``chess|move|<uci>``. The chess workflow runs this script, which
validates the move, updates the board SVG and the README section between
the CHESS markers, and writes a reply for the issue comment.

Usage:
    chess_game.py render   Re-render board + README from current state.
    chess_game.py issue    Process a move from a GitHub issue. Reads
                           ISSUE_TITLE and PLAYER from the environment and
                           writes the issue reply to $COMMENT_PATH.
"""

import json
import os
import sys
import urllib.parse

import chess
import chess.svg

REPO_DIR = os.path.join(os.path.dirname(__file__), "..")
STATE_PATH = os.path.join(REPO_DIR, "game", "state.json")
BOARD_SVG_PATH = os.path.join(REPO_DIR, "generated", "chess-board.svg")
README_PATH = os.path.join(REPO_DIR, "README.md")
COMMENT_PATH = os.environ.get("COMMENT_PATH", "/tmp/chess-comment.md")

OWNER = "ali-jifi"
REPO_URL = f"https://github.com/{OWNER}/{OWNER}"
MARKER_START = "<!-- CHESS-START -->"
MARKER_END = "<!-- CHESS-END -->"
RECENT_MOVES_SHOWN = 5


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "fen": chess.STARTING_FEN,
        "game_no": 1,
        "last_player": None,
        "last_move": None,
        "recent": [],
        "results": {"white": 0, "black": 0, "draw": 0},
    }


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def move_issue_url(board, move):
    san = board.san(move)
    title = f"chess|move|{move.uci()}"
    body = (
        f"Just press **Create** below to play **{san}**. "
        f"A GitHub Action will make your move on @{OWNER}'s profile board and "
        "close this issue automatically. Thanks for playing!"
    )
    query = urllib.parse.urlencode({"title": title, "body": body})
    return f"{REPO_URL}/issues/new?{query}"


def render_moves_table(board):
    """Markdown table of legal moves grouped by origin square."""
    by_origin = {}
    for move in board.legal_moves:
        by_origin.setdefault(move.from_square, []).append(move)

    lines = ["| Piece | Available moves |", "|-------|-----------------|"]
    for from_sq in sorted(by_origin, key=lambda s: chess.square_name(s)):
        piece = board.piece_at(from_sq)
        links = " · ".join(
            f"[{board.san(m)}]({move_issue_url(board, m)})"
            for m in sorted(by_origin[from_sq], key=lambda m: m.uci())
        )
        lines.append(f"| {piece.unicode_symbol()} {chess.square_name(from_sq)} | {links} |")
    return "\n".join(lines)


def render_readme_section(state, board):
    turn = "White" if board.turn == chess.WHITE else "Black"
    check_note = " — **check!**" if board.is_check() else ""
    results = state["results"]
    total_games = results["white"] + results["black"] + results["draw"]

    parts = [
        "Anyone can play — you move for whichever side is up. "
        f"It's **{turn}'s** turn{check_note}. Pick a move below: it opens a "
        "pre-filled GitHub issue, and pressing **Create** makes your move. "
        "The board updates in about a minute.",
        "",
        '<img src="generated/chess-board.svg" alt="Current chess board" width="400">',
        "",
        render_moves_table(board),
    ]

    if state["recent"]:
        recent = " → ".join(
            f"@{entry['player']} ({entry['san']})" for entry in state["recent"][-RECENT_MOVES_SHOWN:]
        )
        parts += ["", f"**Recent moves:** {recent}"]

    parts += [
        "",
        f"**Game #{state['game_no']}** · Completed games: {total_games} "
        f"(White {results['white']} · Black {results['black']} · Draws {results['draw']})",
    ]
    return "\n".join(parts)


def update_readme(section):
    with open(README_PATH) as f:
        readme = f.read()
    start = readme.index(MARKER_START) + len(MARKER_START)
    end = readme.index(MARKER_END)
    with open(README_PATH, "w") as f:
        f.write(readme[:start] + "\n" + section + "\n" + readme[end:])


def render_all(state, board):
    os.makedirs(os.path.dirname(BOARD_SVG_PATH), exist_ok=True)
    last_move = chess.Move.from_uci(state["last_move"]) if state["last_move"] else None
    with open(BOARD_SVG_PATH, "w") as f:
        f.write(chess.svg.board(board, lastmove=last_move, size=400))
    update_readme(render_readme_section(state, board))


def write_comment(text):
    os.makedirs(os.path.dirname(COMMENT_PATH) or ".", exist_ok=True)
    with open(COMMENT_PATH, "w") as f:
        f.write(text + "\n")


def game_over_text(board):
    outcome = board.outcome(claim_draw=True)
    if outcome.winner is None:
        return "draw", f"The game is a **draw** ({outcome.termination.name.replace('_', ' ').lower()})."
    winner = "White" if outcome.winner == chess.WHITE else "Black"
    return winner.lower(), f"**Checkmate — {winner} wins!** 🎉"


def process_issue():
    title = os.environ.get("ISSUE_TITLE", "").strip()
    player = os.environ.get("PLAYER", "").strip()
    state = load_state()
    board = chess.Board(state["fen"])

    parts = [p.strip() for p in title.split("|")]
    if len(parts) != 3 or parts[0] != "chess" or parts[1] != "move":
        write_comment(
            "I couldn't read that as a chess move. Please use one of the move "
            f"links on [my profile]({REPO_URL}#community-chess) — they fill in "
            "the issue title for you. ♟️"
        )
        return

    if state["last_player"] == player and player != OWNER:
        write_comment(
            f"Nice enthusiasm @{player}, but you made the last move — give "
            f"someone else a turn! Check back at [my profile]({REPO_URL}) soon. ♟️"
        )
        return

    try:
        move = chess.Move.from_uci(parts[2].lower())
        if move not in board.legal_moves:
            raise ValueError
    except ValueError:
        write_comment(
            f"`{parts[2]}` isn't a legal move on the current board — someone "
            "probably moved before you (the links in the README were stale). "
            f"Head back to [my profile]({REPO_URL}#community-chess) for the "
            "fresh set of moves. ♟️"
        )
        return

    san = board.san(move)
    board.push(move)
    state["fen"] = board.fen()
    state["last_move"] = move.uci()
    state["last_player"] = player
    state["recent"].append({"player": player, "san": san, "game": state["game_no"]})
    state["recent"] = state["recent"][-RECENT_MOVES_SHOWN:]

    if board.is_game_over(claim_draw=True):
        result_key, result_text = game_over_text(board)
        state["results"][result_key] += 1
        state["game_no"] += 1
        state["fen"] = chess.STARTING_FEN
        state["last_move"] = None
        state["last_player"] = None
        board = chess.Board()
        write_comment(
            f"@{player} played **{san}**. {result_text}\n\n"
            f"A fresh game is already set up on [my profile]({REPO_URL}#community-chess) — "
            "White to move. Thanks for playing! ♟️"
        )
    else:
        turn = "White" if board.turn == chess.WHITE else "Black"
        check_note = " Check!" if board.is_check() else ""
        write_comment(
            f"@{player} played **{san}**.{check_note} It's **{turn}'s** move — "
            f"the updated board is on [my profile]({REPO_URL}#community-chess). "
            "Thanks for playing! ♟️"
        )

    save_state(state)
    render_all(state, board)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "render"
    if command == "issue":
        process_issue()
    elif command == "render":
        state = load_state()
        save_state(state)
        render_all(state, chess.Board(state["fen"]))
    else:
        sys.exit(f"unknown command: {command}")


if __name__ == "__main__":
    main()

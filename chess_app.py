import os
import random
import sqlite3
import time
from datetime import datetime

import chess
import chess.pgn
from flask import redirect, request, send_from_directory
from ui import h, phone_page

BASE_DIR = os.path.dirname(__file__)
CHESS_DB_PATH = os.environ.get("CHESS_DB_PATH", os.path.join(BASE_DIR, "chess.db"))
PIECES_DIR = os.path.abspath(os.path.join(BASE_DIR, "icons", "chess_pieces"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def connect_db():
    conn = sqlite3.connect(CHESS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_chess_db():
    conn = connect_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chess_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chess_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_color TEXT NOT NULL DEFAULT 'white',
            difficulty TEXT NOT NULL DEFAULT 'medium',
            piece_style TEXT NOT NULL DEFAULT 'letters',
            moves_uci TEXT NOT NULL DEFAULT '',
            fen TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            result TEXT NOT NULL DEFAULT '*',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    # Default settings
    defaults = {
        "color": "random",
        "difficulty": "medium",
        "pieces": "png",
    }
    for k, v in defaults.items():
        conn.execute("INSERT OR IGNORE INTO chess_settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()


init_chess_db()


def get_chess_settings():
    conn = connect_db()
    rows = conn.execute("SELECT key, value FROM chess_settings").fetchall()
    conn.close()
    s = {"color": "random", "difficulty": "medium", "pieces": "png"}
    for r in rows:
        s[r["key"]] = r["value"]
    return s


def save_chess_settings(color, diff, pieces):
    conn = connect_db()
    conn.execute("INSERT OR REPLACE INTO chess_settings (key, value) VALUES ('color', ?)", (color,))
    conn.execute("INSERT OR REPLACE INTO chess_settings (key, value) VALUES ('difficulty', ?)", (diff,))
    conn.execute("INSERT OR REPLACE INTO chess_settings (key, value) VALUES ('pieces', ?)", (pieces,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Evaluation & AI Engine (Minimax with Alpha-Beta Pruning)
# ---------------------------------------------------------------------------
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}

PAWN_PST = [
    0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
]

KNIGHT_PST = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]


def evaluate_board(board):
    if board.is_checkmate():
        return -99999 if board.turn == chess.WHITE else 99999
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    val = 0
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if not p:
            continue
        base = PIECE_VALUES[p.piece_type]
        pst = 0
        if p.piece_type == chess.PAWN:
            idx = sq if p.color == chess.WHITE else chess.square_mirror(sq)
            pst = PAWN_PST[idx]
        elif p.piece_type == chess.KNIGHT:
            idx = sq if p.color == chess.WHITE else chess.square_mirror(sq)
            pst = KNIGHT_PST[idx]

        score = base + pst
        val += score if p.color == chess.WHITE else -score
    return val


def minimax(board, depth, alpha, beta, is_maximizing):
    if depth == 0 or board.is_game_over():
        return evaluate_board(board)

    moves = list(board.legal_moves)
    # Order captures first
    moves.sort(key=lambda m: board.is_capture(m), reverse=True)

    if is_maximizing:
        max_eval = -999999
        for m in moves:
            board.push(m)
            eval_score = minimax(board, depth - 1, alpha, beta, False)
            board.pop()
            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break
        return max_eval
    else:
        min_eval = 999999
        for m in moves:
            board.push(m)
            eval_score = minimax(board, depth - 1, alpha, beta, True)
            board.pop()
            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)
            if beta <= alpha:
                break
        return min_eval


def find_best_move(board, difficulty="medium"):
    moves = list(board.legal_moves)
    if not moves:
        return None

    if difficulty == "easy":
        # Depth 1: capture if available, else random
        captures = [m for m in moves if board.is_capture(m)]
        if captures and random.random() < 0.65:
            return random.choice(captures)
        return random.choice(moves)

    depth = 3 if difficulty == "hard" else 2
    is_maximizing = (board.turn == chess.WHITE)
    best_move = moves[0]
    best_val = -999999 if is_maximizing else 999999

    # Sort captures first
    moves.sort(key=lambda m: board.is_capture(m), reverse=True)
    alpha = -999999
    beta = 999999

    for m in moves:
        board.push(m)
        val = minimax(board, depth - 1, alpha, beta, not is_maximizing)
        board.pop()
        if is_maximizing:
            if val > best_val:
                best_val = val
                best_move = m
            alpha = max(alpha, val)
        else:
            if val < best_val:
                best_val = val
                best_move = m
            beta = min(beta, val)

    return best_move


# ---------------------------------------------------------------------------
# Board & Move formatting
# ---------------------------------------------------------------------------
def format_move_label(board, move):
    if board.is_kingside_castling(move):
        return "Castle Kingside (O-O)"
    if board.is_queenside_castling(move):
        return "Castle Queenside (O-O-O)"

    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)
    p = board.piece_at(move.from_square)
    p_name = chess.piece_name(p.piece_type).capitalize() if p else "Piece"
    san = board.san(move)

    promo = ""
    if move.promotion:
        promo = f" ={chess.piece_name(move.promotion).capitalize()}"

    return f"{p_name} {from_sq} -> {to_sq}{promo} ({san})"


def board_from_moves(moves_uci_str, limit_ply=None):
    board = chess.Board()
    if not moves_uci_str:
        return board
    moves = [m.strip() for m in moves_uci_str.split(",") if m.strip()]
    if limit_ply is not None:
        moves = moves[:limit_ply]
    for m in moves:
        try:
            board.push_uci(m)
        except Exception:
            break
    return board


def render_board_html(board, player_color="white", piece_style="letters", last_move=None):
    # Determine rank & file order based on player perspective
    if player_color == "black":
        ranks = list(range(1, 9))       # 1 to 8 (Black at bottom)
        files = list(range(7, -1, -1))  # h to a
    else:
        ranks = list(range(8, 0, -1))   # 8 to 1 (White at bottom)
        files = list(range(8))          # a to h

    file_letters = [chess.FILE_NAMES[f] for f in files]

    last_from = last_move.from_square if last_move else None
    last_to = last_move.to_square if last_move else None

    rows_html = ""
    for r in ranks:
        rows_html += f"<tr><td class='rank-lbl'>{r}</td>"
        for f in files:
            sq = chess.square(f, r - 1)
            is_light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 != 0
            cls = ["light" if is_light else "dark"]

            if sq in (last_from, last_to):
                cls.append("moved")

            piece = board.piece_at(sq)
            if piece:
                char = piece.symbol()
                color_name = "w" if piece.color == chess.WHITE else "b"
                if piece_style == "png":
                    cell_content = f"<img class='p-img' src='/chess/piece/{color_name}_{char.lower()}.png' alt='{char}'>"
                else:
                    p_cls = "p-white" if piece.color == chess.WHITE else "p-black"
                    cell_content = f"<span class='{p_cls}'>{char}</span>"
            else:
                cell_content = "&nbsp;"

            rows_html += f"<td class='{' '.join(cls)}'>{cell_content}</td>"
        rows_html += "</tr>\n"

    # Bottom legend row for files a-h
    bottom_files = "".join(f"<td class='file-lbl'>{fl}</td>" for fl in file_letters)
    rows_html += f"<tr><td class='file-lbl corner'>&nbsp;</td>{bottom_files}</tr>"

    return f"""
<table class="chess-table">
    <tbody>
{rows_html}
    </tbody>
</table>
"""


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CHESS_CSS = """
.menu-box{background:#0f1620;border:1px solid #263241;padding:10px 8px;border-radius:3px;margin:8px auto;max-width:240px;box-sizing:border-box;}
.menu-btn{display:block;background:#263241;color:#95e1ff;border:1px solid #3b4d61;padding:7px 12px;font-size:13px;font-weight:bold;text-decoration:none;border-radius:3px;margin:6px 0;text-align:center;}
.menu-btn:hover{background:#334458;color:#fff;}
.menu-btn.primary{background:#95e1ff;color:#000;border:0;}

.chess-table{width:224px;margin:4px auto;table-layout:fixed;border-collapse:collapse;border:1px solid #3b4d61;}
.chess-table td{width:26px;height:26px;max-width:26px;max-height:26px;padding:0;margin:0;text-align:center;vertical-align:middle;overflow:hidden;box-sizing:border-box;}
.chess-table td.rank-lbl{width:14px;max-width:14px;font-size:10px;font-weight:bold;color:#91a0af;background:#0f1620;border:0;border-right:1px solid #3b4d61;}
.chess-table td.file-lbl{height:14px;max-height:14px;font-size:10px;font-weight:bold;color:#91a0af;background:#0f1620;border:0;border-top:1px solid #3b4d61;}
.chess-table td.file-lbl.corner{width:14px;max-width:14px;background:#0f1620;border:0;}
.chess-table td.light{background:#2a3a50;}
.chess-table td.dark{background:#16202e;}
.chess-table td.moved{background:#2e4d36 !important;}

.p-white{color:#95e1ff;font-weight:bold;font-size:14px;display:block;line-height:28px;}
.p-black{color:#ffd35a;font-weight:bold;font-size:14px;display:block;line-height:28px;}
.p-img{display:block;margin:0 auto;width:22px;height:22px;}

.move-box{background:#0f1620;border:1px solid #263241;padding:6px;border-radius:3px;margin:6px auto;max-width:224px;box-sizing:border-box;}
.move-box label{display:block;color:#91a0af;font-size:11px;margin-bottom:3px;font-weight:bold;}
.move-box select{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:6px;}
.move-box input[type=submit]{background:#95e1ff;color:#000;border:0;padding:6px 14px;font-size:12px;font-weight:bold;cursor:pointer;}

.game-status{text-align:center;font-size:12px;margin:4px auto;max-width:224px;font-weight:bold;}
.status-turn{color:#9fdfff;}
.status-check{color:#ff5252;}
.status-over{background:#1a2e20;border:1px solid #336640;color:#85e396;padding:4px 6px;border-radius:2px;margin:4px auto;}

.controls-bar{text-align:center;margin:6px 0;}
.controls-bar a{margin:0 2px;}

.pgn-box{background:#0f1620;border:1px solid #263241;padding:6px;border-radius:3px;margin:8px auto;max-width:224px;font-size:11px;line-height:1.45;color:#91a0af;}
.pgn-box a{color:#9fdfff;text-decoration:none;padding:1px 2px;}
.pgn-box a.cur{background:#95e1ff;color:#000;font-weight:bold;border-radius:2px;}

.history-item{background:#0f1620;border:1px solid #263241;padding:6px;margin:4px 0;border-radius:2px;font-size:12px;}
.history-item a{color:#9fdfff;text-decoration:none;display:block;}
.history-meta{color:#91a0af;font-size:10px;margin-top:2px;}

.fen-box{font-family:monospace;font-size:10px;color:#91a0af;background:#0f1620;border:1px solid #263241;padding:4px;word-break:break-all;margin:6px auto;max-width:224px;}
"""


# ---------------------------------------------------------------------------
# Flask Routes
# ---------------------------------------------------------------------------
def register_chess_routes(flask_app, prefix="/chess"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def chess_menu():
        # Check active game
        conn = connect_db()
        active = conn.execute(
            "SELECT id, moves_uci, player_color, difficulty FROM chess_games WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()

        resume_html = ""
        if active:
            moves = [m for m in active["moves_uci"].split(",") if m]
            move_num = len(moves) // 2 + 1
            resume_html = f"""
<a class="menu-btn primary" href="{base}/play/{active['id']}">Resume Game (Move {move_num})</a>
"""

        body = f"""
<div class="menu-box">
    <div style="font-size:14px;font-weight:bold;color:#9fdfff;text-align:center;margin-bottom:10px;">MiniOS Chess</div>
    {resume_html}
    <a class="menu-btn" href="{base}/play/new">New Game</a>
    <a class="menu-btn" href="{base}/settings">Settings</a>
    <a class="menu-btn" href="{base}/history">History</a>
</div>
"""
        return phone_page("", body, nav=[("Apps", "/")], extra_css=CHESS_CSS)

    @flask_app.route(base + "/settings", methods=["GET", "POST"])
    def chess_settings_page():
        current = get_chess_settings()
        if request.method == "POST":
            c = request.form.get("color", "white")
            d = request.form.get("difficulty", "medium")
            p = request.form.get("pieces", "letters")
            save_chess_settings(c, d, p)
            return redirect(base)

        body = f"""
<form class="menu-box" method="post" action="{base}/settings">
    <div style="font-size:13px;font-weight:bold;color:#9fdfff;margin-bottom:8px;">Chess Settings</div>
    
    <label style="display:block;color:#91a0af;font-size:11px;margin:6px 0 2px;">Your Color</label>
    <select name="color" style="width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:6px;">
        <option value="white"{' selected' if current['color'] == 'white' else ''}>White (Moves first)</option>
        <option value="black"{' selected' if current['color'] == 'black' else ''}>Black (Bot first, board flipped)</option>
        <option value="random"{' selected' if current['color'] == 'random' else ''}>Random</option>
    </select>
    
    <label style="display:block;color:#91a0af;font-size:11px;margin:6px 0 2px;">Difficulty</label>
    <select name="difficulty" style="width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:6px;">
        <option value="easy"{' selected' if current['difficulty'] == 'easy' else ''}>Easy (Casual)</option>
        <option value="medium"{' selected' if current['difficulty'] == 'medium' else ''}>Medium (Standard)</option>
        <option value="hard"{' selected' if current['difficulty'] == 'hard' else ''}>Hard (Challenging)</option>
    </select>
    
    <label style="display:block;color:#91a0af;font-size:11px;margin:6px 0 2px;">Piece Style</label>
    <select name="pieces" style="width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:10px;">
        <option value="letters"{' selected' if current['pieces'] == 'letters' else ''}>Letters (P, N, B, R, Q, K)</option>
        <option value="png"{' selected' if current['pieces'] == 'png' else ''}>Piece Sprites (24px PNG)</option>
    </select>
    
    <div>
        <input class="btn" style="background:#95e1ff;color:#000;font-weight:bold;padding:6px 14px;" type="submit" value="Save Settings">
        <a class="btn" href="{base}">Cancel</a>
    </div>
</form>
"""
        return phone_page("Settings", body, nav=[("Apps", "/"), ("Chess", base), ("Back", base)], extra_css=CHESS_CSS)

    @flask_app.route(base + "/play/new")
    def chess_play_new():
        cfg = get_chess_settings()
        chosen_color = cfg["color"]
        if chosen_color == "random":
            chosen_color = random.choice(["white", "black"])

        diff = cfg["difficulty"]
        pieces = cfg["pieces"]

        board = chess.Board()
        moves_list = []

        # If player is Black, Bot plays first move as White
        if chosen_color == "black":
            bot_move = find_best_move(board, difficulty=diff)
            if bot_move:
                board.push(bot_move)
                moves_list.append(bot_move.uci())

        now = time.time()
        conn = connect_db()
        cursor = conn.execute(
            """
            INSERT INTO chess_games 
            (player_color, difficulty, piece_style, moves_uci, fen, status, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'active', '*', ?, ?)
            """,
            (chosen_color, diff, pieces, ",".join(moves_list), board.fen(), now, now),
        )
        game_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return redirect(f"{base}/play/{game_id}")

    @flask_app.route(base + "/play")
    def chess_play_default():
        conn = connect_db()
        active = conn.execute(
            "SELECT id FROM chess_games WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if active:
            return redirect(f"{base}/play/{active['id']}")
        return redirect(f"{base}/play/new")

    @flask_app.route(base + "/play/<int:game_id>")
    def chess_play_game(game_id):
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        conn.close()

        if not game:
            return redirect(base)

        moves_uci = [m for m in game["moves_uci"].split(",") if m]
        total_plies = len(moves_uci)

        # Optional viewing of past ply
        req_ply = request.args.get("ply")
        is_past_view = False
        if req_ply is not None:
            try:
                view_ply = int(req_ply)
                if 0 <= view_ply < total_plies:
                    is_past_view = True
                else:
                    view_ply = total_plies
            except ValueError:
                view_ply = total_plies
        else:
            view_ply = total_plies

        # Build board at view_ply
        board = board_from_moves(game["moves_uci"], limit_ply=view_ply)

        # Last move for highlighting
        last_move = None
        if view_ply > 0 and len(moves_uci) >= view_ply:
            try:
                last_move = chess.Move.from_uci(moves_uci[view_ply - 1])
            except Exception:
                pass

        # Player perspective
        player_color = game["player_color"]
        player_is_white = (player_color == "white")
        is_player_turn = (board.turn == chess.WHITE if player_is_white else board.turn == chess.BLACK)

        # Status line
        status_banner = ""
        if is_past_view:
            status_banner = f"""
<div class="game-status status-turn">
    Viewing Move {view_ply} of {total_plies}.<br>
    <a class="btn" href="{base}/play/{game_id}">Return to Live</a>
    <a class="btn" href="{base}/play/{game_id}/revert?ply={view_ply}">Play from Here</a>
</div>
"""
        elif game["status"] != "active":
            status_banner = f"<div class='game-status status-over'>Game Over: {h(game['status'].capitalize())} ({h(game['result'])})</div>"
        else:
            check_str = " - CHECK!" if board.is_check() else ""
            turn_name = "Your Turn" if is_player_turn else "Bot Turn"
            status_banner = f"<div class='game-status status-turn'>{turn_name}{check_str}</div>"

        # 8x8 Board HTML
        board_html = render_board_html(
            board,
            player_color=player_color,
            piece_style=game["piece_style"],
            last_move=last_move,
        )

        # Under-board Move Dropdown (only if live view, active game, and player's turn)
        move_form_html = ""
        if not is_past_view and game["status"] == "active" and is_player_turn:
            legal_moves = list(board.legal_moves)
            # Sort moves by piece type then square
            legal_moves.sort(key=lambda m: (board.piece_at(m.from_square).piece_type if board.piece_at(m.from_square) else 0, m.from_square), reverse=True)

            opts = ""
            for m in legal_moves:
                lbl = format_move_label(board, m)
                opts += f"<option value='{m.uci()}'>{h(lbl)}</option>\n"

            move_form_html = f"""
<form class="move-box" method="post" action="{base}/play/{game_id}/move">
    <label>Select Move:</label>
    <select name="move">
        {opts}
    </select>
    <div style="text-align:center;">
        <input type="submit" value="Play Move">
    </div>
</form>
"""
        elif game["status"] != "active":
            move_form_html = f"""
<div style="text-align:center;margin:8px 0;">
    <a class="btn" style="background:#95e1ff;color:#000;font-weight:bold;" href="{base}/play/new">New Game</a>
    <a class="btn" href="{base}/history/{game_id}">View Replay</a>
</div>
"""

        # Controls bar
        controls_html = f"""
<div class="controls-bar">
    <a class="btn" href="{base}/play/{game_id}/undo">Undo</a>
    <a class="btn btn-danger" href="{base}/play/{game_id}/resign">Resign</a>
    <a class="btn" href="{base}/play/new">New</a>
</div>
"""

        # PGN Moves List with clickable jumps
        pgn_html = ""
        if moves_uci:
            # Reconstruct SAN moves
            temp_board = chess.Board()
            pgn_parts = []
            for i, uci_str in enumerate(moves_uci):
                m_obj = chess.Move.from_uci(uci_str)
                san = temp_board.san(m_obj)
                temp_board.push(m_obj)

                ply_num = i + 1
                move_idx = (i // 2) + 1
                cur_cls = " class='cur'" if ply_num == view_ply else ""
                link = f"<a{cur_cls} href='{base}/play/{game_id}?ply={ply_num}'>{h(san)}</a>"

                if i % 2 == 0:
                    pgn_parts.append(f"<strong>{move_idx}.</strong> {link}")
                else:
                    pgn_parts.append(f"{link}")

            pgn_html = f"""
<div class="pgn-box">
    <div style="font-weight:bold;color:#9fdfff;margin-bottom:3px;">Move History (click to view):</div>
    {' '.join(pgn_parts)}
</div>
"""

        body = f"""
{status_banner}
{board_html}
{move_form_html}
{controls_html}
{pgn_html}
"""
        return phone_page("", body, nav=[("Apps", "/"), ("Chess", base), ("Back", base)], extra_css=CHESS_CSS)

    @flask_app.route(base + "/play/<int:game_id>/move", methods=["POST"])
    def chess_play_move(game_id):
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        if not game or game["status"] != "active":
            conn.close()
            return redirect(f"{base}/play/{game_id}")

        chosen_uci = request.form.get("move", "").strip()
        if not chosen_uci:
            conn.close()
            return redirect(f"{base}/play/{game_id}")

        board = board_from_moves(game["moves_uci"])
        moves_list = [m for m in game["moves_uci"].split(",") if m]

        # 1. Apply Player move
        try:
            player_move = chess.Move.from_uci(chosen_uci)
            if player_move in board.legal_moves:
                board.push(player_move)
                moves_list.append(player_move.uci())
        except Exception:
            conn.close()
            return redirect(f"{base}/play/{game_id}")

        # Check if game over after player move
        status = "active"
        result = "*"
        if board.is_checkmate():
            status = "checkmate"
            result = "1-0" if board.turn == chess.BLACK else "0-1"
        elif board.is_stalemate():
            status = "stalemate"
            result = "1/2-1/2"
        elif board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():
            status = "draw"
            result = "1/2-1/2"
        else:
            # 2. Bot reply move
            diff = game["difficulty"]
            bot_move = find_best_move(board, difficulty=diff)
            if bot_move:
                board.push(bot_move)
                moves_list.append(bot_move.uci())

                if board.is_checkmate():
                    status = "checkmate"
                    result = "1-0" if board.turn == chess.BLACK else "0-1"
                elif board.is_stalemate():
                    status = "stalemate"
                    result = "1/2-1/2"
                elif board.is_insufficient_material() or board.can_claim_threefold_repetition() or board.can_claim_fifty_moves():
                    status = "draw"
                    result = "1/2-1/2"

        now = time.time()
        conn.execute(
            """
            UPDATE chess_games
            SET moves_uci = ?, fen = ?, status = ?, result = ?, updated_at = ?
            WHERE id = ?
            """,
            (",".join(moves_list), board.fen(), status, result, now, game_id),
        )
        conn.commit()
        conn.close()

        return redirect(f"{base}/play/{game_id}")

    @flask_app.route(base + "/play/<int:game_id>/undo")
    def chess_play_undo(game_id):
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        if not game:
            conn.close()
            return redirect(base)

        moves = [m for m in game["moves_uci"].split(",") if m]
        player_color = game["player_color"]

        # Pop moves until it's the player's turn again
        board = board_from_moves(game["moves_uci"])
        target_turn = chess.WHITE if player_color == "white" else chess.BLACK

        while moves:
            moves.pop()
            board = board_from_moves(",".join(moves))
            if board.turn == target_turn:
                break

        now = time.time()
        conn.execute(
            """
            UPDATE chess_games
            SET moves_uci = ?, fen = ?, status = 'active', result = '*', updated_at = ?
            WHERE id = ?
            """,
            (",".join(moves), board.fen(), now, game_id),
        )
        conn.commit()
        conn.close()
        return redirect(f"{base}/play/{game_id}")

    @flask_app.route(base + "/play/<int:game_id>/resign")
    def chess_play_resign(game_id):
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        if game and game["status"] == "active":
            player_color = game["player_color"]
            result = "0-1" if player_color == "white" else "1-0"
            conn.execute(
                "UPDATE chess_games SET status = 'resigned', result = ?, updated_at = ? WHERE id = ?",
                (result, time.time(), game_id),
            )
            conn.commit()
        conn.close()
        return redirect(f"{base}/play/{game_id}")

    @flask_app.route(base + "/play/<int:game_id>/revert")
    def chess_play_revert(game_id):
        ply = int(request.args.get("ply", 0))
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        if game:
            moves = [m for m in game["moves_uci"].split(",") if m][:ply]
            board = board_from_moves(",".join(moves))
            conn.execute(
                "UPDATE chess_games SET moves_uci = ?, fen = ?, status = 'active', result = '*', updated_at = ? WHERE id = ?",
                (",".join(moves), board.fen(), time.time(), game_id),
            )
            conn.commit()
        conn.close()
        return redirect(f"{base}/play/{game_id}")

    @flask_app.route(base + "/history")
    def chess_history_list():
        conn = connect_db()
        rows = conn.execute(
            "SELECT id, player_color, difficulty, status, result, moves_uci, created_at FROM chess_games ORDER BY id DESC LIMIT 30"
        ).fetchall()
        conn.close()

        items_html = ""
        if rows:
            for r in rows:
                moves = [m for m in r["moves_uci"].split(",") if m]
                moves_count = len(moves) // 2
                dt = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M")
                result_color = "#85e396" if r["result"] in ("1-0", "0-1") else "#9fdfff"
                items_html += f"""
<div class="history-item">
    <a href="{base}/history/{r['id']}">
        <strong>Game #{r['id']}</strong> &bull; <span style="color:{result_color};">{h(r['result'])}</span> ({h(r['status'].capitalize())})
        <div class="history-meta">{dt} &bull; Color: {h(r['player_color'].capitalize())} &bull; {h(r['difficulty'].capitalize())} &bull; {moves_count} moves</div>
    </a>
</div>
"""
        else:
            items_html = "<div class='muted small'>No previous games recorded.</div>"

        body = f"""
<div style="font-size:13px;font-weight:bold;color:#9fdfff;margin-bottom:6px;">Game History</div>
{items_html}
<p style="margin-top:10px;"><a class="btn" href="{base}">&laquo; Back to Menu</a></p>
"""
        return phone_page("History", body, nav=[("Apps", "/"), ("Chess", base), ("Back", base)], extra_css=CHESS_CSS)

    @flask_app.route(base + "/history/<int:game_id>")
    def chess_history_replay(game_id):
        conn = connect_db()
        game = conn.execute("SELECT * FROM chess_games WHERE id = ?", (game_id,)).fetchone()
        conn.close()

        if not game:
            return redirect(f"{base}/history")

        moves_uci = [m for m in game["moves_uci"].split(",") if m]
        total_plies = len(moves_uci)

        req_ply = request.args.get("ply")
        if req_ply is not None:
            try:
                ply = max(0, min(int(req_ply), total_plies))
            except ValueError:
                ply = total_plies
        else:
            ply = total_plies

        board = board_from_moves(game["moves_uci"], limit_ply=ply)

        # Last move for highlight
        last_move = None
        move_info = "Starting Position"
        if ply > 0 and len(moves_uci) >= ply:
            try:
                last_move = chess.Move.from_uci(moves_uci[ply - 1])
                # Find san
                temp_b = board_from_moves(game["moves_uci"], limit_ply=ply - 1)
                move_info = f"Move {ply}: {temp_b.san(last_move)}"
            except Exception:
                pass

        board_html = render_board_html(
            board,
            player_color=game["player_color"],
            piece_style=game["piece_style"],
            last_move=last_move,
        )

        # Replay buttons
        prev_ply = max(0, ply - 1)
        next_ply = min(total_plies, ply + 1)
        replay_controls = f"""
<div class="controls-bar">
    <a class="btn" href="{base}/history/{game_id}?ply=0">|&laquo;</a>
    <a class="btn" href="{base}/history/{game_id}?ply={prev_ply}">&lsaquo; Prev</a>
    <span style="font-size:12px;color:#fff;margin:0 4px;">{ply}/{total_plies}</span>
    <a class="btn" href="{base}/history/{game_id}?ply={next_ply}">Next &rsaquo;</a>
    <a class="btn" href="{base}/history/{game_id}?ply={total_plies}">&raquo;|</a>
</div>
"""

        # PGN Moves List with clickable links
        pgn_parts = []
        if moves_uci:
            temp_board = chess.Board()
            for i, uci_str in enumerate(moves_uci):
                m_obj = chess.Move.from_uci(uci_str)
                san = temp_board.san(m_obj)
                temp_board.push(m_obj)

                ply_num = i + 1
                move_idx = (i // 2) + 1
                cur_cls = " class='cur'" if ply_num == ply else ""
                link = f"<a{cur_cls} href='{base}/history/{game_id}?ply={ply_num}'>{h(san)}</a>"

                if i % 2 == 0:
                    pgn_parts.append(f"<strong>{move_idx}.</strong> {link}")
                else:
                    pgn_parts.append(f"{link}")

        pgn_html = f"""
<div class="pgn-box">
    <div style="font-weight:bold;color:#9fdfff;margin-bottom:3px;">PGN:</div>
    {' '.join(pgn_parts)}
</div>
"""

        fen_html = f"""
<div class="fen-box">
    <strong>FEN:</strong><br>{h(board.fen())}
</div>
"""

        play_here_btn = f"""
<div style="text-align:center;margin:6px 0;">
    <a class="btn" href="{base}/play/{game_id}/revert?ply={ply}">Play from Here</a>
</div>
"""

        body = f"""
<div style="text-align:center;font-size:12px;font-weight:bold;color:#9fdfff;">{move_info}</div>
{board_html}
{replay_controls}
{play_here_btn}
{pgn_html}
{fen_html}
"""
        return phone_page("Replay", body, nav=[("Apps", "/"), ("Chess", base), ("History", f"{base}/history")], extra_css=CHESS_CSS)

    @flask_app.route(base + "/piece/<path:filename>")
    def chess_piece_img(filename):
        return send_from_directory(PIECES_DIR, filename)

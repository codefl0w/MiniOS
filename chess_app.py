from flask import redirect, request
from ui import h, phone_page

# Starting position board array (row 0 = rank 8, row 7 = rank 1)
INITIAL_BOARD = [
    ["r", "n", "b", "q", "k", "b", "n", "r"],  # rank 8 (Black)
    ["p", "p", "p", "p", "p", "p", "p", "p"],  # rank 7 (Black)
    ["",  "",  "",  "",  "",  "",  "",  ""],   # rank 6
    ["",  "",  "",  "",  "",  "",  "",  ""],   # rank 5
    ["",  "",  "",  "",  "",  "",  "",  ""],   # rank 4
    ["",  "",  "",  "",  "",  "",  "",  ""],   # rank 3
    ["P", "P", "P", "P", "P", "P", "P", "P"],  # rank 2 (White)
    ["R", "N", "B", "Q", "K", "B", "N", "R"],  # rank 1 (White)
]

# Sample legal opening moves for White pieces
OPENING_MOVES = {
    "a2": [("a3", "to a3"), ("a4", "to a4")],
    "b2": [("b3", "to b3"), ("b4", "to b4")],
    "c2": [("c3", "to c3"), ("c4", "to c4")],
    "d2": [("d3", "to d3"), ("d4", "to d4")],
    "e2": [("e3", "to e3"), ("e4", "to e4")],
    "f2": [("f3", "to f3"), ("f4", "to f4")],
    "g2": [("g3", "to g3"), ("g4", "to g4")],
    "h2": [("h3", "to h3"), ("h4", "to h4")],
    "b1": [("a3", "to a3"), ("c3", "to c3")],
    "g1": [("f3", "to f3"), ("h3", "to h3")],
}

CHESS_CSS = """
.mode-bar{text-align:center;margin:2px 0 6px;font-size:11px;}
.mode-bar a{margin:0 2px;}
.mode-bar a.active{background:#95e1ff;color:#000;font-weight:bold;}
.chess-table{width:224px;margin:0 auto 6px;table-layout:fixed;border-collapse:collapse;border:2px solid #3b4d61;}
.chess-table td{width:28px;height:28px;max-width:28px;max-height:28px;padding:0;margin:0;text-align:center;vertical-align:middle;overflow:hidden;box-sizing:border-box;}
.chess-table td.light{background:#2a3a50;}
.chess-table td.dark{background:#16202e;}
.chess-table td.moved{background:#3b563c !important;}

/* Cell dropdown styling */
select.cell-sel{
    width:100%;
    height:28px;
    line-height:28px;
    border:0;
    background:transparent;
    color:#95e1ff;
    font-size:13px;
    font-weight:bold;
    text-align:center;
    text-align-last:center;
    padding:0;
    margin:0;
    box-sizing:border-box;
    cursor:pointer;
    display:block;
}
select.cell-sel option{background:#0f1620;color:#fff;font-size:12px;}

/* Piece text */
.p-white{color:#95e1ff;font-weight:bold;font-size:14px;display:block;line-height:28px;}
.p-black{color:#ffd35a;font-weight:bold;font-size:14px;display:block;line-height:28px;}

/* Move box for bottom mode */
.move-box{background:#0f1620;border:1px solid #263241;padding:6px;border-radius:3px;margin:6px auto;max-width:224px;box-sizing:border-box;}
.move-box label{display:block;color:#91a0af;font-size:11px;margin-bottom:3px;}
.move-box select{width:100%;box-sizing:border-box;background:#fff;color:#000;border:0;padding:5px;font-size:12px;margin-bottom:6px;}

.info-bar{text-align:center;font-size:11px;color:#91a0af;margin:4px 0;}
.status-msg{background:#132a18;border:1px solid #2e663a;color:#85e396;padding:4px 6px;font-size:11px;border-radius:2px;margin:4px auto;max-width:224px;text-align:center;}
"""


def register_chess_routes(flask_app, prefix="/chess"):
    base = prefix.rstrip("/")

    @flask_app.route(base)
    @flask_app.route(base + "/")
    def chess_index():
        mode = request.args.get("mode", "cell")  # "cell" (user's method) or "bottom"
        last_move = request.args.get("last", "")

        # Mode toggle bar
        cell_active = " active" if mode == "cell" else ""
        bottom_active = " active" if mode == "bottom" else ""
        mode_html = f"""
<div class="mode-bar">
    <a class="btn{cell_active}" href="{base}?mode=cell">Dropdown in Cell</a>
    <a class="btn{bottom_active}" href="{base}?mode=bottom">Under-Board Menu</a>
</div>
"""

        status_html = ""
        if last_move:
            status_html = f"<div class='status-msg'>Move played: <strong>{h(last_move)}</strong></div>"

        # Render 8x8 Board
        files = ["a", "b", "c", "d", "e", "f", "g", "h"]
        ranks = [8, 7, 6, 5, 4, 3, 2, 1]

        board_rows_html = ""
        for r_idx, rank in enumerate(ranks):
            board_rows_html += "<tr>"
            for f_idx, f_char in enumerate(files):
                sq = f"{f_char}{rank}"
                is_light = (r_idx + f_idx) % 2 == 0
                cell_class = "light" if is_light else "dark"

                piece = INITIAL_BOARD[r_idx][f_idx]

                # Check if square has player moves (White pieces)
                legal_moves = OPENING_MOVES.get(sq, [])

                if mode == "cell" and legal_moves and piece:
                    # Method 1: Dropdown in cell
                    opts = f"<option value=''>{piece}</option>"
                    for dest, label in legal_moves:
                        opts += f"<option value='{sq}->{dest}'>{label}</option>"

                    cell_content = f"""<select class="cell-sel" name="m_{sq}" onchange="this.form.submit()">{opts}</select>"""
                elif piece:
                    # Regular piece display
                    p_cls = "p-white" if piece.isupper() else "p-black"
                    cell_content = f"<span class='{p_cls}'>{piece}</span>"
                else:
                    cell_content = "&nbsp;"

                board_rows_html += f"<td class='{cell_class}'>{cell_content}</td>"
            board_rows_html += "</tr>\n"

        board_table = f"""
<table class="chess-table">
    <tbody>
{board_rows_html}
    </tbody>
</table>
"""

        if mode == "cell":
            # Form wrapping the board
            controls_html = f"""
<form method="post" action="{base}/play?mode=cell">
    {board_table}
    <div style="text-align:center;margin:6px 0;">
        <input class="btn" type="submit" value="Play Selected Move">
        <a class="btn" href="{base}?mode=cell">Reset</a>
    </div>
</form>
<div class="info-bar">Select piece dropdown on board to choose move.</div>
"""
        else:
            # Method 2: Bottom dropdown menu
            options_html = ""
            for sq, moves in OPENING_MOVES.items():
                piece_name = "Pawn" if sq[1] == "2" else "Knight"
                for dest, label in moves:
                    options_html += f"<option value='{sq}->{dest}'>{piece_name} {sq} -&gt; {dest}</option>"

            controls_html = f"""
{board_table}
<form class="move-box" method="post" action="{base}/play?mode=bottom">
    <label>Choose Move (White):</label>
    <select name="move">
        {options_html}
    </select>
    <div style="text-align:center;">
        <input type="submit" value="Play Move">
        <a class="btn" href="{base}?mode=bottom">Reset</a>
    </div>
</form>
<div class="info-bar">Clean board, single move dropdown below.</div>
"""

        body = f"""
{mode_html}
{status_html}
{controls_html}
"""
        return phone_page("", body, nav=[("Apps", "/"), ("Chess", base)], extra_css=CHESS_CSS)

    @flask_app.route(base + "/play", methods=["POST"])
    def chess_play():
        mode = request.args.get("mode", "cell")
        chosen_move = ""

        if mode == "cell":
            # Search all m_{sq} fields for chosen move
            for k, v in request.form.items():
                if k.startswith("m_") and v:
                    chosen_move = v
                    break
        else:
            chosen_move = request.form.get("move", "")

        if not chosen_move:
            chosen_move = "e2->e4 (default)"

        # Redirect back to board with feedback
        return redirect(f"{base}?mode={mode}&last={h(chosen_move)}")

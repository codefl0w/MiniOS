from html import escape

BG = "#191f2e"
PANEL = "#0f1620"
TEXT = "#ffffff"
MUTED = "#91a0af"
LINK = "#9fdfff"
BORDER = "#263241"


def h(value, default=""):
    if value is None:
        return default
    return escape(str(value), quote=True)


def get_ui_config():
    try:
        from settings import app_settings
        return app_settings("ui")
    except Exception:
        return {"bg_color": BG, "icon_size": 44, "cell_height": 82, "font_size": 13}


def phone_page(title, body, nav=None, extra_css=""):
    ui_cfg = get_ui_config()
    bg_color = ui_cfg.get("bg_color", BG)
    font_size = ui_cfg.get("font_size", 13)
    
    nav_html = ""
    if nav:
        nav_links = list(nav)
        if nav_links and nav_links[0][1] != "/" and nav_links[0][0] != "Apps":
            nav_links.insert(0, ("Apps", "/"))
        links = [f"<a href='{h(url)}'>{h(label)}</a>" for label, url in nav_links if label]
        nav_html = f"<div class='nav'>{' | '.join(links)}</div>"

    title_html = f"<h3>{h(title)}</h3>" if title else ""
    return f"""<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{{font-family:Arial;background:{bg_color};color:{TEXT};margin:0;padding:6px;font-size:{font_size}px;line-height:1.25;}}
a{{color:{LINK};text-decoration:none;}}
h3{{font-size:15px;margin:4px 0 8px;}}
.nav{{margin:0 0 6px;color:{MUTED};font-size:12px;}}
.muted{{color:{MUTED};}}
.btn{{display:inline-block;background:#263241;color:#95e1ff;border:1px solid #3b4d61;padding:4px 10px;font-size:11px;text-decoration:none;border-radius:3px;margin:3px 0;line-height:normal;box-sizing:border-box;}}
.btn-danger{{background:#5c1d1d !important;color:#ff9e9e !important;border:1px solid #852b2b !important;}}
{extra_css}
</style></head><body>{nav_html}{title_html}{body}</body></html>"""


def welcome_screen():
    css = f"""
.welcome-wrap{{text-align:center;padding:20px 8px;max-width:240px;margin:0 auto;box-sizing:border-box;}}
.welcome-logo{{max-width:150px;width:75%;height:auto;display:block;margin:0 auto 12px;}}
.welcome-title{{font-size:15px;font-weight:bold;color:{TEXT};margin:0 0 8px;}}
.welcome-text{{font-size:11px;line-height:1.4;color:{MUTED};margin:0 0 16px;}}
.welcome-btn{{display:inline-block;background:{BORDER};color:{LINK};border:1px solid #3b4d61;padding:7px 22px;font-size:13px;font-weight:bold;text-decoration:none;border-radius:4px;}}
.welcome-btn:hover{{background:#334458;color:{TEXT};}}
"""
    html = f"""<div class="welcome-wrap">
<img src="/github_res/MiniOS_Logo.png" alt="MiniOS Logo" class="welcome-logo">
<div class="welcome-title">Welcome to MiniOS</div>
<div class="welcome-text">Configure app behavior in Settings and add your keys in the .env file. Enjoy!</div>
<div class="welcome-text">For bugs and feature requests, open an issue at <a href="">github.com/codefl0w/MiniOS/issues</a>.</div>
<div><a href="/welcome/dismiss" class="welcome-btn" autofocus>Get Started</a></div>
</div>"""
    return html, css


welcome_popup = welcome_screen


def app_drawer(apps, slots=9):
    ui_cfg = get_ui_config()
    icon_size = ui_cfg.get("icon_size", 44)
    cell_height = ui_cfg.get("cell_height", 82)
    total_slots = max(slots or 9, ((len(apps) + 2) // 3) * 3)

    drawer_css = f"""
.drawer{{width:100%;overflow:hidden;}}
.appcell{{float:left;width:33%;height:{cell_height}px;text-align:center;padding:5px 0;color:{TEXT};}}
.appcell a{{display:block;color:{TEXT};}}
.drawer img{{width:{icon_size}px;height:{icon_size}px;border:0;display:block;margin:0 auto 4px;}}
.label{{display:block;font-size:10px;line-height:10px;color:{TEXT};word-wrap:break-word;}}
.cell-empty{{float:left;width:33%;height:{cell_height}px;}}
.cell-off .label{{color:{MUTED};}}
.clear{{clear:both;height:0;overflow:hidden;}}
"""
    cells = []
    for app in apps[:total_slots]:
        name = h(app.get("label", app.get("name")))
        url = h(app.get("url", "#"))
        icon = h(app.get("icon", "blank.png"))
        disabled = app.get("disabled")
        if disabled:
            cells.append(
                f"<div class='appcell cell-off'><img src='/icons/{icon}' alt=''><span class='label'>{name}</span></div>"
            )
        else:
            cells.append(
                f"<div class='appcell'><a href='{url}'><img src='/icons/{icon}' alt=''><span class='label'>{name}</span></a></div>"
            )

    while len(cells) < total_slots:
        cells.append("<div class='cell-empty'>&nbsp;</div>")

    return "<div class='drawer'>" + "".join(cells) + "<div class='clear'></div></div>", drawer_css

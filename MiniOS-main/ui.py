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


def phone_page(title, body, nav=None, extra_css=""):
    nav_html = ""
    if nav:
        links = [f"<a href='{h(url)}'>{h(label)}</a>" for label, url in nav]
        nav_html = f"<div class='nav'>{' | '.join(links)}</div>"

    return f"""<html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{{font-family:Arial;background:{BG};color:{TEXT};margin:0;padding:6px;font-size:13px;line-height:1.25;}}
a{{color:{LINK};text-decoration:none;}}
h3{{font-size:15px;margin:4px 0 8px;}}
.nav{{margin:0 0 6px;color:{MUTED};font-size:12px;}}
.muted{{color:{MUTED};}}
{extra_css}
</style></head><body>{nav_html}<h3>{h(title)}</h3>{body}</body></html>"""


def app_drawer(apps, slots=9):
    drawer_css = f"""
.drawer{{width:100%;overflow:hidden;}}
.appcell{{float:left;width:33%;height:82px;text-align:center;padding:5px 0;color:{TEXT};}}
.appcell a{{display:block;color:{TEXT};}}
.drawer img{{width:44px;height:44px;border:0;display:block;margin:0 auto 4px;}}
.label{{display:block;font-size:10px;line-height:10px;color:{TEXT};word-wrap:break-word;}}
.cell-empty{{float:left;width:33%;height:82px;}}
.cell-off .label{{color:{MUTED};}}
.clear{{clear:both;height:0;overflow:hidden;}}
"""
    cells = []
    for app in apps[:slots]:
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

    while len(cells) < slots:
        cells.append("<div class='cell-empty'>&nbsp;</div>")

    return "<div class='drawer'>" + "".join(cells) + "<div class='clear'></div></div>", drawer_css

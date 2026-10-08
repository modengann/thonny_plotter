"""
upload_server.py  -  the students' upload page on the Raspberry Pi.

    python3 upload_server.py            (port 8000; the Pi runs it as a service)

Students pick a .py file and type their name.  The program is checked
(code_check.py) and, if it is plain turtle code, saved in uploads/ where
the dashboard's Open dialog starts.  The page also links to the dashboard
itself (noVNC, port 6080).
"""

import argparse
import datetime
import os
import sys

from flask import Flask, render_template_string, request

import code_check

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "uploads")
MAX_BYTES = 100 * 1024
SHOW = 20
DASHBOARD_PORT = 6080
TOO_BIG = "That file is too big for a turtle program (over 100 KB)."

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AX4 Plotter</title>
<style>
 body { font-family: sans-serif; max-width: 40rem; margin: 1rem auto;
        padding: 0 1rem; }
 .dash { display: block; padding: 1rem; margin: 1rem 0; text-align: center;
         background: #2a6; color: white; font-size: 1.3rem;
         text-decoration: none; border-radius: 6px; }
 .ok { background: #dfd; padding: .5rem; }
 .bad { background: #fdd; padding: .5rem; }
 input, button { font-size: 1rem; margin: .3rem 0; }
</style></head><body>
<h1>AX4 Plotter</h1>
<a class="dash" href="{{ dashboard }}">Open the plotter dashboard</a>
<h2>Upload your turtle program</h2>
{% if saved %}<p class="ok">Uploaded as <b>{{ saved }}</b>.
 Open it from the dashboard with "Open student file...".</p>{% endif %}
{% if problems %}<div class="bad"><p>Not uploaded:</p><ul>
 {% for p in problems %}<li>{{ p }}</li>{% endfor %}</ul></div>{% endif %}
<form method="post" enctype="multipart/form-data">
 <label>Your name <input name="name" maxlength="30" value="{{ name }}"></label><br>
 <input type="file" name="file" accept=".py"><br>
 <button type="submit">Upload</button>
</form>
<h2>Recent uploads</h2>
<ul>{% for f in files %}<li>{{ f }}</li>{% else %}<li>None yet.</li>{% endfor %}</ul>
</body></html>"""


def clean_name(name):
    """Letters (any language), digits, - and _; spaces become _."""
    kept = "".join(c for c in name.strip().replace(" ", "_")
                   if c.isalnum() or c in "-_")
    return kept.strip("_-")[:30] or "student"


def save_upload(folder, name, source, now=None):
    """Save source as <name>_<date-time>.py, never overwriting.  Returns
    the file name."""
    now = now or datetime.datetime.now()
    base = "%s_%s" % (clean_name(name), now.strftime("%Y%m%d-%H%M%S"))
    filename, n = base + ".py", 2
    while True:
        try:                         # "x": fails if it exists, even if
            f = open(os.path.join(folder, filename), "x",    # another upload
                     encoding="utf-8", newline="")         # just made it
        except FileExistsError:
            filename, n = "%s_%d.py" % (base, n), n + 1
            continue
        with f:
            f.write(source)
        return filename


def recent(folder, n=SHOW):
    """The n most recently uploaded .py files, newest first."""
    files = [f for f in os.listdir(folder) if f.endswith(".py")]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)),
               reverse=True)
    return files[:n]


def _read_upload(upload):
    """(source, problems) for an uploaded file."""
    if upload is None or not upload.filename:
        return None, ["Choose a file to upload."]
    if not upload.filename.lower().endswith(".py"):
        return None, ["Only Python files (.py) can be plotted."]
    data = upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return None, [TOO_BIG]
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, ["The file isn't saved as UTF-8 text.  Save it from "
                      "Thonny and try again."]
    return source, code_check.check(source)


def create_app(folder=UPLOADS):
    os.makedirs(folder, exist_ok=True)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 16 * 1024   # form overhead

    def page(status=200, **values):
        host = request.host.split(":")[0]
        values.setdefault("name", "")
        return render_template_string(
            PAGE, files=recent(folder),
            dashboard="http://%s:%d/vnc.html?autoconnect=1&resize=scale"
                      % (host, DASHBOARD_PORT),
            **values), status

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            return page()
        name = request.form.get("name", "")
        source, problems = _read_upload(request.files.get("file"))
        if problems:
            return page(problems=problems, name=name)
        return page(saved=save_upload(folder, name, source), name=name)

    @app.errorhandler(413)
    def too_big(e):
        return page(413, problems=[TOO_BIG])

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="AX4 plotter upload page")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args(argv)
    create_app().run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    sys.exit(main())

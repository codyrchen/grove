"""Grove: a daily dashboard for Ole Miss students.

Run locally:
    python -m flask --app grove.web run --debug
"""

import os

from flask import Flask, abort, g, jsonify, render_template
from werkzeug.middleware.proxy_fix import ProxyFix

from . import db, widgets
from .config import database_url, load_env

SITE_NAME = "Grove"


def create_app(database: str | None = None) -> Flask:
    load_env()
    app = Flask(__name__)
    # Railway (and most hosts) sit behind a proxy that terminates HTTPS.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["DATABASE"] = database or database_url()
    app.jinja_env.globals.update(SITE_NAME=SITE_NAME,
                                 PHOTO_SUBMIT_URL=os.environ.get("PHOTO_SUBMIT_URL"))

    def get_db() -> db.DB:
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", widgets=widgets.WIDGETS, roles=widgets.ROLES,
                               greeting=widgets.greeting(), photo=widgets.photo_of_the_day())

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.get("/api/widgets")
    def api_widgets():
        conn = get_db()
        names = ["greeting", "photo", *widgets.WIDGETS]
        return jsonify({n: widgets.build(conn, n) for n in names})

    @app.get("/api/widgets/<name>")
    def api_widget(name):
        if name not in ("greeting", "photo") and name not in widgets.WIDGETS:
            abort(404)
        return jsonify(widgets.build(get_db(), name))

    @app.get("/healthz")
    def healthz():
        get_db().execute("SELECT 1")
        return "ok"

    return app


app = create_app()

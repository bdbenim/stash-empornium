#!/usr/bin/env python3.12

__author__ = "An EMP user"
__license__ = "unlicense"
__version__ = "0.21.0"

# built-in
import json
from loguru import logger
import os
import time
from concurrent.futures import Future

# external
from flask import (Flask, Response, redirect, request, stream_with_context,
                   url_for)
from flask_bootstrap import Bootstrap5
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

# included
from utils import db, generator, taghandler
from utils.confighandler import ConfigHandler
from webui.webui import settings_page

#############
# CONSTANTS #
#############

ODBL_NOTICE = ("Contains information from https://github.com/mledoze/countries which is made available here under the "
               "Open Database License (ODbL), available at https://github.com/mledoze/countries/blob/master/LICENSE")

config = ConfigHandler()
# logger = logging.getLogger(__name__)
logger.info(f"stash-empornium version {__version__}.")
logger.info(f"Release notes: https://github.com/bdbenim/stash-empornium/releases/tag/v{__version__}")
logger.info(ODBL_NOTICE)

app = Flask(__name__, template_folder=config.template_dir)
app.secret_key = "secret"
app.config["BOOTSTRAP_BOOTSWATCH_THEME"] = "cyborg"
app.register_blueprint(settings_page)
db_path = os.path.abspath(os.path.join(config.config_dir, "db.sqlite3"))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
db.db.init_app(app)
# Ensure FOREIGN KEY for sqlite3
if 'sqlite:' in app.config['SQLALCHEMY_DATABASE_URI']:
    def _fk_pragma_on_connect(dbapi_con, con_record):  # noqa
        dbapi_con.execute('pragma foreign_keys=ON')


    with app.app_context():
        from sqlalchemy import event

        event.listen(db.db.engine, 'connect', _fk_pragma_on_connect)
migrate = Migrate(app, db.db)
with app.app_context():
    db.upgrade()
taghandler.setup(app)
bootstrap = Bootstrap5(app)
csrf = CSRFProtect(app)


@stream_with_context
def generate():
    j = request.get_json()
    try:
        future: Future = generator.jobs[j["id"]]
    except KeyError:
        yield generator.error("Error getting job. Is your userscript updated?")
        return
    except ValueError:
        yield generator.error("Invalid job ID")
        return
    except IndexError:
        yield generator.error("Job does not exist")
        return
    for msg in future.result():
        yield msg
        time.sleep(0.1)


@app.route("/submit", methods=["POST"])
@csrf.exempt
def submit():
    j = request.get_json()
    logger.debug(f"Torrent submitted: {j}")
    for client in config.torrent_clients:
        try:
            client.start(j["torrent_path"])
        except Exception as e:
            logger.error(f"Error attempting to start torrent in {client.name}")
            logger.debug(e)
    return json.dumps({"status": "success"})


@app.route("/suggestions", methods=["POST"])
@csrf.exempt
def process_suggestions():
    j = request.get_json()
    logger.debug(f"Got json {j}")
    accepted_tags = {}
    if "accept" in j:
        logger.info(f"Accepting {len(j['accept'])} tag suggestions")
        for tag in j["accept"]:
            if "name" in tag:
                accepted_tags[tag["name"]] = tag["emp"]
    ignored_tags = []
    if "ignore" in j:
        logger.info(f"Ignoring {len(j['ignore'])} tags")
        for tag in j["ignore"]:
            ignored_tags.append(tag)
    taghandler.accept_suggestions(accepted_tags, j["tracker"])
    taghandler.reject_suggestions(ignored_tags)
    return json.dumps({"status": "success", "data": {"message": "Tags saved"}})


@app.route("/fill", methods=["POST"])
@csrf.exempt
def fill():
    return Response(generate(), mimetype="application/json")  # type: ignore


@app.route("/generate", methods=["POST"])
@csrf.exempt
def submit_job():
    j = request.get_json()
    job_id = generator.add_job(j)
    return json.dumps({"id": job_id})


@app.route("/templates")
@csrf.exempt
def templates():
    return json.dumps(config.template_names)


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="images/favicon.ico"))


@app.route("/favicon-16x16.png")
def favicon16():
    return redirect(url_for("static", filename="images/favicon-16x16.png"))


@app.route("/favicon-32x32.png")
def favicon32():
    return redirect(url_for("static", filename="images/favicon-32x32.png"))


@app.route("/apple-touch-icon.png")
def apple_touch_icon():
    return redirect(url_for("static", filename="images/apple-touch-icon.png"))


@app.route("/android-chrome-192x192.png")
def android_chrome_192():
    return redirect(url_for("static", filename="images/android-chrome-192x192.png"))


@app.route("/android-chrome-512x512.png")
def android_chrome_512():
    return redirect(url_for("static", filename="images/android-chrome-512x512.png"))


@app.route("/mstile-70x70.png")
def mstile70():
    return redirect(url_for("static", filename="images/mstile-70x70.png"))


@app.route("/mstile-144x144.png")
def mstile144():
    return redirect(url_for("static", filename="images/mstile-144x144.png"))


@app.route("/mstile-150x150.png")
def mstile150():
    return redirect(url_for("static", filename="images/mstile-150x150.png"))


@app.route("/mstile-310x150.png")
def mstile310_150():
    return redirect(url_for("static", filename="images/mstile-310x150.png"))


@app.route("/mstile-310x310.png")
def mstile310():
    return redirect(url_for("static", filename="images/mstile-310x310.png"))


@app.route("/safari-pinned-tab.svg")
def safari():
    return redirect(url_for("static", filename="images/safari-pinned-tab.svg"))


@app.route("/browserconfig.xml")
def browserconfig():
    return redirect(url_for("static", filename="browserconfig.xml"))


@app.route("/site.webmanifest")
def webmanifest():
    return redirect(url_for("static", filename="site.webmanifest"))


if __name__ == "__main__":
    try:
        from waitress import serve

        serve(app, host="0.0.0.0", port=config.get("backend", "port", 9932))
        # app.run(host="0.0.0.0", port=config.port, debug=True)
    except ModuleNotFoundError:
        logger.info("Waitress not installed, using builtin server")
        app.run(host="0.0.0.0", port=config.get("backend", "port", 9932), debug=False)  # type: ignore

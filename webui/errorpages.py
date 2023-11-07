from flask import Blueprint, render_template
from werkzeug.exceptions import HTTPException

error_page = Blueprint("error_page", __name__, template_folder="templates")

@error_page.app_errorhandler(HTTPException)
def handle_exception(e):
    message = e.name
    if e.code == 404:
        message = "The page you were looking for was not found"
    return render_template("errorpage.html", code=e.code, message=message)

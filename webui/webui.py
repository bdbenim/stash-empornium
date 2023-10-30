from flask import render_template, Blueprint
simple_page = Blueprint('simple_page', __name__, template_folder="templates")
@simple_page.route("/", defaults={'page': 'index.html'})
@simple_page.route("/<page>")
def show(page):
    return render_template(f"{page}", title="Welcome", username="User")
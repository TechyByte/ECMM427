from flask import Blueprint, request, redirect, url_for, render_template, flash
from flask_login import login_user, logout_user, login_required

from models import User, LoginUser

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and user.check_password(request.form["password"]):
            if user.active:
                login_user(LoginUser(user))
                return redirect(url_for("user.home"))
            else:
                flash("Your account is inactive. Please contact the administrator.", "warning")
        else:
            flash("Invalid credentials", "warning")
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

from datetime import datetime
from flask import Flask, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from models.db import db
from models import User, LoginUser
from routes.auth import auth_bp
from routes.user import user_bp
from routes.proposal import proposal_bp
from routes.project import project_bp

CONFIG = {
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///dissertations.db',
    'SECRET_KEY': 'dev',
    'FLASK_DEBUG': 1,
}

def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(CONFIG)
    if config:
        app.config.from_mapping(config)

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return LoginUser(user) if user else None

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('user.home'))
        else:
            return redirect(url_for('auth.login'))

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(proposal_bp, url_prefix='/proposal')
    app.register_blueprint(project_bp, url_prefix='/project')

    with app.app_context():
        db.create_all()

    return app

if __name__ == "__main__":
    this_app = create_app()
    this_app.run(debug=True)

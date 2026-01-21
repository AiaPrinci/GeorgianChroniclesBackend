from flask import Flask
from flask_cors import CORS
from flask_login import LoginManager
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = "fallback-secret"
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///site.db"
app.config["SESSION_COOKIE_SAMESITE"] = "None"
app.config["SESSION_COOKIE_SECURE"] = True
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://localhost:5173",
        "https://georgianchronicles.netlify.app"
    ],
    allow_headers=["Content-Type", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

from models import db, User

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

from routes import *

print("Render is running this version")

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0")
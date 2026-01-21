from flask import request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from app import app, db
from models import User, Post, Comment, Like
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import jwt
from functools import wraps

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "mp4", "webm", "mov", "mkv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ----------------------
# Helper Functions
# ----------------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token missing"}), 401
        try:
            token = token.split()[1]  # Expecting "Bearer <token>"
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.get(data["user_id"])
        except Exception as e:
            print("JWT error:", e)
            return jsonify({"error": "Invalid or expired token"}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ----------------------
# Auth Routes
# ----------------------

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data sent"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    bio = ""
    role = "member"

    if not username or not email or not password:
        return jsonify({"error": "Missing fields"}), 400

    email = email.lower()

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "ელფოსტა უკვე დარეგისტრირებულია"}), 409

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username უკვე გამოყენებულია"}), 409
    
    if len(password) < 8:
        return jsonify({"error": "პაროლი უნდა შეიცავდეს მინიმუმ 8 სიმბოლოს"}), 400

    user = User(
        username=username,
        email=email,
        password=generate_password_hash(password),
        role="member",
        bio=""
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "Register successful"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data sent"}), 400

    email = data.get("email")
    password = data.get("password")

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "მონაცემები არასწორია"}), 401

    # Generate JWT
    token = jwt.encode({
        "user_id": user.id,
        "exp": datetime.utcnow() + timedelta(days=1)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "profile_image": user.profile_image,
            "role": user.role,
            "bio": user.bio
        }
    }), 200

@app.route("/auth-status", methods=["GET"])
@token_required
def auth_status(current_user):
    return jsonify({
        "logged_in": True,
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "profile_image": current_user.profile_image,
            "role": current_user.role,
            "bio": current_user.bio
        }
    })

# ----------------------
# Post Routes
# ----------------------

@app.route("/posts", methods=["POST"])
@token_required
def create_post(current_user):
    cooldown_seconds = 10
    now = datetime.utcnow()

    if current_user.last_post_time and (now - current_user.last_post_time).total_seconds() < cooldown_seconds:
        remaining = cooldown_seconds - (now - current_user.last_post_time).total_seconds()
        return jsonify({"error": f"Please wait {int(remaining)} more seconds before posting again"}), 429

    title = request.form.get("title")
    content = request.form.get("content")

    image = request.files.get("image")
    video = request.files.get("video")

    if not title and not content and not image and not video:
        return jsonify({"error": "You must provide a title, content, image, or video"}), 400

    file = image or video
    filename = None
    media_type = None

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit(".", 1)[1].lower()
        media_type = "video" if ext in {"mp4", "webm", "mov"} else "image"
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    post = Post(
        title=title or "",
        content=content or "",
        media=filename,
        media_type=media_type,
        user_id=current_user.id
    )

    current_user.last_post_time = now
    db.session.add(post)
    db.session.commit()

    return jsonify({
        "message": "Post created",
        "post": {
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "media": post.media,
            "media_type": post.media_type,
            "created_at": post.created_at,
            "author": {
                "id": current_user.id,
                "username": current_user.username,
                "image": current_user.profile_image
            },
            "comments": [],
            "likes": 0
        }
    }), 201

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

@app.route("/posts/<int:post_id>", methods=["DELETE"])
@token_required
def delete_post(current_user, post_id):
    post = Post.query.get_or_404(post_id)

    if post.user_id != current_user.id and current_user.role != "admin":
        return jsonify({"error": "You are not allowed to delete this post"}), 403

    db.session.delete(post)
    db.session.commit()

    return jsonify({"message": "Post deleted"}), 200

@app.route("/posts", methods=["GET"])
@token_required
def get_posts(current_user):
    posts = Post.query.order_by(Post.id.desc()).all()

    return jsonify([
        {
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "media": post.media,
            "media_type": post.media_type,
            "created_at": post.created_at,
            "author": {
                "id": post.author.id,
                "username": post.author.username,
                "image": post.author.profile_image
            },
            "comments": [
                {
                    "id": c.id,
                    "content": c.content,
                    "user": c.user.username,
                    "user_id": c.user.id,
                    "user_pfp": c.user.profile_image
                }
                for c in post.comments
            ],
            "likes": len(post.likes),
            "liked_by_me": any(l.user_id == current_user.id for l in post.likes)
        }
        for post in posts
    ])

# ----------------------
# Comments, Likes, Users
# ----------------------

@app.route("/posts/<int:post_id>/comments", methods=["POST"])
@token_required
def add_comment(current_user, post_id):
    data = request.get_json()
    content = data.get("content")

    if not content:
        return jsonify({"error": "Comment content required"}), 400

    post = Post.query.get_or_404(post_id)

    comment = Comment(
        content=content,
        user_id=current_user.id,
        post_id=post.id
    )

    db.session.add(comment)
    db.session.commit()

    return jsonify({
        "message": "Comment added",
        "comment": {
            "id": comment.id,
            "content": comment.content,
            "user": current_user.username,
            "user_id": current_user.id
        }
    }), 201

@app.route("/comments/<int:comment_id>", methods=["DELETE"])
@token_required
def delete_comment(current_user, comment_id):
    comment = Comment.query.get_or_404(comment_id)

    if comment.user_id != current_user.id:
        return jsonify({"error": "You are not allowed to delete this comment"}), 403

    db.session.delete(comment)
    db.session.commit()

    return jsonify({"message": "Comment deleted"}), 200

@app.route("/posts/<int:post_id>/comments", methods=["GET"])
def get_comments(post_id):
    post = Post.query.get_or_404(post_id)

    return jsonify([
        {
            "id": c.id,
            "content": c.content,
            "user": c.user.username,
            "user_id": c.user.id,
            "created_at": c.created_at
        }
        for c in post.comments
    ])

@app.route("/posts/<int:post_id>/like", methods=["POST"])
@token_required
def toggle_like(current_user, post_id):
    post = Post.query.get_or_404(post_id)

    existing_like = Like.query.filter_by(
        user_id=current_user.id,
        post_id=post.id
    ).first()

    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        return jsonify({"message": "Post unliked"}), 200

    like = Like(
        user_id=current_user.id,
        post_id=post.id
    )
    db.session.add(like)
    db.session.commit()

    return jsonify({"message": "Post liked"}), 201

@app.route("/posts/<int:post_id>/likes", methods=["GET"])
def get_likes(post_id):
    post = Post.query.get_or_404(post_id)

    return jsonify({
        "post_id": post.id,
        "likes": len(post.likes)
    })

@app.route("/users/<int:user_id>", methods=["GET"])
@token_required
def get_user_profile(current_user, user_id):
    user = User.query.get_or_404(user_id)

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "bio": user.bio,
        "profile_image": user.profile_image,
        "posts": [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
                "media": p.media,
                "media_type": p.media_type,
                "created_at": p.created_at,
                "liked_by_me": any(l.user_id == current_user.id for l in p.likes),
                "author": {
                    "id": user.id,
                    "username": user.username,
                    "image": user.profile_image
                },
                "comments": [
                    {
                        "id": c.id,
                        "content": c.content,
                        "user": c.user.username,
                        "user_id": c.user.id,
                        "user_pfp": c.user.profile_image
                    }
                    for c in p.comments
                ],
                "likes": len(p.likes)
            }
            for p in user.posts
        ]
    })

@app.route("/users/<int:user_id>", methods=["PUT"])
@token_required
def update_profile(current_user, user_id):
    if current_user.id != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    username = request.form.get("username")
    bio = request.form.get("bio")
    file = request.files.get("profile_image")

    if username and username != current_user.username:
        exists = User.query.filter(User.username == username, User.id != current_user.id).first()
        if exists:
            return jsonify({"error": "ეს username უკვე არსებობს"}), 409
        current_user.username = username

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        current_user.profile_image = filename

    if len(bio) > 50:
        return jsonify({"error": "ბიო უნდა შეიცავდეს მაქსიმუმ 50 სიმბოლოს"}), 400

    if bio is not None:
        current_user.bio = bio

    db.session.commit()
    return jsonify({"message": "Profile updated"})

@app.route("/users", methods=["GET"])
@token_required
def get_users(current_user):
    users = User.query.all()
    return jsonify([
        {
            "id": u.id,
            "username": u.username,
            "profile_image": u.profile_image,
            "role": u.role,
            "bio": u.bio
        }
        for u in users
    ])

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')
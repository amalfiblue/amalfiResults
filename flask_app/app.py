import os
import sys
import json
import sqlite3
import datetime
import base64
from pathlib import Path
from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
    flash,
    session,
    get_flashed_messages,
    g,
)
from flask_socketio import SocketIO, emit
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import threading
import time

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.aec_data_downloader import (
    download_and_process_aec_data,
    get_candidates_for_electorate,
)
from utils.booth_results_processor import (
    process_and_load_polling_places,
    get_polling_places_for_division,
)

load_dotenv()

FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://localhost:8000")


def api_call(endpoint, method="get", data=None, params=None):
    """Make an API call to the FastAPI service with robust DNS resolution"""
    # Try multiple methods to resolve the FastAPI service
    fastapi_urls = []

    if FASTAPI_URL:
        fastapi_urls.append(FASTAPI_URL)

    try:
        import socket

        ip = socket.gethostbyname("results_fastapi_app")
        fastapi_urls.append(f"http://{ip}:8000")
    except Exception as e:
        app.logger.warning(
            f"Could not resolve results_fastapi_app via gethostbyname: {e}"
        )

    try:
        import socket

        addrinfo = socket.getaddrinfo(
            "results_fastapi_app", 8000, socket.AF_INET, socket.SOCK_STREAM
        )
        if addrinfo:
            ip = addrinfo[0][4][0]
            fastapi_urls.append(f"http://{ip}:8000")
    except Exception as e:
        app.logger.warning(
            f"Could not resolve results_fastapi_app via getaddrinfo: {e}"
        )

    try:
        import subprocess

        result = subprocess.run(
            ["getent", "hosts", "results_fastapi_app"], capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout:
            ip = result.stdout.split()[0]
            fastapi_urls.append(f"http://{ip}:8000")
    except Exception as e:
        app.logger.warning(f"Could not resolve results_fastapi_app via getent: {e}")

    fastapi_urls.append("http://localhost:8000")

    seen = set()
    fastapi_urls = [x for x in fastapi_urls if not (x in seen or seen.add(x))]

    last_error = None
    for base_url in fastapi_urls:
        url = f"{base_url}{endpoint}"
        try:
            app.logger.info(f"Trying FastAPI URL: {url}")
            if method.lower() == "get":
                response = requests.get(url, params=params, timeout=5)
            elif method.lower() == "post":
                response = requests.post(url, json=data, timeout=5)
            elif method.lower() == "delete":
                response = requests.delete(url, timeout=5)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            app.logger.info(f"Successfully connected to FastAPI at {base_url}")
            return response.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            app.logger.warning(f"Failed to connect to {base_url}: {e}")
            continue

    app.logger.error(f"All API connection attempts failed. Last error: {last_error}")
    return {"status": "error", "message": str(last_error)}


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev_key_for_amalfi_results")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///results.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "info"

app.config["IS_ADMIN"] = False


class Result:
    """Plain Python class to replace SQLAlchemy model"""

    def __init__(
        self,
        id=None,
        image_url=None,
        timestamp=None,
        electorate=None,
        booth_name=None,
        data=None,
        is_reviewed=0,
        reviewer=None,
    ):
        self.id = id
        self.image_url = image_url
        self.timestamp = timestamp
        self.electorate = electorate
        self.booth_name = booth_name
        self.data = data
        self.is_reviewed = is_reviewed
        self.reviewer = reviewer

    def to_dict(self):
        return {
            "id": self.id,
            "image_url": self.image_url,
            "timestamp": (
                self.timestamp.isoformat()
                if isinstance(self.timestamp, datetime.datetime)
                else self.timestamp
            ),
            "electorate": self.electorate,
            "booth_name": self.booth_name,
            "data": self.data,
            "is_reviewed": self.is_reviewed,
            "reviewer": self.reviewer,
        }

    def get_primary_votes(self):
        """Get primary votes from data JSON"""
        if self.data and "primary_votes" in self.data:
            return self.data["primary_votes"]
        return {}

    def get_tcp_votes(self):
        """Get two-candidate preferred votes from data JSON"""
        if self.data:
            if "tcp_votes" in self.data:
                return self.data["tcp_votes"]
            elif "two_candidate_preferred" in self.data:
                return self.data["two_candidate_preferred"]
        return {}

    def get_totals(self):
        """Get vote totals from data JSON"""
        if self.data and "totals" in self.data:
            return self.data["totals"]
        return {"formal": None, "informal": None, "total": None}


class TCPCandidate:
    """Plain Python class to replace SQLAlchemy model"""

    def __init__(
        self,
        id=None,
        electorate=None,
        candidate_id=None,
        candidate_name=None,
        position=None,
    ):
        self.id = id
        self.electorate = electorate
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name
        self.position = position

    def to_dict(self):
        return {
            "id": self.id,
            "electorate": self.electorate,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "position": self.position,
        }


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    division = db.Column(
        db.String(100), nullable=True
    )  # Null means root user with access to all divisions
    is_approved = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "division": self.division,
            "is_approved": self.is_approved,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if the password matches"""
        return check_password_hash(self.password_hash, password)

    def has_access_to_division(self, division):
        """Check if user has access to a specific division"""
        if self.division is None:
            return True
        return self.division == division


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_root_user():
    """Create the root user if it doesn't exist"""
    root_email = "andrew.waites@amalfination.com"
    root_password = os.environ.get("ROOT_PWD", "development_password")

    root_user = User.query.filter_by(email=root_email).first()
    if not root_user:
        root_user = User(
            email=root_email,
            division=None,  # No division means access to all
            is_approved=True,
            is_admin=True,
        )
        root_user.set_password(root_password)
        db.session.add(root_user)
        db.session.commit()
        app.logger.info(f"Root user {root_email} created")


with app.app_context():
    db.create_all()
    create_root_user()


def get_all_electorates():
    """Get all unique electorates - frontend directly queries FastAPI"""
    # Return empty list - frontend will populate via direct API call
    return []


def get_candidates(electorate=None, candidate_type=None):
    """Get candidates - frontend directly queries FastAPI"""
    # Return empty list - frontend will populate via direct API call
    return []


def get_last_updated_time():
    """Get the last updated time for AEC data"""
    try:
        data_dir = Path(__file__).parent.parent / "data"
        senate_path = data_dir / "senate-candidates.csv"
        house_path = data_dir / "house-candidates.csv"
        booth_results_path = data_dir / "HouseTppByPollingPlaceDownload-27966.csv"

        files_to_check = [senate_path, house_path, booth_results_path]

        timestamps = []
        for file_path in files_to_check:
            if file_path.exists():
                timestamps.append(
                    datetime.datetime.fromtimestamp(file_path.stat().st_mtime)
                )

        if timestamps:
            return max(timestamps).strftime("%Y-%m-%d %H:%M:%S")
        return "Never"
    except Exception as e:
        app.logger.error(f"Error getting last updated time: {e}")
        return "Unknown"


@app.route("/")
def index():
    """Redirect to dashboard as the default landing page"""
    return redirect(url_for("get_dashboard"))


@app.route("/results")
def get_results():
    """Get all results page - frontend directly queries FastAPI"""
    # Initialize empty results list - frontend will populate via direct API call
    results = []

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "results_new.html",
        results=results,
        messages=messages,
        is_admin=current_user.is_admin if hasattr(current_user, "is_admin") else False,
    )


@app.route("/results/<int:result_id>")
def get_result_detail(result_id):
    """Get result detail page - frontend directly queries FastAPI"""
    # Initialize empty result object - frontend will populate via direct API call
    result = Result()
    result.id = result_id

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "result_detail_new.html",
        result=result,
        messages=messages,
        is_admin=current_user.is_admin if hasattr(current_user, "is_admin") else False,
    )


@app.route("/candidates")
def get_candidates_page():
    electorate = request.args.get("electorate", "")
    candidate_type = request.args.get("candidate_type", "")

    candidates_data = get_candidates(electorate, candidate_type)
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "candidates_new.html",
        candidates=candidates_data,
        electorates=electorates,
        electorate=electorate,
        candidate_type=candidate_type,
        last_updated=last_updated,
        messages=messages,
        is_admin=current_user.is_admin if hasattr(current_user, "is_admin") else False,
    )


@app.route("/update-aec-data")
def update_aec_data():
    try:
        success = download_and_process_aec_data()
        if success:
            flash("AEC data updated successfully!", "success")
        else:
            flash("Failed to update AEC data. Check logs for details.", "error")
    except Exception as e:
        app.logger.error(f"Error updating AEC data: {e}")
        flash(f"Error updating AEC data: {str(e)}", "error")

    return redirect(url_for("get_candidates_page"))


@app.route("/polling-places")
def get_polling_places_page():
    """Get polling places page - frontend directly queries FastAPI"""
    electorate = request.args.get("electorate", "")
    booth = request.args.get("booth", "")

    electorates = get_all_electorates()
    last_updated = get_last_updated_time()

    # Check if user has access to the specified electorate
    if (
        electorate
        and hasattr(current_user, "is_authenticated")
        and current_user.is_authenticated
    ):
        if not current_user.has_access_to_division(electorate):
            flash(f"You don't have access to {electorate}", "error")
            return redirect(url_for("index"))

    # Initialize empty arrays - frontend will populate via direct API call
    polling_places = []
    current_results = []

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "polling_places.html",
        polling_places=polling_places,
        current_results=current_results,
        electorates=electorates,
        electorate=electorate,
        booth=booth,
        last_updated=last_updated,
        messages=messages,
        is_admin=current_user.is_admin if hasattr(current_user, "is_admin") else False,
    )


@app.route("/update-polling-places-data")
def update_polling_places_data():
    try:
        success = process_and_load_polling_places()
        if success:
            flash("Polling places data updated successfully!", "success")
        else:
            flash(
                "Failed to update polling places data. Check logs for details.", "error"
            )
    except Exception as e:
        app.logger.error(f"Error updating polling places data: {e}")
        flash(f"Error updating polling places data: {str(e)}", "error")

    return redirect(url_for("get_polling_places_page"))


@app.route("/dashboard")
@app.route("/dashboard/<electorate>")
@login_required
def get_dashboard(electorate=None):
    """Electorate dashboard showing live results - frontend directly queries FastAPI"""
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()

    if not electorate:
        for e in electorates:
            if current_user.has_access_to_division(e):
                electorate = e
                break
        if not electorate and electorates:
            if not current_user.is_admin:
                flash("You don't have access to any electorate", "error")
                return redirect(url_for("index"))
            # Admin users can see any electorate
            electorate = electorates[0]

    # Check if user has access to the specified electorate
    if electorate and not current_user.has_access_to_division(electorate):
        flash(f"You don't have access to {electorate}", "error")
        return redirect(url_for("index"))

    # Initialize empty data structures - data will be loaded by frontend directly from FastAPI
    booth_counts = {}
    total_booths = {}
    booth_results = []
    primary_votes_array = []
    tcp_votes_array = []

    # Get polling places counts for each electorate
    for e in electorates:
        polling_places = get_polling_places_for_division(e)
        total_booths[e] = len(polling_places) if polling_places else 0
        booth_counts[e] = 0  # Will be populated by frontend

    if not electorate:
        electorate = session.get("default_division")

    if not electorate and electorates:
        electorate = electorates[0]

    if electorate:
        session["last_viewed_division"] = electorate

    is_admin = current_user.is_admin if hasattr(current_user, "is_admin") else False

    return render_template(
        "electorate_dashboard.html",
        electorates=electorates,
        selected_electorate=electorate,
        booth_results=booth_results,
        primary_votes=primary_votes_array,
        tcp_votes=tcp_votes_array,
        booth_counts=booth_counts,
        total_booths=total_booths,
        last_updated=last_updated,
        is_admin=is_admin,
    )


@app.route("/admin/tcp-candidates", methods=["GET"])
@app.route("/admin/tcp-candidates/<electorate>", methods=["GET", "POST"])
@login_required
def admin_tcp_candidates(electorate=None):
    """Admin page to set TCP candidates for an electorate - frontend directly queries FastAPI"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("get_dashboard"))

    # If no electorate is specified, redirect to the first available electorate
    if electorate is None:
        electorates = get_all_electorates()
        if electorates:
            return redirect(url_for("admin_tcp_candidates", electorate=electorates[0]))
        else:
            flash("No electorates available", "error")
            return redirect(url_for("get_dashboard"))

    if request.method == "POST":
        return redirect(url_for("admin_tcp_candidates", electorate=electorate))

    # Initialize empty arrays - frontend will populate via direct API call
    candidates = []
    tcp_candidate_names = []

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "admin_tcp_candidates_new.html",
        electorate=electorate,
        candidates=candidates,
        tcp_candidates=tcp_candidate_names,
        messages=messages,
        electorates=get_all_electorates(),
        selected_electorate=electorate,
        is_admin=app.config.get("IS_ADMIN", False),
    )


@app.route("/api/notify", methods=["POST"])
def notify():
    """Endpoint for FastAPI to notify of new results"""
    data = request.json
    app.logger.info(f"Received notification: {data}")

    if "electorate" in data:
        socketio.emit(
            "update", {"electorate": data["electorate"]}, namespace="/dashboard"
        )

    return jsonify({"status": "success", "message": "Notification received"})


@socketio.on("connect", namespace="/dashboard")
def dashboard_connect():
    app.logger.info(f"Client connected to dashboard: {request.sid}")


@socketio.on("disconnect", namespace="/dashboard")
def dashboard_disconnect():
    app.logger.info(f"Client disconnected from dashboard: {request.sid}")


@socketio.on("join", namespace="/dashboard")
def dashboard_join(data):
    """Join a specific electorate's dashboard room"""
    if "electorate" in data:
        app.logger.info(f"Client {request.sid} joined electorate: {data['electorate']}")
        socketio.emit(
            "status",
            {"status": "connected", "electorate": data["electorate"]},
            to=request.sid,
        )


@app.route("/admin/polling-places", methods=["GET"])
@app.route("/admin/polling-places/<division>", methods=["GET"])
@login_required
def admin_polling_places(division=None):
    """Admin page to view polling places for a division and manage results - frontend directly queries FastAPI"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("get_dashboard"))

    if not division and request.args.get("division"):
        division = request.args.get("division")

    electorates = get_all_electorates()

    if not division and electorates:
        division = electorates[0]

    # Check if user has access to the specified division
    if division and not current_user.has_access_to_division(division):
        flash(f"You don't have access to {division}", "error")
        return redirect(url_for("index"))

    polling_places = []
    if division:
        from utils.booth_results_processor import get_polling_places_for_division

        polling_places = get_polling_places_for_division(division)
        app.logger.info(
            f"Retrieved {len(polling_places)} polling places for division {division}"
        )
        if polling_places:
            app.logger.info(f"First polling place: {polling_places[0]}")

    # Initialize empty arrays - data will be loaded by frontend directly from FastAPI
    current_results = []
    unreviewed_results = []

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "admin_polling_places.html",
        division=division,
        electorates=electorates,
        polling_places=polling_places,
        current_results=current_results,
        unreviewed_results=unreviewed_results,
        messages=messages,
        is_admin=current_user.is_admin,
    )


@app.route("/admin/reset-results", methods=["POST"])
@login_required
def admin_reset_results():
    """Reset results for testing purposes - frontend directly calls FastAPI"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("get_dashboard"))

    division = request.form.get("division")

    return redirect(url_for("admin_polling_places", division=division))


@app.route("/admin/review-result/<int:result_id>", methods=["GET", "POST"])
@login_required
def admin_review_result(result_id):
    """Admin page to review and approve a result - frontend directly queries FastAPI"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("get_dashboard"))

    # Initialize empty result - data will be loaded by frontend directly from FastAPI
    result = Result(
        id=result_id,
        image_url="",
        timestamp=datetime.datetime.now(),
        electorate="",
        booth_name="",
        data={},
    )

    if request.method == "POST":
        action = request.form.get("action")
        electorate = request.form.get("electorate")

        if electorate:
            socketio.emit("update", {"electorate": electorate}, namespace="/dashboard")

            if action == "approve":
                flash("Result approved successfully", "success")
            elif action == "reject":
                flash("Result rejected", "warning")

            return redirect(url_for("admin_polling_places", division=electorate))
        else:
            flash("Missing electorate information", "error")

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "admin_review_result_new.html",
        result=result,
        messages=messages,
        electorates=get_all_electorates(),
        selected_electorate="",
        is_admin=current_user.is_admin,
    )


@app.route("/admin/panel", methods=["GET"])
@app.route("/admin/panel/<division>", methods=["GET"])
@login_required
def admin_panel(division=None):
    """Admin panel that uses FastAPI endpoints for actions"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("get_dashboard"))

    electorates = get_all_electorates()

    if not division and electorates:
        division = electorates[0]

    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))

    return render_template(
        "admin_panel_new.html",
        division=division,
        electorates=electorates,
        messages=messages,
        selected_electorate=division,
        is_admin=app.config.get("IS_ADMIN", False),
    )


@app.route("/api/notify", methods=["POST"])
def api_notify():
    """Endpoint for FastAPI to notify Flask app of updates"""
    data = request.json
    app.logger.info(f"Received notification from FastAPI: {data}")

    result_id = data.get("result_id")
    electorate = data.get("electorate")
    action = data.get("action")

    if electorate:
        socketio.emit("update", {"electorate": electorate}, namespace="/dashboard")

        if action == "review":
            approved = data.get("approved", False)
            status = "approved" if approved else "rejected"
            socketio.emit(
                "result_reviewed",
                {"result_id": result_id, "electorate": electorate, "status": status},
                namespace="/dashboard",
            )


@app.before_request
def before_request():
    """Set up global variables and session data"""
    g.is_admin = current_user.is_authenticated and current_user.is_admin

    # Set default division from session if not set
    if "default_division" not in session and current_user.is_authenticated:
        session["default_division"] = current_user.division or "Warringah"

    # Make selected division available to templates
    g.selected_division = session.get("default_division", "Warringah")


@app.route("/set-default-division")
def set_default_division():
    """Set the default division for the user session"""
    division = request.args.get("division")
    next_url = request.args.get("next", url_for("get_dashboard"))

    if division:
        session["default_division"] = division
        flash(f"Default division set to {division}", "success")

    return redirect(next_url)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if not user.is_approved:
                flash("Your account is pending approval", "warning")
                return redirect(url_for("login"))

            login_user(user)

            app.config["IS_ADMIN"] = user.is_admin

            next_page = request.args.get("next")
            return redirect(next_page or url_for("index"))
        else:
            flash("Invalid email or password", "danger")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """Logout user"""
    logout_user()
    app.config["IS_ADMIN"] = False
    flash("You have been logged out", "success")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    electorates = get_all_electorates()

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        division = request.form.get("division")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered", "danger")
            return render_template("register.html", electorates=electorates)

        user = User(email=email, division=division, is_approved=False, is_admin=False)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Your account is pending approval.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", electorates=electorates)


@app.route("/admin/users")
@login_required
def admin_users():
    """Admin page to manage user registrations"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("index"))

    pending_users = User.query.filter_by(is_approved=False).all()
    approved_users = User.query.filter_by(is_approved=True).all()

    return render_template(
        "admin_users.html",
        pending_users=pending_users,
        approved_users=approved_users,
        is_admin=current_user.is_admin,
    )


@app.route("/admin/users/<int:user_id>/approve", methods=["POST"])
@login_required
def approve_user(user_id):
    """Approve a user registration"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("index"))

    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()

    flash(f"User {user.email} approved", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reject", methods=["POST"])
@login_required
def reject_user(user_id):
    """Reject and delete a user registration"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("index"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()

    flash(f"User {user.email} rejected", "success")
    return redirect(url_for("admin_users"))


@app.route("/load-reference-data")
@login_required
def load_reference_data():
    """Load reference data - frontend directly calls FastAPI"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("index"))

    flash("Reference data loading initiated. Please wait...", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/upload-image", methods=["POST"])
@login_required
def admin_upload_image():
    """Upload an image file and send it to FastAPI for processing"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for("index"))

    if "image" not in request.files:
        flash("No image file provided", "error")
        return redirect(url_for("admin_panel"))

    image_file = request.files["image"]

    if image_file.filename == "":
        flash("No image file selected", "error")
        return redirect(url_for("admin_panel"))

    try:
        files = {
            "file": (image_file.filename, image_file.read(), image_file.content_type)
        }

        response = None
        fastapi_urls = []

        if FASTAPI_URL:
            fastapi_urls.append(FASTAPI_URL)

        fastapi_urls.append("http://results_fastapi_app:8000")

        try:
            import socket

            ip = socket.gethostbyname("results_fastapi_app")
            fastapi_urls.append(f"http://{ip}:8000")
        except Exception as e:
            app.logger.warning(
                f"Could not resolve results_fastapi_app via gethostbyname: {e}"
            )

        try:
            import socket

            addrinfo = socket.getaddrinfo(
                "results_fastapi_app", 8000, socket.AF_INET, socket.SOCK_STREAM
            )
            if addrinfo:
                ip = addrinfo[0][4][0]
                fastapi_urls.append(f"http://{ip}:8000")
        except Exception as e:
            app.logger.warning(
                f"Could not resolve results_fastapi_app via getaddrinfo: {e}"
            )

        try:
            import subprocess

            result = subprocess.run(
                ["getent", "hosts", "results_fastapi_app"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout:
                ip = result.stdout.split()[0]
                fastapi_urls.append(f"http://{ip}:8000")
        except Exception as e:
            app.logger.warning(f"Could not resolve results_fastapi_app via getent: {e}")

        fastapi_urls.append("http://localhost:8000")

        seen = set()
        fastapi_urls = [x for x in fastapi_urls if not (x in seen or seen.add(x))]

        last_error = None
        for base_url in fastapi_urls:
            url = f"{base_url}/scan-image"
            try:
                app.logger.info(f"Trying to upload image to FastAPI URL: {url}")
                response = requests.post(url, files=files, timeout=30)
                response.raise_for_status()
                app.logger.info(f"Successfully uploaded image to FastAPI at {base_url}")
                break
            except requests.exceptions.RequestException as e:
                last_error = e
                app.logger.warning(f"Failed to connect to {base_url}: {e}")
                continue

        if response is None or response.status_code != 200:
            flash(f"Failed to process image: {last_error}", "error")
            return redirect(url_for("admin_panel"))

        result_data = response.json()
        if result_data.get("status") == "success":
            result_id = result_data.get("result_id")
            flash("Image processed successfully!", "success")
            return redirect(url_for("admin_review_result", result_id=result_id))
        else:
            flash(
                f"Error processing image: {result_data.get('message', 'Unknown error')}",
                "error",
            )
            return redirect(url_for("admin_panel"))

    except Exception as e:
        app.logger.error(f"Error processing image upload: {e}", exc_info=True)
        flash(f"Error processing image: {str(e)}", "error")
        return redirect(url_for("admin_panel"))


@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def api_proxy(path):
    """Proxy all /api/* requests to the FastAPI server"""
    method = request.method
    app.logger.info(f"Proxying {method} request to /{path}")

    try:
        if method.lower() == "get":
            response = api_call(f"/{path}", method="get", params=request.args)
            return jsonify(response)
        elif method.lower() == "post":
            data = request.get_json(silent=True)
            response = api_call(f"/{path}", method="post", data=data)
            return jsonify(response)
        elif method.lower() == "put":
            data = request.get_json(silent=True)
            response = api_call(f"/{path}", method="put", data=data)
            return jsonify(response)
        elif method.lower() == "delete":
            response = api_call(f"/{path}", method="delete")
            return jsonify(response)
        else:
            return (
                jsonify(
                    {"status": "error", "message": f"Unsupported method: {method}"}
                ),
                405,
            )
    except Exception as e:
        app.logger.error(f"Error proxying {method} request to /{path}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    socketio.run(
        app,
        debug=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        allow_unsafe_werkzeug=True,
        use_reloader=True,
        log_output=True,
    )

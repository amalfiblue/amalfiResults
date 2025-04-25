import os
import sys
import json
import sqlite3
import datetime
import base64
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session, get_flashed_messages
from flask_socketio import SocketIO, emit
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import threading
import time

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.aec_data_downloader import download_and_process_aec_data, get_candidates_for_electorate
from utils.booth_results_processor import process_and_load_booth_results, get_booth_results_for_division, get_booth_results_for_polling_place, calculate_swing

load_dotenv()

FASTAPI_URL = os.environ.get('FASTAPI_URL', 'http://localhost:8000')

def api_call(endpoint, method='get', data=None, params=None):
    """Make an API call to the FastAPI service"""
    url = f"{FASTAPI_URL}{endpoint}"
    try:
        if method.lower() == 'get':
            response = requests.get(url, params=params)
        elif method.lower() == 'post':
            response = requests.post(url, json=data)
        elif method.lower() == 'delete':
            response = requests.delete(url)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        app.logger.error(f"API call error: {e}")
        return {"status": "error", "message": str(e)}


app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_amalfi_results')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///amalfi_results.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

app.config['IS_ADMIN'] = False

class Result:
    """Plain Python class to replace SQLAlchemy model"""
    
    def __init__(self, id=None, image_url=None, timestamp=None, electorate=None, booth_name=None, data=None):
        self.id = id
        self.image_url = image_url
        self.timestamp = timestamp
        self.electorate = electorate
        self.booth_name = booth_name
        self.data = data

    def to_dict(self):
        return {
            'id': self.id,
            'image_url': self.image_url,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime.datetime) else self.timestamp,
            'electorate': self.electorate,
            'booth_name': self.booth_name,
            'data': self.data
        }
        
    def get_primary_votes(self):
        """Get primary votes from data JSON"""
        if self.data and 'primary_votes' in self.data:
            return self.data['primary_votes']
        return {}
    
    def get_tcp_votes(self):
        """Get two-candidate preferred votes from data JSON"""
        if self.data:
            if 'tcp_votes' in self.data:
                return self.data['tcp_votes']
            elif 'two_candidate_preferred' in self.data:
                return self.data['two_candidate_preferred']
        return {}
    
    def get_totals(self):
        """Get vote totals from data JSON"""
        if self.data and 'totals' in self.data:
            return self.data['totals']
        return {'formal': None, 'informal': None, 'total': None}

class TCPCandidate:
    """Plain Python class to replace SQLAlchemy model"""
    
    def __init__(self, id=None, electorate=None, candidate_id=None, candidate_name=None, position=None):
        self.id = id
        self.electorate = electorate
        self.candidate_id = candidate_id
        self.candidate_name = candidate_name
        self.position = position
    
    def to_dict(self):
        return {
            'id': self.id,
            'electorate': self.electorate,
            'candidate_id': self.candidate_id,
            'candidate_name': self.candidate_name,
            'position': self.position
        }

class User(db.Model, UserMixin):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    division = db.Column(db.String(100), nullable=True)  # Null means root user with access to all divisions
    is_approved = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'division': self.division,
            'is_approved': self.is_approved,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None
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
    root_password = "dragonSneezer"
    
    root_user = User.query.filter_by(email=root_email).first()
    if not root_user:
        root_user = User(
            email=root_email,
            division=None,  # No division means access to all
            is_approved=True,
            is_admin=True
        )
        root_user.set_password(root_password)
        db.session.add(root_user)
        db.session.commit()
        app.logger.info(f"Root user {root_email} created")

with app.app_context():
    db.create_all()
    create_root_user()


def get_all_electorates():
    """Get all unique electorates from the candidates table via FastAPI"""
    try:
        response = api_call("/api/electorates")
        if response.get("status") == "success":
            return response.get("electorates", [])
        else:
            app.logger.error(f"Error getting electorates: {response.get('message')}")
            return []
    except Exception as e:
        app.logger.error(f"Error getting electorates: {e}")
        return []

def get_candidates(electorate=None, candidate_type=None):
    """Get candidates from the FastAPI service with optional filtering"""
    try:
        if electorate:
            params = {"candidate_type": candidate_type} if candidate_type else {}
            response = api_call(f"/api/candidates/{electorate}", params=params)
        else:
            response = api_call("/api/candidates")
        
        if response.get("status") == "success":
            return response.get("candidates", [])
        else:
            app.logger.error(f"Error getting candidates: {response.get('message')}")
            return []
    except Exception as e:
        app.logger.error(f"Error getting candidates: {e}")
        return []

def get_last_updated_time():
    """Get the last updated time for AEC data"""
    try:
        data_dir = Path(__file__).parent.parent / "data"
        senate_path = data_dir / "senate-candidates.csv"
        house_path = data_dir / "house-candidates.csv"
        booth_results_path = data_dir / "HouseTppByPollingPlaceDownload-27966.csv"
        
        files_to_check = [
            senate_path,
            house_path,
            booth_results_path
        ]
        
        timestamps = []
        for file_path in files_to_check:
            if file_path.exists():
                timestamps.append(datetime.datetime.fromtimestamp(file_path.stat().st_mtime))
        
        if timestamps:
            return max(timestamps).strftime("%Y-%m-%d %H:%M:%S")
        return "Never"
    except Exception as e:
        app.logger.error(f"Error getting last updated time: {e}")
        return "Unknown"

@app.route('/')
def index():
    """Redirect to dashboard as the default landing page"""
    return redirect(url_for('get_dashboard'))

@app.route('/results')
def get_results():
    """Get all results page using FastAPI endpoint"""
    response = api_call("/api/results")
    results = []
    if response.get("status") == "success":
        for r in response.get("results", []):
            result = Result(
                id=r["id"],
                image_url=r["image_url"],
                timestamp=datetime.datetime.fromisoformat(r["timestamp"]),
                electorate=r["electorate"],
                booth_name=r["booth_name"],
                data=r["data"]
            )
            results.append(result)
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template('results_new.html', results=results, messages=messages)

@app.route('/results/<int:result_id>')
def get_result_detail(result_id):
    """Get result detail page using FastAPI endpoint"""
    response = api_call(f"/api/results/{result_id}")
    if response.get("status") == "success":
        r = response.get("result")
        result = Result(
            id=r["id"],
            image_url=r["image_url"],
            timestamp=datetime.datetime.fromisoformat(r["timestamp"]),
            electorate=r["electorate"],
            booth_name=r["booth_name"],
            data=r["data"]
        )
        
        messages = []
        for category, message in get_flashed_messages(with_categories=True):
            messages.append((category, message))
        
        return render_template('result_detail_new.html', result=result, messages=messages)
    else:
        return render_template('error.html', error=f"Result not found: {response.get('message')}")


@app.route('/candidates')
def get_candidates_page():
    electorate = request.args.get('electorate', '')
    candidate_type = request.args.get('candidate_type', '')
    
    candidates_data = get_candidates(electorate, candidate_type)
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'candidates_new.html', 
        candidates=candidates_data, 
        electorates=electorates,
        electorate=electorate,
        candidate_type=candidate_type,
        last_updated=last_updated,
        messages=messages
    )

@app.route('/update-aec-data')
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
    
    return redirect(url_for('get_candidates_page'))

@app.route('/api/results')
def api_results():
    """Proxy API call to FastAPI service for all results"""
    response = api_call("/api/results")
    if response.get("status") == "success":
        return jsonify(response.get("results", []))
    return jsonify([])

@app.route('/api/results/<int:result_id>')
def api_result_detail(result_id):
    """Proxy API call to FastAPI service for a specific result"""
    response = api_call(f"/api/results/{result_id}")
    if response.get("status") == "success":
        return jsonify(response.get("result", {}))
    return jsonify({})

@app.route('/api/candidates')
def api_candidates():
    electorate = request.args.get('electorate', '')
    candidate_type = request.args.get('candidate_type', '')
    candidates_data = get_candidates(electorate, candidate_type)
    return jsonify(candidates_data)

@app.route('/api/electorates')
def api_electorates():
    electorates = get_all_electorates()
    return jsonify(electorates)

@app.route('/booth-results')
def get_booth_results_page():
    electorate = request.args.get('electorate', '')
    booth = request.args.get('booth', '')
    
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()
    
    booth_results = []
    if electorate:
        booth_results = get_booth_results_for_division(electorate)
        if booth and booth.strip():
            booth_results = [r for r in booth_results if booth.lower() in r['polling_place_name'].lower()]
    
    # Get results from FastAPI service
    params = {}
    if electorate:
        params['electorate'] = electorate
    if booth:
        params['booth'] = booth
    
    response = api_call("/api/results", params=params)
    current_results = []
    
    if response.get("status") == "success":
        results_data = response.get("results", [])
        for result_data in results_data:
            result = Result()
            result.id = result_data.get("id")
            result.timestamp = datetime.datetime.fromisoformat(result_data.get("timestamp"))
            result.electorate = result_data.get("electorate")
            result.booth_name = result_data.get("booth_name")
            result.image_url = result_data.get("image_url")
            result.data = result_data.get("data", {})
            current_results.append(result)
    
    if booth_results and current_results:
        for booth_result in booth_results:
            matching_result = next(
                (r for r in current_results if r.booth_name and 
                 booth_result['polling_place_name'].lower() in r.booth_name.lower() or
                 r.booth_name.lower() in booth_result['polling_place_name'].lower()),
                None
            )
            
            if matching_result:
                tcp_votes = matching_result.get_tcp_votes()
                if tcp_votes and len(tcp_votes) >= 2:
                    liberal_votes = list(tcp_votes.values())[0]
                    labor_votes = list(tcp_votes.values())[1]
                    total_votes = liberal_votes + labor_votes
                    
                    if total_votes > 0:
                        liberal_pct = (liberal_votes / total_votes) * 100
                        labor_pct = (labor_votes / total_votes) * 100
                        
                        current_result_data = {
                            'liberal_national_percentage': liberal_pct,
                            'labor_percentage': labor_pct
                        }
                        
                        booth_result['current_swing'] = calculate_swing(
                            current_result_data, 
                            booth_result
                        )
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'booth_results_new.html',
        booth_results=booth_results,
        current_results=current_results,
        electorates=electorates,
        electorate=electorate,
        booth=booth,
        last_updated=last_updated,
        messages=messages
    )

@app.route('/update-booth-data')
def update_booth_data():
    try:
        success = process_and_load_booth_results()
        if success:
            flash("Booth results data updated successfully!", "success")
        else:
            flash("Failed to update booth results data. Check logs for details.", "error")
    except Exception as e:
        app.logger.error(f"Error updating booth results data: {e}")
        flash(f"Error updating booth results data: {str(e)}", "error")
    
    return redirect(url_for('get_booth_results_page'))

@app.route('/api/booth-results')
def api_booth_results():
    electorate = request.args.get('electorate', '')
    booth = request.args.get('booth', '')
    
    if not electorate:
        return jsonify({"error": "Electorate parameter is required"}), 400
    
    booth_results = get_booth_results_for_division(electorate)
    
    if booth:
        booth_results = [r for r in booth_results if booth.lower() in r['polling_place_name'].lower()]
    
    return jsonify(booth_results)

@app.route('/dashboard')
@app.route('/dashboard/<electorate>')
@login_required
def get_dashboard(electorate=None):
    """Electorate dashboard showing live results"""
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
                return redirect(url_for('index'))
            # Admin users can see any electorate
            electorate = electorates[0]
    
    # Check if user has access to the specified electorate
    if electorate and not current_user.has_access_to_division(electorate):
        flash(f"You don't have access to {electorate}", "error")
        return redirect(url_for('index'))
    
    # Get booth counts for each electorate
    booth_counts = {}
    total_booths = {}
    
    for e in electorates:
        # Get result count from FastAPI service
        response = api_call(f"/api/results/count/{e}")
        booth_counts[e] = response.get("count", 0) if response.get("status") == "success" else 0
        
        historical_booths = get_booth_results_for_division(e)
        total_booths[e] = len(historical_booths) if historical_booths else 0
    
    if not electorate:
        electorate = session.get('default_division')
        
    if not electorate and electorates:
        electorate = electorates[0]
        
    if electorate:
        session['last_viewed_division'] = electorate
    
    # Get booth results for the selected electorate
    booth_results = []
    primary_votes = {}
    tcp_votes = {}
    
    primary_votes_array = []
    tcp_votes_array = []
    
    if electorate:
        # Get dashboard data for this electorate from FastAPI service
        response = api_call(f"/api/dashboard/{electorate}")
        results = []
        
        if response.get("status") == "success":
            # Get booth results from the dashboard data
            booth_results_data = response.get("booth_results", [])
            for booth_data in booth_results_data:
                result = Result()
                result.id = booth_data.get("id")
                result.timestamp = datetime.datetime.fromisoformat(booth_data.get("timestamp")) if booth_data.get("timestamp") else datetime.datetime.now()
                result.electorate = electorate
                result.booth_name = booth_data.get("booth_name")
                result.image_url = booth_data.get("image_url")
                result.data = {
                    "primary_votes": booth_data.get("primary_votes", {}),
                    "tcp_votes": booth_data.get("tcp_votes", {}),
                    "totals": booth_data.get("totals", {"formal": 0, "informal": 0, "total": 0})
                }
                results.append(result)
        
        for result in results:
            booth_data = result.to_dict()
            booth_data['totals'] = result.get_totals()
            
            historical_booth = get_booth_results_for_polling_place(electorate, result.booth_name)
            if historical_booth:
                tcp_data = result.get_tcp_votes()
                if tcp_data and len(tcp_data) >= 2:
                    liberal_votes = list(tcp_data.values())[0]
                    labor_votes = list(tcp_data.values())[1]
                    total_votes = liberal_votes + labor_votes
                    
                    if total_votes > 0:
                        liberal_pct = (liberal_votes / total_votes) * 100
                        labor_pct = (labor_votes / total_votes) * 100
                        
                        current_result_data = {
                            'liberal_national_percentage': liberal_pct,
                            'labor_percentage': labor_pct
                        }
                        
                        booth_data['swing'] = calculate_swing(
                            current_result_data, 
                            historical_booth
                        )
            
            booth_results.append(booth_data)
        
        for result in results:
            primary_result = result.get_primary_votes()
            for candidate, votes in primary_result.items():
                if candidate in primary_votes:
                    primary_votes[candidate]['votes'] += votes
                else:
                    primary_votes[candidate] = {'votes': votes, 'percentage': 0}
        
        total_primary_votes = sum(item['votes'] for item in primary_votes.values())
        if total_primary_votes > 0:
            for candidate in primary_votes:
                primary_votes[candidate]['percentage'] = (primary_votes[candidate]['votes'] / total_primary_votes) * 100
        
        # Get TCP candidates from FastAPI service
        response = api_call(f"/api/tcp-candidates/{electorate}")
        tcp_candidates = []
        
        if response.get("status") == "success":
            candidates_data = response.get("candidates", [])
            for candidate_data in candidates_data:
                candidate = TCPCandidate()
                candidate.id = candidate_data.get("id")
                candidate.electorate = candidate_data.get("electorate")
                candidate.candidate_name = candidate_data.get("candidate_name")
                candidate.position = candidate_data.get("position")
                tcp_candidates.append(candidate)
                
        tcp_candidate_names = [c.candidate_name for c in tcp_candidates]
        
        for result in results:
            tcp_result = result.get_tcp_votes()
            
            if tcp_candidate_names and len(tcp_candidate_names) == 2:
                for i, candidate in enumerate(tcp_candidate_names):
                    if i < len(tcp_result):
                        votes = list(tcp_result.values())[i]
                        if candidate in tcp_votes:
                            tcp_votes[candidate]['votes'] += votes
                        else:
                            tcp_votes[candidate] = {'votes': votes, 'percentage': 0}
            else:
                for i, (candidate, votes) in enumerate(tcp_result.items()):
                    if i >= 2:  # Only use first two candidates
                        break
                    if candidate in tcp_votes:
                        tcp_votes[candidate]['votes'] += votes
                    else:
                        tcp_votes[candidate] = {'votes': votes, 'percentage': 0}
        
        total_tcp_votes = sum(item['votes'] for item in tcp_votes.values())
        if total_tcp_votes > 0:
            for candidate in tcp_votes:
                tcp_votes[candidate]['percentage'] = (tcp_votes[candidate]['votes'] / total_tcp_votes) * 100
    
        tcp_votes_array = []
        for candidate, data in tcp_votes.items():
            tcp_votes_array.append({
                'candidate': candidate,
                'votes': data['votes'],
                'percentage': data['percentage']
            })
        
        primary_votes_array = []
        for candidate, data in primary_votes.items():
            primary_votes_array.append({
                'candidate': candidate,
                'votes': data['votes'],
                'percentage': data['percentage']
            })
        else:
            app.logger.error(f"Error getting dashboard data: {response.get('message')}")
    
    is_admin = app.config.get('IS_ADMIN', False)
    
    return render_template(
        'electorate_dashboard.html',
        electorates=electorates,
        selected_electorate=electorate,
        booth_results=booth_results,
        primary_votes=primary_votes_array,
        tcp_votes=tcp_votes_array,
        booth_counts=booth_counts,
        total_booths=total_booths,
        last_updated=last_updated,
        is_admin=is_admin
    )

@app.route('/admin/tcp-candidates/<electorate>', methods=['GET', 'POST'])
@login_required
def admin_tcp_candidates(electorate):
    """Admin page to set TCP candidates for an electorate"""
    if not current_user.is_admin:

        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    if request.method == 'POST':
        candidate_ids = request.form.getlist('tcp_candidates')
        
        if len(candidate_ids) != 2:
            flash("You must select exactly two candidates for TCP counting", "error")
        else:
            try:
                candidate_ids = [int(cid) for cid in candidate_ids]
                
                # Use FastAPI endpoint to update TCP candidates
                response = api_call(
                    f"/api/tcp-candidates/{electorate}", 
                    method="post", 
                    data={"candidate_ids": candidate_ids}
                )
                
                if response.get("status") == "success":
                    flash("TCP candidates updated successfully", "success")
                    socketio.emit('tcp_update', {'electorate': electorate}, namespace='/dashboard')
                else:
                    app.logger.error(f"Error setting TCP candidates: {response.get('message')}")
                    flash(f"Error setting TCP candidates: {response.get('message')}", "error")
                
            except Exception as e:
                app.logger.error(f"Error setting TCP candidates: {e}")
                flash(f"Error setting TCP candidates: {str(e)}", "error")
        
        return redirect(url_for('admin_tcp_candidates', electorate=electorate))
    
    # Get candidates for this electorate
    candidates = get_candidates(electorate, 'house')
    
    # Get candidate votes from FastAPI
    response = api_call(f"/api/dashboard/{electorate}/candidate-votes")
    candidate_votes = {}
    if response.get("status") == "success":
        candidate_votes = response.get("candidate_votes", {})
    
    for candidate in candidates:
        candidate['votes'] = candidate_votes.get(candidate['name'], 0)
    
    # Get current TCP candidates from FastAPI
    response = api_call(f"/api/tcp-candidates/{electorate}")
    tcp_candidate_names = []
    if response.get("status") == "success":
        tcp_candidates = response.get("tcp_candidates", [])
        tcp_candidate_names = [c["candidate_name"] for c in tcp_candidates]
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_tcp_candidates_new.html',
        electorate=electorate,
        candidates=candidates,
        tcp_candidates=tcp_candidate_names,
        messages=messages,
        electorates=get_all_electorates(),
        selected_electorate=electorate,
        is_admin=app.config.get('IS_ADMIN', False)
    )

@app.route('/api/dashboard/<electorate>')
def api_dashboard(electorate):
    """API endpoint for dashboard data using FastAPI endpoints"""
    # Get dashboard data from FastAPI
    response = api_call(f"/api/dashboard/{electorate}")
    
    if response.get("status") != "success":
        app.logger.error(f"Error getting dashboard data: {response.get('message')}")
        return jsonify({
            'booth_count': 0,
            'total_booths': 0,
            'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'primary_votes': [],
            'tcp_votes': [],
            'booth_results': []
        })
    
    dashboard_data = response
    
    total_booths = dashboard_data.get("total_booths", 0)
    
    booth_results = dashboard_data.get("booth_results", [])
    for booth_data in booth_results:
        if booth_data.get("booth_name"):
            historical_booth = get_booth_results_for_polling_place(electorate, booth_data["booth_name"])
            if historical_booth and "tcp_votes" in booth_data:
                tcp_data = booth_data["tcp_votes"]
                if tcp_data and len(tcp_data) >= 2:
                    tcp_values = list(tcp_data.values())
                    if len(tcp_values) >= 2:
                        liberal_votes = tcp_values[0]
                        labor_votes = tcp_values[1]
                        total_votes = liberal_votes + labor_votes
                        
                        if total_votes > 0:
                            liberal_pct = (liberal_votes / total_votes) * 100
                            labor_pct = (labor_votes / total_votes) * 100
                            
                            current_result_data = {
                                'liberal_national_percentage': liberal_pct,
                                'labor_percentage': labor_pct
                            }
                            
                            booth_data['swing'] = calculate_swing(
                                current_result_data, 
                                historical_booth
                            )
    
    # Get the actual booth count from the booth_results
    booth_count = len(booth_results)
    
    tcp_votes_data = []
    tcp_votes_raw = dashboard_data.get("tcp_votes", [])
    
    # Check if tcp_votes is already in array format
    if isinstance(tcp_votes_raw, list):
        tcp_votes_data = tcp_votes_raw
    else:
        total_tcp_votes = sum(tcp_votes_raw.values())
        
        for candidate, votes in tcp_votes_raw.items():
            percentage = (votes / total_tcp_votes * 100) if total_tcp_votes > 0 else 0
            tcp_votes_data.append({
                "candidate": candidate,
                "votes": votes,
                "percentage": percentage
            })
    
    primary_votes_data = []
    primary_votes_raw = dashboard_data.get("primary_votes", {})
    total_primary_votes = sum(item.get("votes", 0) for item in primary_votes_raw.values()) if isinstance(primary_votes_raw, dict) else 0
    
    if isinstance(primary_votes_raw, dict):
        for candidate, data in primary_votes_raw.items():
            primary_votes_data.append({
                "candidate": candidate,
                "votes": data.get("votes", 0),
                "percentage": data.get("percentage", 0)
            })
    
    return jsonify({
        'booth_count': booth_count,
        'total_booths': total_booths,
        'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'primary_votes': primary_votes_data,
        'tcp_votes': tcp_votes_data,
        'booth_results': booth_results
    })

@app.route('/api/notify', methods=['POST'])
def notify():
    """Endpoint for FastAPI to notify of new results"""
    data = request.json
    app.logger.info(f"Received notification: {data}")
    
    if 'electorate' in data:
        socketio.emit('update', {'electorate': data['electorate']}, namespace='/dashboard')
    
    return jsonify({"status": "success", "message": "Notification received"})

@socketio.on('connect', namespace='/dashboard')
def dashboard_connect():
    app.logger.info(f"Client connected to dashboard: {request.sid}")

@socketio.on('disconnect', namespace='/dashboard')
def dashboard_disconnect():
    app.logger.info(f"Client disconnected from dashboard: {request.sid}")

@socketio.on('join', namespace='/dashboard')
def dashboard_join(data):
    """Join a specific electorate's dashboard room"""
    if 'electorate' in data:
        app.logger.info(f"Client {request.sid} joined electorate: {data['electorate']}")
        socketio.emit('status', {'status': 'connected', 'electorate': data['electorate']}, to=request.sid)

@app.route('/admin/polling-places', methods=['GET'])
@app.route('/admin/polling-places/<division>', methods=['GET'])
@login_required
def admin_polling_places(division=None):
    """Admin page to view polling places for a division and manage results"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    electorates = get_all_electorates()
    
    if not division and electorates:
        division = electorates[0]
    
    polling_places = []
    if division:
        from utils.booth_results_processor import get_booth_results_for_division
        booth_results = get_booth_results_for_division(division)
        polling_places = booth_results
    
    # Get current results for this division from FastAPI service
    response = api_call(f"/api/results", params={"electorate": division})
    current_results = []
    
    if response.get("status") == "success":
        results_data = response.get("results", [])
        for result_data in results_data:
            result = Result()
            result.id = result_data.get("id")
            result.timestamp = datetime.datetime.fromisoformat(result_data.get("timestamp"))
            result.electorate = result_data.get("electorate")
            result.booth_name = result_data.get("booth_name")
            result.image_url = result_data.get("image_url")
            result.data = result_data.get("data", {})
            current_results.append(result)
    
    unreviewed_results = [r for r in current_results if not (r.data and r.data.get('reviewed'))]
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_polling_places.html',
        division=division,
        electorates=electorates,
        polling_places=polling_places,
        current_results=current_results,
        unreviewed_results=unreviewed_results,
        messages=messages
    )

@app.route('/admin/reset-results', methods=['POST'])
@login_required
def admin_reset_results():
    """Reset results for testing purposes"""
    if not current_user.is_admin:

        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    division = request.form.get('division')
    booth_name = request.form.get('booth_name')
    all_results = request.form.get('all_results') == 'true'
    
    try:
        data = {
            "division": division,
            "booth_name": booth_name,
            "all_results": all_results
        }
        
        response = api_call("/api/results/reset", method="post", data=data)
        
        if response.get("status") == "success":
            if all_results:
                flash("All results have been reset", "success")
            elif division and booth_name:
                flash(f"Results for {booth_name} in {division} have been reset", "success")
            elif division:
                flash(f"Results for {division} have been reset", "success")
            
            if division:
                socketio.emit('update', {'electorate': division}, namespace='/dashboard')
        else:
            app.logger.error(f"Error resetting results: {response.get('message')}")
            flash(f"Error resetting results: {response.get('message')}", "error")
    except Exception as e:
        app.logger.error(f"Error resetting results: {e}")
        flash(f"Error resetting results: {str(e)}", "error")
    
    return redirect(url_for('admin_polling_places', division=division))

@app.route('/admin/review-result/<int:result_id>', methods=['GET', 'POST'])
@login_required
def admin_review_result(result_id):

    """Admin page to review and approve a result"""
    if not current_user.is_admin:

        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    # Get result from FastAPI
    response = api_call(f"/api/results/{result_id}")
    if response.get("status") != "success":
        flash(f"Error retrieving result: {response.get('message')}", "error")
        return redirect(url_for('admin_polling_places'))
    
    r = response.get("result")
    result = Result(
        id=r["id"],
        image_url=r["image_url"],
        timestamp=datetime.datetime.fromisoformat(r["timestamp"]),
        electorate=r["electorate"],
        booth_name=r["booth_name"],
        data=r["data"]
    )
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'approve':
                if not result.data:
                    result.data = {}
                result.data['reviewed'] = True
                result.data['approved'] = True
                result.data['reviewed_at'] = datetime.datetime.utcnow().isoformat()
                db.session.commit()
                flash("Result approved successfully", "success")

                
                socketio.emit('update', {'electorate': result.electorate}, namespace='/dashboard')
                
                api_call("/api/notify", method="post", data={
                    "result_id": result_id,
                    "electorate": result.electorate,
                    "action": "review",
                    "approved": action == "approve"
                })
                
                return redirect(url_for('admin_polling_places', division=result.electorate))

            elif action == 'reject':
                if not result.data:
                    result.data = {}
                result.data['reviewed'] = True
                result.data['approved'] = False
                result.data['reviewed_at'] = datetime.datetime.utcnow().isoformat()
                db.session.commit()
                flash("Result rejected", "warning")
                return redirect(url_for('admin_polling_places', division=result.electorate))

            else:
                app.logger.error(f"Error reviewing result: Unknown action {action}")
                flash(f"Error reviewing result: Unknown action {action}", "error")

        except Exception as e:
            app.logger.error(f"Error reviewing result: {e}")
            flash(f"Error reviewing result: {str(e)}", "error")
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_review_result_new.html',
        result=result,
        messages=messages,
        electorates=get_all_electorates(),
        selected_electorate=result.electorate,
        is_admin=app.config.get('IS_ADMIN', False)
    )

@app.route('/admin/panel', methods=['GET'])
@app.route('/admin/panel/<division>', methods=['GET'])
@login_required
def admin_panel(division=None):
    """Admin panel that uses FastAPI endpoints for actions"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    electorates = get_all_electorates()
    
    if not division and electorates:
        division = electorates[0]
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_panel_new.html',
        division=division,
        electorates=electorates,
        messages=messages,
        selected_electorate=division,
        is_admin=app.config.get('IS_ADMIN', False)
    )

@app.route('/api/notify', methods=['POST'])
def api_notify():
    """Endpoint for FastAPI to notify Flask app of updates"""
    data = request.json
    app.logger.info(f"Received notification from FastAPI: {data}")
    
    result_id = data.get('result_id')
    electorate = data.get('electorate')
    action = data.get('action')
    
    if electorate:
        socketio.emit('update', {'electorate': electorate}, namespace='/dashboard')
        
        if action == 'review':
            approved = data.get('approved', False)
            status = 'approved' if approved else 'rejected'
            socketio.emit('result_reviewed', {
                'result_id': result_id,
                'electorate': electorate,
                'status': status
            }, namespace='/dashboard')
    

@app.route('/set-default-division/<division>')
def set_default_division(division):
    """Set the default division for the user session"""
    next_url = request.args.get('next', url_for('get_dashboard'))
    
    if division:
        session['default_division'] = division
        flash(f"Default division set to {division}", "success")
    
    return redirect(next_url)

    return jsonify({"status": "success"})

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_approved:
                flash("Your account is pending approval", "warning")
                return redirect(url_for('login'))
                
            login_user(user)
            
            app.config['IS_ADMIN'] = user.is_admin
            
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash("Invalid email or password", "danger")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    app.config['IS_ADMIN'] = False
    flash("You have been logged out", "success")
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    electorates = get_all_electorates()
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        division = request.form.get('division')
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("Email already registered", "danger")
            return render_template('register.html', electorates=electorates)
        
        user = User(
            email=email,
            division=division,
            is_approved=False,
            is_admin=False
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash("Registration successful. Your account is pending approval.", "success")
        return redirect(url_for('login'))
        
    return render_template('register.html', electorates=electorates)

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin page to manage user registrations"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('index'))
        
    pending_users = User.query.filter_by(is_approved=False).all()
    approved_users = User.query.filter_by(is_approved=True).all()
    
    return render_template(
        'admin_users.html',
        pending_users=pending_users,
        approved_users=approved_users
    )

@app.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@login_required
def approve_user(user_id):
    """Approve a user registration"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('index'))
        
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    
    flash(f"User {user.email} approved", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@login_required
def reject_user(user_id):
    """Reject and delete a user registration"""
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('index'))
        
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User {user.email} rejected", "success")
    return redirect(url_for('admin_users'))

@app.route('/load-reference-data')
@login_required
def load_reference_data():
    if not current_user.is_admin:
        flash("Admin access required", "error")
        return redirect(url_for('index'))
        
    try:
        response = api_call("/admin/load-reference-data", method="GET")
        if response.get("status") == "success":
            details = response.get("details", {})
            candidates_loaded = details.get("candidates_loaded", "Unknown")
            booth_results = details.get("booth_results_loaded", "Unknown")
            flash(f"Reference data loaded successfully! Candidates: {candidates_loaded}, Booth results: {booth_results}", "success")
        else:
            error_detail = response.get("detail", "Unknown error")
            app.logger.error(f"Failed to load reference data: {error_detail}")
            flash(f"Failed to load reference data: {error_detail}", "error")
    except Exception as e:
        app.logger.error(f"Error loading reference data: {e}")
        flash(f"Error loading reference data: {str(e)}", "error")
    
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), 
                 allow_unsafe_werkzeug=True, use_reloader=True, log_output=True)

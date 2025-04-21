import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session, get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
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

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///results.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_amalfi_results')
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

app.config['IS_ADMIN'] = True

class Result(db.Model):
    __tablename__ = "results"
    
    id = db.Column(db.Integer, primary_key=True)
    image_url = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    electorate = db.Column(db.String(100), index=True)
    booth_name = db.Column(db.String(100), index=True)
    data = db.Column(db.JSON)

    def to_dict(self):
        return {
            'id': self.id,
            'image_url': self.image_url,
            'timestamp': self.timestamp.isoformat(),
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
        if self.data and 'two_candidate_preferred' in self.data:
            return self.data['two_candidate_preferred']
        return {}
    
    def get_totals(self):
        """Get vote totals from data JSON"""
        if self.data and 'totals' in self.data:
            return self.data['totals']
        return {'formal': None, 'informal': None, 'total': None}

class TCPCandidate(db.Model):
    __tablename__ = "tcp_candidates"
    
    id = db.Column(db.Integer, primary_key=True)
    electorate = db.Column(db.String(100), index=True)
    candidate_id = db.Column(db.Integer)
    candidate_name = db.Column(db.String(100))
    position = db.Column(db.Integer)  # 1 or 2 for the two TCP candidates
    
    def to_dict(self):
        return {
            'id': self.id,
            'electorate': self.electorate,
            'candidate_id': self.candidate_id,
            'candidate_name': self.candidate_name,
            'position': self.position
        }

with app.app_context():
    db.create_all()

def get_all_electorates():
    """Get all unique electorates from the candidates table"""
    try:
        conn = sqlite3.connect(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite://', ''))
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT electorate FROM candidates ORDER BY electorate")
        electorates = [row[0] for row in cursor.fetchall()]
        conn.close()
        return electorates
    except Exception as e:
        app.logger.error(f"Error getting electorates: {e}")
        return []

def get_candidates(electorate=None, candidate_type=None):
    """Get candidates from the database with optional filtering"""
    try:
        conn = sqlite3.connect(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite://', ''))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM candidates WHERE 1=1"
        params = []
        
        if electorate:
            query += " AND electorate = ?"
            params.append(electorate)
        
        if candidate_type:
            query += " AND candidate_type = ?"
            params.append(candidate_type)
        
        query += " ORDER BY electorate, ballot_position"
        
        cursor.execute(query, params)
        candidates = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return candidates
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
    return render_template('index.html')

@app.route('/results')
def get_results():
    results = Result.query.order_by(Result.timestamp.desc()).all()
    return render_template('results.html', results=results)

@app.route('/results/<int:result_id>')
def get_result_detail(result_id):
    result = Result.query.get_or_404(result_id)
    return render_template('result_detail.html', result=result)

@app.route('/candidates')
def get_candidates_page():
    electorate = request.args.get('electorate', '')
    candidate_type = request.args.get('candidate_type', '')
    
    candidates_data = get_candidates(electorate, candidate_type)
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()
    
    return render_template(
        'candidates.html', 
        candidates=candidates_data, 
        electorates=electorates,
        electorate=electorate,
        candidate_type=candidate_type,
        last_updated=last_updated
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
    results = Result.query.order_by(Result.timestamp.desc()).all()
    return jsonify([result.to_dict() for result in results])

@app.route('/api/results/<int:result_id>')
def api_result_detail(result_id):
    result = Result.query.get_or_404(result_id)
    return jsonify(result.to_dict())

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
    
    current_results_query = Result.query.order_by(Result.timestamp.desc())
    if electorate:
        current_results_query = current_results_query.filter(Result.electorate == electorate)
    if booth:
        current_results_query = current_results_query.filter(Result.booth_name.like(f"%{booth}%"))
    
    current_results = current_results_query.all()
    
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
    
    return render_template(
        'booth_results.html',
        booth_results=booth_results,
        current_results=current_results,
        electorates=electorates,
        electorate=electorate,
        booth=booth,
        last_updated=last_updated
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
def get_dashboard(electorate=None):
    """Electorate dashboard showing live results"""
    electorates = get_all_electorates()
    last_updated = get_last_updated_time()
    
    # Get booth counts for each electorate
    booth_counts = {}
    total_booths = {}
    
    for e in electorates:
        booth_counts[e] = Result.query.filter_by(electorate=e).count()
        
        historical_booths = get_booth_results_for_division(e)
        total_booths[e] = len(historical_booths) if historical_booths else 0
    
    if not electorate and electorates:
        electorate = electorates[0]
    
    # Get booth results for the selected electorate
    booth_results = []
    primary_votes = {}
    tcp_votes = {}
    
    if electorate:
        # Get current results for this electorate
        results = Result.query.filter_by(electorate=electorate).order_by(Result.timestamp.desc()).all()
        
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
        
        tcp_candidates = TCPCandidate.query.filter_by(electorate=electorate).order_by(TCPCandidate.position).all()
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
    
    is_admin = app.config.get('IS_ADMIN', False)
    
    return render_template(
        'electorate_dashboard.html',
        electorates=electorates,
        selected_electorate=electorate,
        booth_results=booth_results,
        primary_votes=primary_votes,
        tcp_votes=tcp_votes,
        booth_counts=booth_counts,
        total_booths=total_booths,
        last_updated=last_updated,
        is_admin=is_admin
    )

@app.route('/admin/tcp-candidates/<electorate>', methods=['GET', 'POST'])
def admin_tcp_candidates(electorate):
    """Admin page to set TCP candidates for an electorate"""
    if not app.config.get('IS_ADMIN', False):
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    if request.method == 'POST':
        candidate_ids = request.form.getlist('tcp_candidates')
        
        if len(candidate_ids) != 2:
            flash("You must select exactly two candidates for TCP counting", "error")
        else:
            try:
                # Delete existing TCP candidates for this electorate
                TCPCandidate.query.filter_by(electorate=electorate).delete()
                
                candidates_data = get_candidates(electorate, 'house')
                
                # Add new TCP candidates
                for position, candidate_id in enumerate(candidate_ids, 1):
                    candidate_id = int(candidate_id)
                    candidate = next((c for c in candidates_data if c['id'] == candidate_id), None)
                    
                    if candidate:
                        tcp_candidate = TCPCandidate(
                            electorate=electorate,
                            candidate_id=candidate_id,
                            candidate_name=candidate['name'],
                            position=position
                        )
                        db.session.add(tcp_candidate)
                
                db.session.commit()
                flash("TCP candidates updated successfully", "success")
                
                socketio.emit('tcp_update', {'electorate': electorate}, namespace='/dashboard')
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error setting TCP candidates: {e}")
                flash(f"Error setting TCP candidates: {str(e)}", "error")
        
        return redirect(url_for('admin_tcp_candidates', electorate=electorate))
    
    # Get candidates for this electorate
    candidates = get_candidates(electorate, 'house')
    
    # Add current votes to candidates
    results = Result.query.filter_by(electorate=electorate).all()
    candidate_votes = {}
    
    for result in results:
        primary_votes = result.get_primary_votes()
        for candidate, votes in primary_votes.items():
            if candidate in candidate_votes:
                candidate_votes[candidate] += votes
            else:
                candidate_votes[candidate] = votes
    
    for candidate in candidates:
        candidate['votes'] = candidate_votes.get(candidate['name'], 0)
    
    # Get current TCP candidates
    tcp_candidates = TCPCandidate.query.filter_by(electorate=electorate).order_by(TCPCandidate.position).all()
    tcp_candidate_names = [c.candidate_name for c in tcp_candidates]
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_tcp_candidates.html',
        electorate=electorate,
        candidates=candidates,
        tcp_candidates=tcp_candidate_names,
        messages=messages
    )

@app.route('/api/dashboard/<electorate>')
def api_dashboard(electorate):
    """API endpoint for dashboard data"""
    # Get booth counts
    booth_count = Result.query.filter_by(electorate=electorate).count()
    
    historical_booths = get_booth_results_for_division(electorate)
    total_booths = len(historical_booths) if historical_booths else 0
    
    # Get booth results for the selected electorate
    results = Result.query.filter_by(electorate=electorate).order_by(Result.timestamp.desc()).all()
    
    booth_results = []
    primary_votes = {}
    tcp_votes = {}
    
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
    
    tcp_candidates = TCPCandidate.query.filter_by(electorate=electorate).order_by(TCPCandidate.position).all()
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
    
    primary_votes_list = [
        {'candidate': candidate, 'votes': data['votes'], 'percentage': data['percentage']}
        for candidate, data in primary_votes.items()
    ]
    
    tcp_votes_list = [
        {'candidate': candidate, 'votes': data['votes'], 'percentage': data['percentage']}
        for candidate, data in tcp_votes.items()
    ]
    
    return jsonify({
        'booth_count': booth_count,
        'total_booths': total_booths,
        'last_updated': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'primary_votes': primary_votes_list,
        'tcp_votes': tcp_votes_list,
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
        socketio.emit('status', {'status': 'connected', 'electorate': data['electorate']}, room=request.sid)

@app.route('/admin/polling-places', methods=['GET'])
@app.route('/admin/polling-places/<division>', methods=['GET'])
def admin_polling_places(division=None):
    """Admin page to view polling places for a division and manage results"""
    if not app.config.get('IS_ADMIN', False):
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
    
    # Get current results for this division
    current_results = Result.query.filter_by(electorate=division).order_by(Result.timestamp.desc()).all()
    
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
def admin_reset_results():
    """Reset results for testing purposes"""
    if not app.config.get('IS_ADMIN', False):
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    division = request.form.get('division')
    booth_name = request.form.get('booth_name')
    all_results = request.form.get('all_results') == 'true'
    
    try:
        if all_results:
            Result.query.delete()
            flash("All results have been reset", "success")
        elif division and booth_name:
            Result.query.filter_by(electorate=division, booth_name=booth_name).delete()
            flash(f"Results for {booth_name} in {division} have been reset", "success")
        elif division:
            Result.query.filter_by(electorate=division).delete()
            flash(f"Results for {division} have been reset", "success")
        else:
            flash("Please specify what results to reset", "error")
            return redirect(url_for('admin_polling_places', division=division))
            
        db.session.commit()
        
        if division:
            socketio.emit('update', {'electorate': division}, namespace='/dashboard')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error resetting results: {e}")
        flash(f"Error resetting results: {str(e)}", "error")
    
    return redirect(url_for('admin_polling_places', division=division))

@app.route('/admin/review-result/<int:result_id>', methods=['GET', 'POST'])
def admin_review_result(result_id):
    """Admin page to review and approve a result"""
    if not app.config.get('IS_ADMIN', False):
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    result = Result.query.get_or_404(result_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        try:
            if action == 'approve':
                if not result.data:
                    result.data = {}
                result.data['reviewed'] = True
                result.data['approved'] = True
                result.data['reviewed_at'] = datetime.utcnow().isoformat()
                db.session.commit()
                flash("Result approved successfully", "success")
                
                socketio.emit('update', {'electorate': result.electorate}, namespace='/dashboard')
                
                return redirect(url_for('admin_polling_places', division=result.electorate))
            elif action == 'reject':
                if not result.data:
                    result.data = {}
                result.data['reviewed'] = True
                result.data['approved'] = False
                result.data['reviewed_at'] = datetime.utcnow().isoformat()
                db.session.commit()
                flash("Result rejected", "warning")
                return redirect(url_for('admin_polling_places', division=result.electorate))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error reviewing result: {e}")
            flash(f"Error reviewing result: {str(e)}", "error")
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_review_result.html',
        result=result,
        messages=messages
    )

@app.route('/admin/panel', methods=['GET'])
@app.route('/admin/panel/<division>', methods=['GET'])
def admin_panel(division=None):
    """Admin panel that uses FastAPI endpoints for actions"""
    if not app.config.get('IS_ADMIN', False):
        flash("Admin access required", "error")
        return redirect(url_for('get_dashboard'))
    
    electorates = get_all_electorates()
    
    if not division and electorates:
        division = electorates[0]
    
    messages = []
    for category, message in get_flashed_messages(with_categories=True):
        messages.append((category, message))
    
    return render_template(
        'admin_panel.html',
        division=division,
        electorates=electorates,
        messages=messages
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
    
    return jsonify({"status": "success"})

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), allow_unsafe_werkzeug=True)

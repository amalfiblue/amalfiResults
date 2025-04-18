import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests

sys.path.append(str(Path(__file__).parent.parent))
from utils.aec_data_downloader import download_and_process_aec_data, get_candidates_for_electorate
from utils.booth_results_processor import process_and_load_booth_results, get_booth_results_for_division, get_booth_results_for_polling_place, calculate_swing

load_dotenv()

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/ubuntu/repos/amalfiResults/results.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_for_amalfi_results')
db = SQLAlchemy(app)

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

@app.route('/api/notify', methods=['POST'])
def notify():
    """Endpoint for FastAPI to notify of new results"""
    data = request.json
    app.logger.info(f"Received notification: {data}")
    return jsonify({"status": "success", "message": "Notification received"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

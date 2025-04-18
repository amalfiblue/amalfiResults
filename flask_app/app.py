import os
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///results.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Result(db.Model):
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

@app.route('/api/results')
def api_results():
    results = Result.query.order_by(Result.timestamp.desc()).all()
    return jsonify([result.to_dict() for result in results])

@app.route('/api/results/<int:result_id>')
def api_result_detail(result_id):
    result = Result.query.get_or_404(result_id)
    return jsonify(result.to_dict())

@app.route('/api/notify', methods=['POST'])
def notify():
    """Endpoint for FastAPI to notify of new results"""
    data = request.json
    app.logger.info(f"Received notification: {data}")
    return jsonify({"status": "success", "message": "Notification received"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

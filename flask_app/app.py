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
    data = db.Column(db.JSON)

    def to_dict(self):
        return {
            'id': self.id,
            'image_url': self.image_url,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data
        }

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/results')
def get_results():
    results = Result.query.order_by(Result.timestamp.desc()).all()
    return render_template('results.html', results=results)

@app.route('/api/results')
def api_results():
    results = Result.query.order_by(Result.timestamp.desc()).all()
    return jsonify([result.to_dict() for result in results])

@app.route('/api/notify', methods=['POST'])
def notify():
    """Endpoint for FastAPI to notify of new results"""
    data = request.json
    return jsonify({"status": "success", "message": "Notification received"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

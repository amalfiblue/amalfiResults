import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

from main import app

client = TestClient(app)

@patch('main.httpx.AsyncClient')
@patch('main.SessionLocal')
def test_manual_entry_new_result(mock_session, mock_httpx):
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    mock_client = MagicMock()
    mock_httpx.return_value.__aenter__.return_value = mock_client
    
    test_data = {
        "booth_name": "Test Booth",
        "electorate": "Test Electorate",
        "primary_votes": {"Candidate A": 100, "Candidate B": 200},
        "two_candidate_preferred": {
            "Candidate A": {"Candidate A": 100, "Candidate B": 50},
            "Candidate B": {"Candidate A": 50, "Candidate B": 200}
        },
        "totals": {"formal": 300, "informal": 10, "total": 310}
    }
    
    response = client.post("/manual-entry", json=test_data)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    assert mock_db.add.called
    assert mock_db.commit.called
    
    assert mock_client.post.called

@patch('main.httpx.AsyncClient')
@patch('main.SessionLocal')
def test_manual_entry_update_existing(mock_session, mock_httpx):
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_result
    mock_session.return_value = mock_db
    
    mock_client = MagicMock()
    mock_httpx.return_value.__aenter__.return_value = mock_client
    
    test_data = {
        "result_id": 123,
        "booth_name": "Test Booth",
        "electorate": "Test Electorate",
        "primary_votes": {"Candidate A": 100, "Candidate B": 200},
        "totals": {"formal": 300, "informal": 10, "total": 310}
    }
    
    response = client.post("/manual-entry", json=test_data)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    assert not mock_db.add.called
    assert mock_db.commit.called
    
    assert mock_result.data is not None
    
    assert mock_client.post.called

@patch('main.SessionLocal')
def test_manual_entry_missing_fields(mock_session):
    mock_db = MagicMock()
    mock_session.return_value = mock_db
    
    test_data = {
        "primary_votes": {"Candidate A": 100, "Candidate B": 200},
        "totals": {"formal": 300, "informal": 10, "total": 310}
    }
    
    response = client.post("/manual-entry", json=test_data)
    
    assert response.status_code == 400
    
    assert not mock_db.add.called
    assert not mock_db.commit.called

import pytest
from flask import url_for
import json
from datetime import datetime

def test_admin_polling_places_access(client, app):
    """Test that admin polling places page requires admin access"""
    app.config['IS_ADMIN'] = False
    
    response = client.get('/admin/polling-places')
    
    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']
    
    app.config['IS_ADMIN'] = True
    
    response = client.get('/admin/polling-places')
    
    assert response.status_code == 200
    assert b'Admin Polling Places' in response.data

def test_admin_reset_results(client, app, mocker):
    """Test that admin reset results functionality works"""
    app.config['IS_ADMIN'] = True
    
    mock_query = mocker.patch('flask_app.app.Result.query')
    mock_filter = mocker.MagicMock()
    mock_query.filter_by.return_value = mock_filter
    
    response = client.post('/admin/reset-results', data={
        'division': 'Test Division',
        'booth_name': 'Test Booth'
    }, follow_redirects=True)
    
    mock_query.filter_by.assert_called_with(electorate='Test Division', booth_name='Test Booth')
    mock_filter.delete.assert_called_once()
    
    assert b'Results for Test Booth in Test Division have been reset' in response.data
    
    mock_query.reset_mock()
    mock_filter.reset_mock()
    
    response = client.post('/admin/reset-results', data={
        'division': 'Test Division',
        'all_results': 'false'
    }, follow_redirects=True)
    
    mock_query.filter_by.assert_called_with(electorate='Test Division')
    mock_filter.delete.assert_called_once()
    
    assert b'Results for Test Division have been reset' in response.data
    
    mock_query.reset_mock()
    
    response = client.post('/admin/reset-results', data={
        'division': 'Test Division',
        'all_results': 'true'
    }, follow_redirects=True)
    
    mock_query.delete.assert_called_once()
    
    assert b'All results have been reset' in response.data

def test_admin_review_result(client, app, mocker):
    """Test that admin review result functionality works"""
    app.config['IS_ADMIN'] = True
    
    mock_result = mocker.MagicMock()
    mock_result.id = 1
    mock_result.electorate = 'Test Division'
    mock_result.booth_name = 'Test Booth'
    mock_result.timestamp = datetime.utcnow()
    mock_result.data = {}
    mock_result.get_primary_votes.return_value = {'Candidate 1': 100, 'Candidate 2': 50}
    mock_result.get_tcp_votes.return_value = {'Candidate 1': {'Candidate 2': 30}, 'Candidate 2': {'Candidate 1': 20}}
    mock_result.get_totals.return_value = {'formal': 150, 'informal': 10, 'total': 160}
    
    mock_query = mocker.patch('flask_app.app.Result.query')
    mock_query.get_or_404.return_value = mock_result
    
    response = client.get('/admin/review-result/1')
    
    assert response.status_code == 200
    assert b'Review Tally Sheet Result' in response.data
    
    response = client.post('/admin/review-result/1', data={
        'action': 'approve'
    }, follow_redirects=True)
    
    assert mock_result.data['reviewed'] is True
    assert mock_result.data['approved'] is True
    assert 'reviewed_at' in mock_result.data
    
    assert b'Result approved successfully' in response.data
    
    mock_result.data = {}
    
    response = client.post('/admin/review-result/1', data={
        'action': 'reject'
    }, follow_redirects=True)
    
    assert mock_result.data['reviewed'] is True
    assert mock_result.data['approved'] is False
    assert 'reviewed_at' in mock_result.data
    
    assert b'Result rejected' in response.data

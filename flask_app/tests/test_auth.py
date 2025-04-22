import pytest
from flask_login import current_user
from app import app, db, User

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['WTF_CSRF_ENABLED'] = False
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            root_user = User(
                email="test_admin@example.com",
                division=None,
                is_approved=True,
                is_admin=True
            )
            root_user.set_password("adminpass")
            
            regular_user = User(
                email="test_user@example.com",
                division="Test Division",
                is_approved=True,
                is_admin=False
            )
            regular_user.set_password("userpass")
            
            pending_user = User(
                email="pending@example.com",
                division="Test Division",
                is_approved=False,
                is_admin=False
            )
            pending_user.set_password("pendingpass")
            
            db.session.add_all([root_user, regular_user, pending_user])
            db.session.commit()
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_user_model():
    """Test User model functionality"""
    with app.app_context():
        user = User(
            email="test@example.com",
            division="Test Division",
            is_approved=True,
            is_admin=False
        )
        user.set_password("testpass")
        
        assert user.email == "test@example.com"
        assert user.division == "Test Division"
        assert user.is_approved is True
        assert user.is_admin is False
        assert user.check_password("testpass")
        assert not user.check_password("wrongpass")
        
        assert user.has_access_to_division("Test Division")
        assert not user.has_access_to_division("Other Division")
        
        admin = User(
            email="admin@example.com",
            division=None,
            is_approved=True,
            is_admin=True
        )
        assert admin.has_access_to_division("Any Division")

def test_login(client):
    """Test login functionality"""
    response = client.post('/login', data={
        'email': 'test_user@example.com',
        'password': 'userpass'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Home' in response.data
    
    response = client.post('/login', data={
        'email': 'test_user@example.com',
        'password': 'wrongpass'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Invalid email or password' in response.data
    
    response = client.post('/login', data={
        'email': 'pending@example.com',
        'password': 'pendingpass'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Your account is pending approval' in response.data

def test_registration(client):
    """Test registration functionality"""
    response = client.post('/register', data={
        'email': 'new_user@example.com',
        'password': 'newpass',
        'division': 'Test Division'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Registration successful' in response.data
    
    response = client.post('/register', data={
        'email': 'test_user@example.com',
        'password': 'newpass',
        'division': 'Test Division'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Email already registered' in response.data

def test_admin_access(client):
    """Test admin access control"""
    client.post('/login', data={
        'email': 'test_admin@example.com',
        'password': 'adminpass'
    })
    
    response = client.get('/admin/users')
    assert response.status_code == 200
    
    client.get('/logout')
    
    client.post('/login', data={
        'email': 'test_user@example.com',
        'password': 'userpass'
    })
    
    response = client.get('/admin/users')
    assert response.status_code == 302  # Redirect

def test_division_access(client):
    """Test division-based access control"""
    client.post('/login', data={
        'email': 'test_user@example.com',
        'password': 'userpass'
    })
    
    with app.app_context():
        user = User.query.filter_by(email='test_user@example.com').first()
        assert user.has_access_to_division(user.division)
        
        assert not user.has_access_to_division("Other Division")
    
    client.get('/logout')
    
    client.post('/login', data={
        'email': 'test_admin@example.com',
        'password': 'adminpass'
    })
    
    with app.app_context():
        admin = User.query.filter_by(email='test_admin@example.com').first()
        assert admin.has_access_to_division("Any Division")

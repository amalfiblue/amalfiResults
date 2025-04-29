import unittest
from flask import url_for
from unittest.mock import patch, MagicMock
from app import app, User, db
from io import BytesIO

class TestAdminUpload(unittest.TestCase):

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app = app.test_client()
        with app.app_context():
            db.create_all()
            admin_user = User(email="admin@test.com", is_admin=True, is_approved=True)
            admin_user.set_password("password")
            db.session.add(admin_user)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    @patch('app.requests.post')
    def test_admin_upload_image_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'success',
            'result_id': 123,
            'electorate': 'Test Electorate',
            'booth_name': 'Test Booth'
        }
        mock_post.return_value = mock_response

        self.app.post('/login', data={
            'email': 'admin@test.com',
            'password': 'password'
        }, follow_redirects=True)

        test_image = (BytesIO(b'test image content'), 'test.jpg')

        response = self.app.post('/admin/upload-image', 
                               data={'image': test_image},
                               content_type='multipart/form-data',
                               follow_redirects=True)

        mock_post.assert_called_once()
        
        self.assertIn(b'Image processed successfully', response.data)

if __name__ == '__main__':
    unittest.main()

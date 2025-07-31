import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from datetime import datetime

import sqlalchemy
from flask import url_for
from flask.testing import FlaskClient

from exceptions import InvalidStudent, InvalidSupervisor, MaxProposalsReachedError, NoConcordantProjectMarks

from models import User, Proposal, Project, CatalogProposal, ProjectMark, Meeting
from models.Proposal import ProposalStatus
from models.Project import ProjectStatus

from models.db import db

from app import create_app


class UserManipulation(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        test_config = {
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{self.db_path}',
            'TESTING': True,
            'SECRET_KEY': 'test',
            'SERVER_NAME': 'localhost'
        }
        self.flask_app = create_app(test_config)
        self.app = self.flask_app.test_client()
        self.app_context = self.flask_app.app_context()
        self.app_context.push()
        db.drop_all()
        db.create_all()
        self.student_user = User(
            email="student@example.com",
            name="Student User",
            is_supervisor=False,
            is_admin=False,
            active=True
        )
        self.student_user.set_password("password")
        db.session.add(self.student_user)

        self.student_user2 = User(
            email="student2@example.com",
            name="Student 2 User",
            is_supervisor=False,
            is_admin=False,
            active=True
        )
        self.student_user2.set_password("password")
        db.session.add(self.student_user2)

        self.supervisor_user = User(
            email="supervisor@example.com",
            name="Supervisor User",
            is_supervisor=True,
            is_admin=False,
            active=True
        )
        self.supervisor_user.set_password("password")
        db.session.add(self.supervisor_user)

        self.admin_user = User(
            email="admin@example.com",
            name="Admin User",
            is_supervisor=False,
            is_admin=True,
            active=True
        )
        self.admin_user.set_password("password")
        db.session.add(self.admin_user)
        db.session.commit()

    def tearDown(self):
        db.drop_all()
        self.app_context.pop()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def login(self, user: User) -> FlaskClient:
        client = self.flask_app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = user.id
        return client

    def get_with_login(self, user: User, url: str, **kwargs):
        client = self.flask_app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = user.id
        return client.get(url, **kwargs)

    def test_deactivates_user_successfully(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.deactivate_user', user_id=self.student_user.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User deactivated successfully.', response.data)
        db.session.refresh(self.student_user)
        self.assertFalse(self.student_user.active)

    def test_prevents_non_admin_from_deactivating_user(self):
        client = self.login(self.student_user)
        response = client.post(url_for('user.deactivate_user', user_id=self.supervisor_user.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only module leaders can deactivate users.', response.data)
        db.session.refresh(self.supervisor_user)
        self.assertTrue(self.supervisor_user.active)

    def test_handles_deactivation_of_nonexistent_user(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.deactivate_user', user_id=9999), follow_redirects=True)
        self.assertEqual(response.status_code, 404)

    def test_creates_user_successfully(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.create_user'), data={
            'name': 'New User',
            'email': 'newuser@example.com',
            'password': 'password123',
            'role': 'supervisor'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'New User (supervisor) created successfully.', response.data)
        new_user = User.query.filter_by(email='newuser@example.com').first()
        self.assertIsNotNone(new_user)
        self.assertTrue(new_user.is_supervisor)
        self.assertFalse(new_user.is_admin)
        self.assertTrue(new_user.active)

    def test_prevents_non_admin_from_creating_user(self):
        client = self.login(self.student_user)
        response = client.post(url_for('user.create_user'), data={
            'name': 'Unauthorized User',
            'email': 'unauthorized@example.com',
            'password': 'password123',
            'role': 'supervisor'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only module leaders can create users.', response.data)
        unauthorized_user = User.query.filter_by(email='unauthorized@example.com').first()
        self.assertIsNone(unauthorized_user)

    def test_handles_creation_with_missing_fields(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.create_user'), data={
            'name': '',
            'email': '',
            'password': '',
            'role': 'supervisor'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error:', response.data)
        empty_user = User.query.filter_by(email='').first()
        self.assertIsNone(empty_user)

    def test_handles_creation_with_duplicate_email(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.create_user'), data={
            'name': 'Duplicate User',
            'email': self.student_user.email,
            'password': 'password123',
            'role': 'supervisor'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error:', response.data)
        duplicate_user = User.query.filter_by(name='Duplicate User').first()
        self.assertIsNone(duplicate_user)

    def test_logs_in_user_with_valid_credentials(self):
        client = self.flask_app.test_client()
        user = User(email="validuser@example.com", name="Valid User", active=True)
        user.set_password("validpassword")
        db.session.add(user)
        db.session.commit()
        response = client.post(url_for("auth.login"), data={
            "email": "validuser@example.com",
            "password": "validpassword"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome", response.data)

    def test_prevents_login_with_invalid_credentials(self):
        client = self.flask_app.test_client()
        response = client.post(url_for("auth.login"), data={
            "email": "invaliduser@example.com",
            "password": "wrongpassword"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid credentials", response.data)

    def test_prevents_login_for_inactive_user(self):
        client = self.flask_app.test_client()
        user = User(email="inactiveuser@example.com", name="Inactive User", active=False)
        user.set_password("validpassword")
        db.session.add(user)
        db.session.commit()
        response = client.post(url_for("auth.login"), data={
            "email": "inactiveuser@example.com",
            "password": "validpassword"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Your account is inactive", response.data)

    def test_logs_out_authenticated_user(self):
        client = self.login(self.admin_user)
        response = client.get(url_for("auth.logout"), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Login", response.data)

    def test_handles_error_during_user_deactivation(self):
        client = self.login(self.admin_user)
        with unittest.mock.patch.object(db.session, "commit", side_effect=Exception("Database error")):
            response = client.post(url_for('user.deactivate_user', user_id=self.student_user.id), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error deactivating user: Database error', response.data)
            db.session.refresh(self.student_user)
            self.assertTrue(self.student_user.active)

    def test_grants_admin_privileges_successfully(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.change_admin', user_id=self.student_user.id, admin='true'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User granted admin privileges successfully.', response.data)
        db.session.refresh(self.student_user)
        self.assertTrue(self.student_user.is_admin)

    def test_removes_admin_privileges_successfully(self):
        self.student_user.is_admin = True
        db.session.commit()
        client = self.login(self.admin_user)
        response = client.post(url_for('user.change_admin', user_id=self.student_user.id, admin='false'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User removed admin privileges successfully.', response.data)
        db.session.refresh(self.student_user)
        self.assertFalse(self.student_user.is_admin)

    def test_prevents_non_admin_from_changing_admin_status(self):
        client = self.login(self.student_user)
        response = client.post(url_for('user.change_admin', user_id=self.supervisor_user.id, admin='true'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only module leaders can promote users.', response.data)
        db.session.refresh(self.supervisor_user)
        self.assertFalse(self.supervisor_user.is_admin)

    def test_handles_invalid_user_id_for_admin_change(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('user.change_admin', user_id=9999, admin='true'), follow_redirects=True)
        self.assertEqual(response.status_code, 404)

    def test_prevents_redundant_admin_status_change(self):
        self.student_user.is_admin = True
        db.session.commit()
        client = self.login(self.admin_user)
        response = client.post(url_for('user.change_admin', user_id=self.student_user.id, admin='true'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User is already an admin.', response.data)
        db.session.refresh(self.student_user)
        self.assertTrue(self.student_user.is_admin)

    def test_handles_error_during_admin_status_change(self):
        client = self.login(self.admin_user)
        with unittest.mock.patch.object(db.session, "commit", side_effect=Exception("Database error")):
            response = client.post(url_for('user.change_admin', user_id=self.student_user.id, admin='true'), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error changing admin status: Database error', response.data)
            db.session.refresh(self.student_user)
            self.assertFalse(self.student_user.is_admin)

    def test_changes_password_successfully_with_valid_data(self):
        client = self.login(self.student_user)
        self.student_user.set_password("oldpassword")
        db.session.commit()
        response = client.post(url_for("user.change_password"), data={
            "current_password": "oldpassword",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Password changed successfully.", response.data)
        self.assertTrue(self.student_user.check_password("newpassword123"))

    def test_prevents_password_change_with_incorrect_current_password(self):
        client = self.login(self.student_user)
        self.student_user.set_password("oldpassword")
        db.session.commit()
        response = client.post(url_for("user.change_password"), data={
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Current password is incorrect.", response.data)
        self.assertTrue(self.student_user.check_password("oldpassword"))

    def test_prevents_password_change_when_new_passwords_do_not_match(self):
        client = self.login(self.student_user)
        self.student_user.set_password("oldpassword")
        db.session.commit()
        response = client.post(url_for("user.change_password"), data={
            "current_password": "oldpassword",
            "new_password": "newpassword123",
            "confirm_password": "differentpassword"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New passwords do not match.", response.data)
        self.assertTrue(self.student_user.check_password("oldpassword"))

    def test_prevents_password_change_when_new_password_is_too_short(self):
        client = self.login(self.student_user)
        self.student_user.set_password("oldpassword")
        db.session.commit()
        response = client.post(url_for("user.change_password"), data={
            "current_password": "oldpassword",
            "new_password": "short",
            "confirm_password": "short"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New password must be at least 6 characters.", response.data)
        self.assertTrue(self.student_user.check_password("oldpassword"))

    def test_redirects_authenticated_user_to_home(self):
        client = self.login(self.student_user)
        response = client.get(url_for('index'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome', response.data)

    def test_redirects_unauthenticated_user_to_login(self):
        client = self.flask_app.test_client()
        response = client.get(url_for('index'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)

    def test_renders_admin_home_with_supervisor_data(self):
        client = self.login(self.admin_user)
        self.admin_user.is_supervisor = True
        db.session.commit()
        response = client.get(url_for('user.home'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Module Leader Dashboard', response.data)
        self.assertIn(b'Admin Supervisor', response.data)
        self.assertIn(b"You don\xe2\x80\x99t have any proposals or projects yet.", response.data)

    def test_renders_admin_home_without_supervisor_data(self):
        client = self.login(self.admin_user)
        self.admin_user.is_supervisor = False
        db.session.commit()
        response = client.get(url_for('user.home'), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Module Leader Dashboard', response.data)
        self.assertIn(b'Admin', response.data)
        self.assertNotIn(b'Admin Supervisor', response.data)
        self.assertNotIn(b"You don\xe2\x80\x99t have any proposals or projects yet.", response.data)

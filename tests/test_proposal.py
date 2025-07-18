import os
import tempfile
import unittest
from datetime import datetime

from exceptions import InvalidStudent, InvalidSupervisor, MaxProposalsReachedError

from models import User, Proposal, Project
from models.Proposal import ProposalStatus

from models.db import db

from app import create_app


class ProposalCreation(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        test_config = {
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{self.db_path}',
            'TESTING': True,
            'SECRET_KEY': 'test'
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

        self.supervisor_user = User(
            email="supervisor@example.com",
            name="Supervisor User",
            is_supervisor=True,
            is_admin=False,
            active=True
        )
        self.supervisor_user.set_password("password")
        db.session.add(self.supervisor_user)
        db.session.commit()

    def tearDown(self):
        db.drop_all()
        self.app_context.pop()
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_validates_student_accepts_regular_user(self):
        student_user = User(is_supervisor=False, is_admin=False)
        proposal = Proposal(student=student_user)
        self.assertEqual(proposal.student, student_user)

    def test_validates_student_rejects_user_with_supervisor_flag(self):
        supervisor = User(is_supervisor=True, is_admin=False)
        with self.assertRaisesRegex(InvalidStudent, "Received Supervisor"):
            Proposal(student=supervisor)

    def test_validates_student_rejects_user_with_admin_flag(self):
        admin = User(is_supervisor=False, is_admin=True)
        with self.assertRaisesRegex(InvalidStudent, "Received Admin"):
            Proposal(student=admin)

    def test_validates_student_rejects_user_with_both_flags(self):
        invalid_user = User(is_supervisor=True, is_admin=True)
        with self.assertRaisesRegex(InvalidStudent, "Received Supervisor"):
            Proposal(student=invalid_user)

    def test_validates_supervisor_accepts_active_supervisor(self):
        active_supervisor = User(is_supervisor=True, is_admin=False, active=True)
        proposal = Proposal(supervisor=active_supervisor)
        self.assertEqual(proposal.supervisor, active_supervisor)

    def test_validates_supervisor_rejects_inactive_supervisor(self):
        inactive_supervisor = User(is_supervisor=True, is_admin=False, active=False)
        with self.assertRaisesRegex(InvalidSupervisor, "Supervisor must be active."):
            Proposal(supervisor=inactive_supervisor)

    def test_validates_supervisor_rejects_non_supervisor(self):
        non_supervisor = User(is_supervisor=False, is_admin=False, active=True)
        with self.assertRaisesRegex(InvalidSupervisor, "User is not supervisor."):
            Proposal(supervisor=non_supervisor)

    def test_proposal_status_returns_accepted_when_accepted_date_is_set_and_rejected_date_is_none(self):
        proposal = Proposal(accepted_date=datetime.utcnow(), rejected_date=None)
        self.assertEqual(proposal.status, ProposalStatus.ACCEPTED)

    def test_proposal_status_returns_rejected_when_rejected_date_is_set(self):
        proposal = Proposal(accepted_date=None, rejected_date=datetime.utcnow())
        self.assertEqual(proposal.status, ProposalStatus.REJECTED)

    def test_proposal_status_returns_pending_when_neither_accepted_nor_rejected_date_is_set(self):
        proposal = Proposal(accepted_date=None, rejected_date=None)
        self.assertEqual(proposal.status, ProposalStatus.PENDING)

    def test_proposal_status_returns_rejected_when_both_accepted_and_rejected_dates_are_set(self):
        proposal = Proposal(accepted_date=datetime.utcnow(), rejected_date=datetime.utcnow())
        self.assertEqual(proposal.status, ProposalStatus.REJECTED)

    def test_submits_proposal_successfully(self):
        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.student_user.id
            response = client.post('/submit_proposal', data={
                'title': 'Test Proposal',
                'description': 'Test Description',
                'supervisor_id': self.supervisor_user.id
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Proposal submitted successfully.', response.data)

    def test_rejects_proposal_submission_by_supervisor(self):
        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.supervisor_user.id
            response = client.post('/submit_proposal', data={
                'title': 'Test Proposal',
                'description': 'Test Description',
                'supervisor_id': 1
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Only students can submit proposals.', response.data)

    def test_handles_missing_supervisor_and_catalog_proposal(self):
        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(self.student_user.id)
            response = client.post('/submit_proposal', data={
                'title': 'Test Proposal',
                'description': 'Test Description'
            }, follow_redirects=True)
            self.assertEqual(200, response.status_code)
            self.assertIn(b'Error:', response.data)

    def test_handles_invalid_catalog_proposal_id(self):
        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = str(self.student_user.id)
            response = client.post('/submit_proposal', data={
                'title': 'Test Proposal',
                'description': 'Test Description',
                'catalog_id': 9999
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 404)

    def test_validates_student_rejects_user_with_active_proposal(self):
        active_proposal = Proposal(
            title="Active Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user
        )
        db.session.add(active_proposal)
        db.session.commit()

        with self.assertRaisesRegex(MaxProposalsReachedError, "Student already has an active proposal."):
            new_proposal = Proposal(
                title="New Proposal",
                description="Description",
                student=self.student_user,
                supervisor=self.supervisor_user
            )
            db.session.add(new_proposal)
            db.session.commit()

    def test_validates_student_accepts_user_with_no_active_proposal(self):
        new_proposal = Proposal(
            title="New Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user
        )
        db.session.add(new_proposal)
        db.session.commit()

        self.assertEqual(new_proposal.student, self.student_user)

    def test_proposal_action_accepts_pending_proposal_and_creates_project(self):
        proposal = Proposal(
            title="Pending Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.supervisor_user.id
            response = client.post(f'/proposal_action/{proposal.id}', data={'action': 'accept'}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Proposal accepted and project created.', response.data)
            self.assertIsNotNone(proposal.accepted_date)
            self.assertEqual(Project.query.filter_by(proposal_id=proposal.id).count(), 1)

    def test_proposal_action_rejects_pending_proposal(self):
        proposal = Proposal(
            title="Pending Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.supervisor_user.id
            response = client.post(f'/proposal_action/{proposal.id}', data={'action': 'reject'}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Proposal rejected.', response.data)
            self.assertIsNotNone(proposal.rejected_date)

    def test_proposal_action_prevents_non_supervisor_from_processing_proposal(self):
        proposal = Proposal(
            title="Pending Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.student_user.id
            response = client.post(f'/proposal_action/{proposal.id}', data={'action': 'accept'}, follow_redirects=True)
            self.assertEqual(response.status_code, 403)

    def test_proposal_action_prevents_processing_already_processed_proposal(self):
        proposal = Proposal(
            title="Processed Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=datetime.utcnow(),
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.supervisor_user.id
            response = client.post(f'/proposal_action/{proposal.id}', data={'action': 'reject'}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Proposal already processed.', response.data)

    def test_proposal_action_handles_invalid_action(self):
        proposal = Proposal(
            title="Pending Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        self.app_context.push()
        with self.flask_app.test_client() as client:
            with client.session_transaction() as session:
                session['_user_id'] = self.supervisor_user.id
            response = client.post(f'/proposal_action/{proposal.id}', data={'action': 'invalid_action'},
                                   follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Invalid action.', response.data)

if __name__ == '__main__':
    unittest.main()
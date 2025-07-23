import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from datetime import datetime

import sqlalchemy
from flask import url_for
from flask.testing import FlaskClient

from exceptions import InvalidStudent, InvalidSupervisor, MaxProposalsReachedError

from models import User, Proposal, Project, CatalogProposal
from models.Proposal import ProposalStatus

from models.db import db

from app import create_app


class ProposalCreation(unittest.TestCase):
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

        self.supervisor_user = User(
            email="supervisor@example.com",
            name="Supervisor User",
            is_supervisor=True,
            is_admin=False,
            active=True
        )
        self.supervisor_user.set_password("password")
        db.session.add(self.supervisor_user)

        self.inactive_supervisor_user = User(
            email="inactive_supervisor@example.com",
            name="Inactive Supervisor",
            is_supervisor=True,
            is_admin=False,
            active=False
        )
        self.inactive_supervisor_user.set_password("password")
        db.session.add(self.inactive_supervisor_user)
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

    def test_validates_student_accepts_regular_user(self):
        proposal = Proposal(student=self.student_user)
        self.assertEqual(proposal.student, self.student_user)

    def test_validates_student_rejects_user_with_supervisor_flag(self):
        with self.assertRaisesRegex(InvalidStudent, "Received Supervisor"):
            Proposal(student=self.supervisor_user)

    def test_validates_student_rejects_user_with_admin_flag(self):
        admin = User(is_supervisor=False, is_admin=True)
        with self.assertRaisesRegex(InvalidStudent, "Received Admin"):
            Proposal(student=admin)

    def test_validates_student_rejects_user_with_both_flags(self):
        with self.assertRaisesRegex(InvalidStudent, "Received Supervisor"):
            Proposal(student=self.supervisor_user)

    def test_validates_supervisor_accepts_active_supervisor(self):
        proposal = Proposal(supervisor=self.supervisor_user)
        self.assertEqual(proposal.supervisor, self.supervisor_user)

    def test_validates_supervisor_rejects_inactive_supervisor(self):
        with self.assertRaisesRegex(InvalidSupervisor, "Supervisor must be active."):
            Proposal(supervisor=self.inactive_supervisor_user)

    def test_validates_supervisor_rejects_non_supervisor(self):
        with self.assertRaisesRegex(InvalidSupervisor, "User is not supervisor."):
            Proposal(supervisor=self.student_user)

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
        client = self.login(self.student_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
            'title': 'Test Proposal',
            'description': 'Test Description',
            'supervisor_id': self.supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Proposal submitted successfully.', response.data)

    def test_rejects_proposal_submission_by_supervisor(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
            'title': 'Test Proposal',
            'description': 'Test Description',
            'supervisor_id': 1
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only students can submit proposals.', response.data)

    def test_handles_missing_supervisor_and_catalog_proposal(self):
        client = self.login(self.student_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
            'title': 'Test Proposal',
            'description': 'Test Description'
        }, follow_redirects=True)
        self.assertEqual(200, response.status_code)
        self.assertIn(b'Error:', response.data)

    def test_handles_invalid_catalog_proposal_id(self):
        client = self.login(self.student_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
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

        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.proposal_action', proposal_id=proposal.id), data={'action': 'accept'}, follow_redirects=True)
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

        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.proposal_action', proposal_id=proposal.id), data={'action': 'reject'}, follow_redirects=True)
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

        client = self.login(self.student_user)
        response = client.post(url_for('proposal.proposal_action', proposal_id=proposal.id), data={'action': 'accept'}, follow_redirects=True)
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

        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.proposal_action', proposal_id=proposal.id), data={'action': 'reject'}, follow_redirects=True)
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

        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.proposal_action', proposal_id=proposal.id), data={'action': 'invalid_action'},
                               follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid action.', response.data)

    def test_withdraws_pending_proposal_successfully(self):
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

        client = self.login(self.student_user)
        response = client.post(url_for('proposal.withdraw_proposal', proposal_id=proposal.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Proposal withdrawn successfully.', response.data)
        self.assertIsNone(Proposal.query.get(proposal.id))

    def test_prevents_withdrawing_proposal_by_non_owner(self):
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

        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.withdraw_proposal', proposal_id=proposal.id), follow_redirects=True)
        self.assertEqual(response.status_code, 403)

    def test_prevents_withdrawing_non_pending_proposal(self):
        proposal = Proposal(
            title="Accepted Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=datetime.utcnow(),
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()

        client = self.login(self.student_user)
        response = client.post(url_for('proposal.withdraw_proposal', proposal_id=proposal.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only pending proposals can be withdrawn.', response.data)
        self.assertIsNotNone(Proposal.query.get(proposal.id))

    def test_handles_error_during_proposal_withdrawal(self):
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

        client = self.login(self.student_user)
        with unittest.mock.patch.object(db.session, 'delete', side_effect=Exception("Database error")):
            response = client.post(url_for('proposal.withdraw_proposal', proposal_id=proposal.id), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error withdrawing proposal: Database error', response.data)
            self.assertIsNotNone(Proposal.query.get(proposal.id))

    def test_associates_proposal_with_project_successfully(self):
        proposal = Proposal(
            title="Test Proposal",
            description="Test Description",
            student=self.student_user,
            supervisor=self.supervisor_user
        )
        project = Project(
            proposal=proposal,
            student=self.student_user,
            supervisor=self.supervisor_user
        )
        db.session.add(proposal)
        db.session.add(project)
        db.session.commit()

        self.assertEqual(project.proposal, proposal)
        self.assertEqual(proposal.project, project)


    def test_prevents_associating_project_with_null_proposal(self):
        project = Project(
            proposal=None,
            student=self.student_user,
            supervisor=self.supervisor_user
        )
        with self.assertRaisesRegex(Exception, "NOT NULL constraint failed"):
            db.session.add(project)
            db.session.commit()

    def test_prevents_associating_multiple_projects_with_same_proposal(self):
        proposal = Proposal(
            title="Test Proposal",
            description="Test Description",
            student=self.student_user,
            supervisor=self.supervisor_user
        )

        project1 = Project(
            proposal=proposal,
            student=self.student_user,
            supervisor=self.supervisor_user
        )

        db.session.add(proposal)
        db.session.add(project1)

        project2 = Project(
            proposal=proposal,
            student=self.student_user,
            supervisor=self.supervisor_user
        )

        try:
            db.session.add(project2)
            db.session.commit()
            self.fail("IntegrityError not raised")
        except sqlalchemy.exc.IntegrityError as e:
            # Check both the SQLAlchemy error and the original DBAPI error
            error_message = str(e) + str(getattr(e, "orig", ""))
            self.assertIn("UNIQUE constraint failed", error_message)
            db.session.rollback()

    def test_handles_error_during_proposal_submission(self):
        client = self.login(self.student_user)
        with unittest.mock.patch.object(db.session, 'commit', side_effect=Exception("Database error")):
            response = client.post(url_for('proposal.submit_proposal'), data={
                'title': 'Test Proposal',
                'description': 'Test Description',
                'supervisor_id': self.supervisor_user.id
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error: Database error', response.data)

    def test_prevents_proposal_submission_by_non_student(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
            'title': 'Test Proposal',
            'description': 'Test Description',
            'supervisor_id': self.supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only students can submit proposals.', response.data)

    def test_prevents_proposal_submission_with_invalid_supervisor(self):
        client = self.login(self.student_user)
        response = client.post(url_for('proposal.submit_proposal'), data={
            'title': 'Test Proposal',
            'description': 'Test Description',
            'supervisor_id': 9999
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error: invalid supervisor', response.data)

    def test_retrieves_supervisor_from_catalog_proposal(self):
        catalog_proposal = CatalogProposal(
            title="Catalog Proposal",
            description="Description",
            supervisor=self.supervisor_user
        )
        db.session.add(catalog_proposal)
        db.session.commit()

        self.assertEqual(catalog_proposal.supervisor, self.supervisor_user)

    def test_assigns_supervisor_from_catalog_proposal_via_submit_proposal(self):
        catalog_proposal = CatalogProposal(
            title="Catalog Proposal",
            description="Description",
            supervisor=self.supervisor_user
        )
        db.session.add(catalog_proposal)
        db.session.commit()

        client = self.login(self.student_user)
        response = client.post(url_for("proposal.submit_proposal"), data={
            'catalog_id': catalog_proposal.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        proposal = Proposal.query.filter_by(student_id=self.student_user.id,
                                            catalog_proposal_id=catalog_proposal.id).first()
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.supervisor, catalog_proposal.supervisor)

    def test_prevents_submission_with_empty_title_and_description(self):
        client = self.login(self.student_user)
        response = client.post(url_for("proposal.submit_proposal"), data={
            'title': '',
            'description': '',
            'supervisor_id': self.supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error submitting proposal: Title and description are required.', response.data)

    def test_prevents_submission_with_invalid_catalog_id(self):
        client = self.login(self.student_user)
        response = client.post(url_for("proposal.submit_proposal"), data={
            'catalog_id': 'invalid'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 404)

    def test_prevents_submission_with_inactive_supervisor(self):
        client = self.login(self.student_user)
        response = client.post(url_for("proposal.submit_proposal"), data={
            'title': 'Test Proposal',
            'description': 'Test Description',
            'supervisor_id': self.inactive_supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Error: invalid supervisor', response.data)


    def test_handles_missing_supervisor_in_catalog_proposal(self):
        try:
            catalog_proposal = CatalogProposal(
                title="Catalog Proposal",
                description="Description",
                supervisor=None
            )
            db.session.add(catalog_proposal)
            db.session.commit()
            self.fail("InvalidSupervisor not raised")
        except InvalidSupervisor as e:
            self.assertEqual(str(e), "Catalog proposals must be assigned to a supervisor.")
            db.session.rollback()

    def test_displays_pending_proposal_on_student_home(self):
        proposal = Proposal(
            title="Pending Test Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()
        response = self.get_with_login(self.student_user, url_for('user.home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Pending Test Proposal', response.data)

    def test_displays_pending_proposal_on_supervisor_home(self):
        proposal = Proposal(
            title="Pending Test Proposal",
            description="Description",
            student=self.student_user,
            supervisor=self.supervisor_user,
            accepted_date=None,
            rejected_date=None
        )
        db.session.add(proposal)
        db.session.commit()
        response = self.get_with_login(self.supervisor_user, url_for('user.home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Pending Test Proposal', response.data)
        self.assertIn(b'Accept', response.data)
        self.assertIn(b'Reject', response.data)


class CatalogProposalManagement(unittest.TestCase):
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

        self.supervisor_user = User(
            email="supervisor@example.com",
            name="Supervisor User",
            is_supervisor=True,
            is_admin=False,
            active=True
        )
        self.supervisor_user.set_password("password")
        db.session.add(self.supervisor_user)

        self.admin_supervisor_user = User(
            email="supervisor2@example.com",
            name="Supervisor User 2",
            is_supervisor=True,
            is_admin=True,
            active=True
        )
        self.admin_supervisor_user.set_password("password")
        db.session.add(self.admin_supervisor_user)

        self.admin_user = User(
            email="admin@example.com",
            name="Supervisor User",
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

    def get_with_login(self, user: User, url: str, **kwargs):
        client = self.flask_app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = user.id
        return client.get(url, follow_redirects=True, **kwargs)

    def login(self, user: User) -> FlaskClient:
        client = self.flask_app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = user.id
        return client

    def test_includes_modal_proposal_template_for_students(self):
        response = self.get_with_login(self.student_user, url_for('proposal.view_catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Catalog', response.data)
        self.assertIn(b'proposalModalLabel', response.data)
        self.assertIn(b'Submit a Proposal', response.data)

    def test_does_not_include_modal_proposal_template_for_supervisors(self):
        response = self.get_with_login(self.supervisor_user, url_for('proposal.view_catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Catalog', response.data)
        self.assertNotIn(b'proposalModalLabel', response.data)
        self.assertNotIn(b'Submit a Proposal', response.data)

    def test_does_not_include_modal_proposal_template_for_admins(self):
        response = self.get_with_login(self.admin_user, url_for('proposal.view_catalog'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Catalog', response.data)
        self.assertNotIn(b'proposalModalLabel', response.data)
        self.assertNotIn(b'Submit a Proposal', response.data)

    def test_renders_create_catalog_proposal_button_for_supervisors(self):
        response = self.get_with_login(self.supervisor_user, url_for('proposal.view_catalog'))
        self.assertIn(b'Create Catalog Proposal', response.data)
        self.assertIn(b'catalogProposalModalLabel', response.data)

    def test_does_not_render_create_catalog_proposal_button_for_students(self):
        response = self.get_with_login(self.student_user, url_for('proposal.view_catalog'))
        self.assertNotIn(b'Create Catalog Proposal', response.data)
        self.assertNotIn(b'catalogProposalModalLabel', response.data)

    def test_does_not_render_create_catalog_proposal_button_for_admins(self):
        response = self.get_with_login(self.admin_user, url_for('proposal.view_catalog'))
        self.assertNotIn(b'Create Catalog Proposal', response.data)
        self.assertNotIn(b'catalogProposalModalLabel', response.data)

    def test_renders_deactivate_button_for_admins_on_own_proposals(self):
        client = self.login(self.admin_user)
        catalog_proposal = CatalogProposal(
            title="Test Catalog Proposal",
            description="Test Description",
            supervisor=self.admin_supervisor_user,
            active=True
        )
        db.session.add(catalog_proposal)
        db.session.commit()
        response = client.get(url_for('proposal.view_catalog'))
        self.assertIn(b'Deactivate Proposal', response.data)

    def test_renders_deactivate_button_for_supervisor_on_own_proposals(self):
        client = self.login(self.supervisor_user)
        catalog_proposal = CatalogProposal(
            title="Test Catalog Proposal",
            description="Test Description",
            supervisor=self.supervisor_user,
            active=True
        )
        db.session.add(catalog_proposal)
        db.session.commit()
        response = client.get(url_for('proposal.view_catalog'))
        self.assertIn(b'Deactivate Proposal', response.data)

    def test_does_not_render_deactivate_button_for_supervisor_on_other_proposals(self):
        client = self.login(self.supervisor_user)
        catalog_proposal = CatalogProposal(
            title="Test Catalog Proposal",
            description="Test Description",
            supervisor=self.supervisor_user,
            active=True
        )
        db.session.add(catalog_proposal)
        db.session.commit()
        catalog_proposal = CatalogProposal(
            title="Test Catalog Proposal 2",
            description="Test Description",
            supervisor=self.admin_supervisor_user,
            active=True
        )
        db.session.add(catalog_proposal)
        db.session.commit()
        response = client.get(url_for('proposal.view_catalog'))
        count_deactivate = response.data.count(b'Deactivate Proposal')
        self.assertEqual(count_deactivate, sum(p.active for p in self.supervisor_user.catalog_proposals))

    def test_does_not_render_deactivate_button_for_students(self):
        client = self.login(self.student_user)
        catalog_proposal = CatalogProposal(
            title="Test Catalog Proposal",
            description="Test Description",
            supervisor=self.supervisor_user,
            active=True
        )
        db.session.add(catalog_proposal)
        db.session.commit()
        response = client.get(url_for('proposal.view_catalog'))
        self.assertNotIn(b'Deactivate Proposal', response.data)


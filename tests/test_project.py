import os
import sqlite3
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta

import sqlalchemy
from sqlalchemy.exc import IntegrityError
from flask import url_for
from flask.testing import FlaskClient

from exceptions import InvalidStudent, InvalidSupervisor, MaxProposalsReachedError, NoConcordantProjectMarks

from models import User, Proposal, Project, CatalogProposal, ProjectMark, Meeting
from models.Proposal import ProposalStatus
from models.Project import ProjectStatus

from models.db import db

from app import create_app


class ProjectManipulation(unittest.TestCase):
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

        self.inactive_supervisor_user = User(
            email="inactive_supervisor@example.com",
            name="Inactive Supervisor",
            is_supervisor=True,
            is_admin=False,
            active=False
        )
        self.inactive_supervisor_user.set_password("password")
        db.session.add(self.inactive_supervisor_user)

        self.proposal = Proposal(
            title="Test Proposal",
            description="Description",
            student_id=self.student_user.id,
            supervisor_id=self.supervisor_user.id
        )
        db.session.add(self.proposal)
        self.proposal2 = Proposal(
            title="Test Proposal 2",
            description="Description",
            student_id=self.student_user2.id,
            supervisor_id=self.supervisor_user.id
        )
        db.session.add(self.proposal2)
        db.session.commit()

        self.project = Project(
            proposal_id=self.proposal.id,
            student_id=self.student_user.id,
            supervisor_id=self.supervisor_user.id
        )

        self.submitted_project = Project(
            proposal_id=self.proposal2.id,
            student_id=self.student_user2.id,
            supervisor_id=self.supervisor_user.id,
            submitted_datetime=datetime.utcnow()
        )
        db.session.add(self.project)
        db.session.add(self.submitted_project)
        db.session.commit()
        db.session.add(ProjectMark(project_id=self.submitted_project.id, marker_id=self.supervisor_user.id))

        db.session.commit()

    def tearDown(self):
        db.session.remove()
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

    def test_assigns_second_marker_successfully(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('project.add_marker', project_id=self.project.id), data={
            'add_marker_id': self.inactive_supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Second marker assigned successfully.', response.data)
        self.assertEqual(self.project.second_marker_id, self.inactive_supervisor_user.id)

    def test_prevents_non_admin_from_assigning_second_marker(self):
        client = self.login(self.student_user)
        response = client.post(url_for('project.add_marker', project_id=self.project.id), data={
            'add_marker_id': self.inactive_supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only admins can assign a second marker.', response.data)
        self.assertIsNone(self.project.second_marker_id)

    def test_prevents_assigning_supervisor_as_second_marker(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('project.add_marker', project_id=self.project.id), data={
            'add_marker_id': self.supervisor_user.id
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Supervisor cannot be assigned as second marker.', response.data)
        self.assertIsNone(self.project.second_marker_id)

    def test_prevents_assigning_second_marker_without_selection(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('project.add_marker', project_id=self.project.id), data={}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No second marker selected.', response.data)
        self.assertIsNone(self.project.second_marker_id)

    def test_allows_student_to_submit_active_project(self):
        self.assertIsNone(self.project.submitted_datetime)
        client = self.login(self.student_user)
        response = client.post(url_for('project.submit_project', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project marked as submitted.', response.data)
        self.assertIsNotNone(self.project.submitted_datetime)
        self.project.submitted_datetime = None  # Reset for further tests
        db.session.commit()

    def test_prevents_student_from_submitting_already_submitted_project(self):
        self.assertIsNotNone(self.submitted_project.submitted_datetime)
        client = self.login(self.student_user2)
        response = client.post(url_for('project.submit_project', project_id=self.submitted_project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project cannot be submitted if project is not active.', response.data)
        self.assertIsNotNone(self.submitted_project.submitted_datetime)

    def test_prevents_non_student_from_submitting_project(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.submit_project', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only the student can submit the project.', response.data)
        self.assertIsNone(self.project.submitted_datetime)

    def test_handles_submission_error_gracefully(self):
        self.assertIsNone(self.project.submitted_datetime)
        with unittest.mock.patch.object(db.session, "commit", side_effect=Exception('Database error')):
            client = self.login(self.student_user)
            response = client.post(url_for('project.submit_project', project_id=self.project.id), follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Error submitting project: Database error', response.data)
            self.assertIsNone(self.project.submitted_datetime)

    def test_allows_supervisor_to_submit_mark_for_submitted_project(self):
        mark = ProjectMark.query.filter_by(project_id=self.submitted_project.id, marker_id=self.supervisor_user.id).first()
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=mark.id), data={
            'grade': 85,
            'feedback': 'Good work'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Mark submitted.', response.data)
        self.assertTrue(mark.finalised)
        self.assertEqual(mark.mark, 85)
        self.assertEqual(mark.feedback, 'Good work')

    def test_prevents_non_marker_from_submitting_mark(self):
        mark = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.supervisor_user.id
        )
        db.session.add(mark)
        db.session.commit()
        self.assertIsNone(self.project.submitted_datetime)
        client = self.login(self.student_user)
        response = client.post(url_for('project.submit_mark', mark_id=mark.id), data={
            'grade': 85,
            'feedback': 'Good work'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Not authorised.', response.data)
        self.assertFalse(mark.finalised)

    def test_prevents_mark_submission_for_non_submitted_project(self):
        mark = ProjectMark(
            project_id=self.project.id,
            marker_id=self.supervisor_user.id
        )
        db.session.add(mark)
        db.session.commit()
        self.assertIsNone(self.project.submitted_datetime)
        self.assertFalse(mark.finalised)
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=mark.id), data={
            'grade': 85,
            'feedback': 'Good work'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project must be submitted before marking.', response.data)
        self.assertFalse(mark.finalised)

    def test_prevents_resubmission_of_finalised_mark(self):
        mark = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.supervisor_user.id,
            mark=85,
            feedback='Good work'
        )
        db.session.add(mark)
        mark.finalised = True
        db.session.commit()

        self.assertTrue(mark.finalised)
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=mark.id), data={
            'grade': 90,
            'feedback': 'Updated feedback'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Mark already finalised.', response.data)
        self.assertEqual(mark.mark, 85)
        self.assertEqual(mark.feedback, 'Good work')

    def test_starts_new_marking_round_for_non_concordant_marks(self):
        ProjectMark.query.filter_by(project_id=self.submitted_project.id).delete()
        db.session.commit()
        mark1 = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.supervisor_user.id
        )
        db.session.add(mark1)

        mark2 = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.inactive_supervisor_user.id,
            mark=70
        )
        db.session.add(mark2)
        mark2.finalised = True
        db.session.refresh(mark1)
        db.session.commit()

        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=mark1.id), data={
            'grade': 85,
            'feedback': 'Good work'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Non-concordant marks detected. New marking round started for the two markers.', response.data)
        new_marks = ProjectMark.query.filter_by(project_id=self.submitted_project.id, finalised=False).all()
        self.assertEqual(len(new_marks), 2)

    def test_allows_second_marker_to_submit_concordant_mark(self):
        self.app_context.push()
        # Assign second marker
        self.submitted_project.second_marker_id = self.inactive_supervisor_user.id
        db.session.commit()
        # Add ProjectMark for second marker
        second_mark = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.inactive_supervisor_user.id
        )
        db.session.add(second_mark)
        db.session.commit()
        # Supervisor submits mark
        supervisor_mark = ProjectMark.query.filter_by(
            project_id=self.submitted_project.id,
            marker_id=self.supervisor_user.id
        ).first()
        supervisor_mark.mark = 80
        supervisor_mark.finalised = True
        db.session.commit()
        self.assertTrue(self.submitted_project.is_submitted)
        # Second marker submits a concordant mark (within 5)
        client = self.login(self.inactive_supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=second_mark.id), data={
            'grade': 84,
            'feedback': 'Concordant mark'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Mark submitted.', response.data)
        db.session.refresh(second_mark)
        self.assertTrue(second_mark.finalised)
        self.assertEqual(second_mark.mark, 84)
        # Project status should be updated to MARKS_CONFIRMED or MARKING depending on implementation
        self.assertIn(self.submitted_project.status, [ProjectStatus.MARKS_CONFIRMED, ProjectStatus.MARKING])

    def test_allows_second_marker_to_submit_non_concordant_mark_and_starts_new_round(self):
        self.app_context.push()
        # Assign second marker
        self.submitted_project.second_marker_id = self.inactive_supervisor_user.id
        db.session.commit()
        # Add ProjectMark for second marker
        second_mark = ProjectMark(
            project_id=self.submitted_project.id,
            marker_id=self.inactive_supervisor_user.id
        )
        db.session.add(second_mark)
        db.session.commit()
        # Supervisor submits mark
        supervisor_mark = ProjectMark.query.filter_by(
            project_id=self.submitted_project.id,
            marker_id=self.supervisor_user.id
        ).first()
        supervisor_mark.mark = 80
        supervisor_mark.finalised = True
        db.session.commit()
        client = self.login(self.inactive_supervisor_user)
        response = client.post(url_for('project.submit_mark', mark_id=second_mark.id), data={
            'grade': 70,
            'feedback': 'Non-concordant mark'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Non-concordant marks detected. New marking round started for the two markers.', response.data)
        db.session.refresh(second_mark)
        self.assertTrue(second_mark.finalised)
        self.assertEqual(second_mark.mark, 70)
        # There should be two new unfinalised marks for a new round
        new_marks = ProjectMark.query.filter_by(
            project_id=self.submitted_project.id, finalised=False
        ).all()
        self.assertEqual(len(new_marks), 2)

    def test_returns_final_mark_when_concordant_marks_exist(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80, finalised=True)
        mark2 = ProjectMark(project_id=self.project.id, marker_id=self.inactive_supervisor_user.id, mark=82,
                            finalised=True)
        db.session.add_all([mark1, mark2])
        db.session.commit()
        self.assertEqual(self.project.final_mark, 81)

    def test_returns_none_when_no_finalised_marks_exist(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80)
        mark2 = ProjectMark(project_id=self.project.id, marker_id=self.inactive_supervisor_user.id, mark=82)
        db.session.add_all([mark1, mark2])
        db.session.commit()
        self.assertIsNone(self.project.final_mark)

    def test_returns_none_when_no_concordant_marks_exist(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80, finalised=True)
        mark2 = ProjectMark(project_id=self.project.id, marker_id=self.inactive_supervisor_user.id, mark=90,
                            finalised=True)
        db.session.add_all([mark1, mark2])
        db.session.commit()
        self.assertIsNone(self.project.final_mark)

    def test_raises_exception_when_marks_are_not_in_pairs(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80, finalised=True)
        db.session.add(mark1)
        db.session.commit()
        with self.assertRaises(NoConcordantProjectMarks):
            self.project.get_final_mark()

    def test_returns_marking_status_when_at_least_one_mark_is_finalised(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80, finalised=True)
        mark2 = ProjectMark(project_id=self.project.id, marker_id=self.inactive_supervisor_user.id, mark=85)
        self.project.submitted_datetime = datetime.utcnow()
        db.session.add_all([mark1, mark2])
        db.session.commit()
        self.assertEqual(self.project.status, ProjectStatus.MARKING)
        # self.project.submitted_datetime = None
        # db.session.commit()

    def test_does_not_return_marking_status_when_no_marks_are_finalised(self):
        mark1 = ProjectMark(project_id=self.project.id, marker_id=self.supervisor_user.id, mark=80)
        mark2 = ProjectMark(project_id=self.project.id, marker_id=self.inactive_supervisor_user.id, mark=85)
        db.session.add_all([mark1, mark2])
        db.session.commit()
        self.assertNotEqual(self.project.status, ProjectStatus.MARKING)

    def test_removes_second_marker_successfully(self):
        self.project.second_marker_id = self.inactive_supervisor_user.id
        db.session.commit()
        client = self.login(self.admin_user)
        response = client.post(url_for('project.remove_second_marker', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Second marker removed.', response.data)
        db.session.refresh(self.project)
        self.assertIsNone(self.project.second_marker_id)

    def test_prevents_non_admin_from_removing_second_marker(self):
        self.project.second_marker_id = self.inactive_supervisor_user.id
        db.session.commit()
        client = self.login(self.student_user)
        response = client.post(url_for('project.remove_second_marker', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only admins can remove the second marker.', response.data)
        db.session.refresh(self.project)
        self.assertIsNotNone(self.project.second_marker_id)

    def test_handles_removal_when_no_second_marker_exists(self):
        self.project.second_marker_id = None
        db.session.commit()
        client = self.login(self.admin_user)
        response = client.post(url_for('project.remove_second_marker', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Second marker removed.', response.data)
        db.session.refresh(self.project)
        self.assertIsNone(self.project.second_marker_id)

    def test_allows_supervisor_to_edit_meeting_details(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'attendance': 1,
            'outcome_notes': 'Discussed project progress'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting updated.', response.data)
        db.session.refresh(meeting)
        self.assertTrue(meeting.attendance)
        self.assertEqual(meeting.outcome_notes, 'Discussed project progress')

    def test_prevents_student_from_editing_meeting_details(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.student_user)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'attendance': 1,
            'outcome_notes': 'Attempted edit'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Not authorized.', response.data)
        db.session.refresh(meeting)
        self.assertFalse(meeting.attendance)
        self.assertIsNone(meeting.outcome_notes)

    def test_prevents_editing_meeting_by_unauthorized_supervisor(self):
        other_supervisor = User(
            email="other_supervisor@example.com",
            name="Other Supervisor",
            is_supervisor=True,
            is_admin=False,
            active=True
        )
        other_supervisor.set_password("password")
        db.session.add(other_supervisor)
        db.session.commit()
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(other_supervisor)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'attendance': 1,
            'outcome_notes': 'Unauthorized edit'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Not authorized.', response.data)
        db.session.refresh(meeting)
        self.assertFalse(meeting.attendance)
        self.assertIsNone(meeting.outcome_notes)

    def test_allows_admin_to_edit_meeting_details(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.admin_user)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'attendance': 1,
            'outcome_notes': 'Admin updated meeting'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting updated.', response.data)
        db.session.refresh(meeting)
        self.assertTrue(meeting.attendance)
        self.assertEqual(meeting.outcome_notes, 'Admin updated meeting')

    def test_deletes_meeting_successfully_when_authorized(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.delete_meeting', meeting_id=meeting.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting deleted.', response.data)
        self.assertIsNone(Meeting.query.get(meeting.id))

    def test_prevents_deleting_meeting_when_not_authorized(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.student_user)
        response = client.post(url_for('project.delete_meeting', meeting_id=meeting.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Not authorized.', response.data)
        self.assertIsNotNone(Meeting.query.get(meeting.id))

    def test_prevents_deleting_nonexistent_meeting(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.delete_meeting', meeting_id=9999), follow_redirects=True)
        self.assertEqual(response.status_code, 404)

    def test_archives_active_project_successfully(self):
        client = self.login(self.admin_user)
        response = client.post(url_for('project.archive_project', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project archived successfully.', response.data)
        db.session.refresh(self.project)
        self.assertTrue(self.project.is_archived)

    def test_prevents_non_admin_from_archiving_project(self):
        client = self.login(self.student_user)
        response = client.post(url_for('project.archive_project', project_id=self.project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only admins can archive projects.', response.data)
        db.session.refresh(self.project)
        self.assertFalse(self.project.is_archived)

    def test_allows_archiving_project_with_confirmed_marks(self):
        client = self.login(self.admin_user)
        # Ensure the project has confirmed marks
        mark1 = ProjectMark(project_id=self.submitted_project.id, marker_id=self.supervisor_user.id, mark=90, finalised=True)
        mark2 = ProjectMark(project_id=self.submitted_project.id, marker_id=self.inactive_supervisor_user.id, mark=85, finalised=True)
        db.session.add_all([mark1, mark2])
        db.session.commit()
        response = client.post(url_for('project.archive_project', project_id=self.submitted_project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project archived successfully.', response.data)
        db.session.refresh(self.submitted_project)
        self.assertTrue(self.submitted_project.is_archived)

    def test_prevents_archiving_project_after_submission_and_during_marking(self):
        client = self.login(self.admin_user)
        self.assertTrue(self.submitted_project.is_submitted)
        self.assertFalse(self.submitted_project.is_archived)
        response = client.post(url_for('project.archive_project', project_id=self.submitted_project.id),
                               follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cannot archive project after submission until marking is complete.', response.data)
        db.session.refresh(self.submitted_project)
        self.assertFalse(self.submitted_project.is_archived)

        mark1 = ProjectMark(project_id=self.submitted_project.id, marker_id=self.supervisor_user.id, mark=90, finalised=True)
        db.session.add(mark1)
        db.session.commit()

        response = client.post(url_for('project.archive_project', project_id=self.submitted_project.id),
                               follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cannot archive project after submission until marking is complete.', response.data)
        db.session.refresh(self.submitted_project)
        self.assertFalse(self.submitted_project.is_archived)

        mark2 = ProjectMark(project_id=self.submitted_project.id, marker_id=self.inactive_supervisor_user.id, mark=85, finalised=True)
        db.session.add(mark2)
        db.session.commit()
        response = client.post(url_for('project.archive_project', project_id=self.submitted_project.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Project archived successfully.', response.data)
        db.session.refresh(self.submitted_project)
        self.assertTrue(self.submitted_project.is_archived)

    def test_creates_meeting_successfully_with_valid_data(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': datetime.utcnow().isoformat(),
            'meeting_end': (datetime.utcnow() + timedelta(hours=1)).strftime('%H:%M'),
            'location': 'Room 101'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting created.', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNotNone(meeting)
        self.assertEqual(meeting.location, 'Room 101')

    def test_prevents_meeting_creation_by_non_supervisor(self):
        client = self.login(self.student_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': datetime.utcnow().isoformat(),
            'meeting_end': (datetime.utcnow() + timedelta(hours=1)).strftime('%H:%M'),
            'location': 'Room 101'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Only the supervisor can create meetings.', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNone(meeting)

    def test_prevents_meeting_creation_with_missing_start_or_end_time(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': '',
            'meeting_end': '',
            'location': 'Room 101'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting start and end times are required.', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNone(meeting)

    def test_prevents_meeting_creation_with_invalid_start_time_format(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': 'invalid-date',
            'meeting_end': (datetime.utcnow() + timedelta(hours=1)).strftime('%H:%M'),
            'location': 'Room 101'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid meeting start time format:', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNone(meeting)

    def test_prevents_meeting_creation_with_invalid_end_time_format(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': datetime.utcnow().isoformat(),
            'meeting_end': 'invalid-time',
            'location': 'Room 101'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid meeting end time format:', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNone(meeting)

    def test_prevents_meeting_creation_with_missing_location(self):
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.create_meeting', project_id=self.project.id), data={
            'meeting_start': datetime.utcnow().isoformat(),
            'meeting_end': (datetime.utcnow() + timedelta(hours=1)).strftime('%H:%M'),
            'location': ''
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting location is required.', response.data)
        meeting = Meeting.query.filter_by(project_id=self.project.id).first()
        self.assertIsNone(meeting)

    def test_invalid_meeting_start_time_redirects_with_error(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'meeting_start': 'invalid-date',
            'meeting_end': (datetime.utcnow() + timedelta(hours=1)).isoformat()
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid meeting start time format:', response.data)
        db.session.refresh(meeting)
        self.assertNotEqual(meeting.meeting_start, 'invalid-date')

    def test_invalid_meeting_end_time_redirects_with_error(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.supervisor_user)
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'meeting_start': datetime.utcnow().isoformat(),
            'meeting_end': 'invalid-time'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid meeting end time format:', response.data)
        db.session.refresh(meeting)
        self.assertNotEqual(meeting.meeting_end, 'invalid-time')

    def test_valid_meeting_start_and_end_updates_successfully(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        client = self.login(self.supervisor_user)
        new_start = (datetime.utcnow() + timedelta(days=1)).isoformat()
        new_end = (datetime.utcnow() + timedelta(days=1, hours=1)).isoformat()
        response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
            'meeting_start': new_start,
            'meeting_end': new_end
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Meeting updated.', response.data)
        db.session.refresh(meeting)
        self.assertEqual(meeting.meeting_start.isoformat(), new_start)
        self.assertEqual(meeting.meeting_end.isoformat(), new_end)

    def test_handles_integrity_error_when_meeting_end_before_start(self):
        meeting = Meeting(
            project_id=self.project.id,
            meeting_start=datetime.utcnow(),
            meeting_end=datetime.utcnow() + timedelta(hours=1),
            location="Room 101"
        )
        db.session.add(meeting)
        db.session.commit()
        with unittest.mock.patch.object(db.session, "commit", side_effect=IntegrityError("Integrity error", None, None)):
            client = self.login(self.supervisor_user)
            response = client.post(url_for('project.edit_meeting', meeting_id=meeting.id), data={
                'meeting_start': datetime.utcnow().isoformat(),
                'meeting_end': (datetime.utcnow() - timedelta(hours=1)).isoformat()
            }, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Integrity error. Meeting end time can not be before start time.", response.data)
            db.session.refresh(meeting)
            self.assertNotEqual(meeting.meeting_end, datetime.utcnow() - timedelta(hours=1))


if __name__ == '__main__':
    unittest.main()

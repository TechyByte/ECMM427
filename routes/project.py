from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.Project import Project, ProjectStatus
from models.Meeting import Meeting
from models.ProjectMark import ProjectMark

from models.db import db

project_bp = Blueprint('project', __name__)

@project_bp.route('/project/<int:project_id>', methods=['GET'])
@login_required
def view_project(project_id):
    project = Project.query.get_or_404(project_id)
    meetings = Meeting.query.filter_by(project_id=project_id).order_by(Meeting.meeting_start).all()
    marks = ProjectMark.query.filter_by(project_id=project_id).all()
    user_role = 'student' if current_user.id == project.student_id else (
        'supervisor' if current_user.id == project.supervisor_id else (
            'second_marker' if current_user.id == project.second_marker_id else (
                'admin' if current_user.is_admin else 'other')))
    can_create_meeting = user_role == 'supervisor'
    can_mark = (current_user.is_supervisor) # TODO: and project.status == 'submitted'
    can_submit = user_role == 'student' # TODO: and project.status == 'active'
    return render_template('project.html', project=project, meetings=meetings, marks=marks, user_role=user_role, can_create_meeting=can_create_meeting, can_mark=can_mark, can_submit=can_submit)

@project_bp.route('/project/<int:project_id>/create_meeting', methods=['POST'])
@login_required
def create_meeting(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.id != project.supervisor_id:
        flash('Only the supervisor can create meetings.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    meeting_start = request.form.get('meeting_start')
    meeting_end = request.form.get('meeting_end')
    location = request.form.get('location')
    meeting = Meeting(
        project_id=project_id,
        meeting_start=datetime.fromisoformat(meeting_start),
        meeting_end=datetime.fromisoformat(meeting_end),
        location=location
    )
    db.session.add(meeting)
    db.session.commit()
    flash('Meeting created.', 'success')
    return redirect(url_for('project.view_project', project_id=project_id))

@project_bp.route('/meeting/<int:meeting_id>/edit', methods=['POST'])
@login_required
def edit_meeting(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    project = Project.query.get(meeting.project_id)
    # Only supervisor or admin can edit
    if current_user.id not in [project.supervisor_id] and not current_user.is_admin:
        flash('Not authorized.', 'danger')
        return redirect(url_for('project.view_project', project_id=meeting.project_id))
    meeting.attendance = bool(int(request.form.get('attendance', 0)))
    meeting.outcome_notes = request.form.get('outcome_notes')
    db.session.commit()
    flash('Meeting updated.', 'success')
    return redirect(url_for('project.view_project', project_id=meeting.project_id))

@project_bp.route('/mark/<int:mark_id>/submit', methods=['POST'])
@login_required
def submit_mark(mark_id):
    mark = ProjectMark.query.get_or_404(mark_id)
    project = Project.query.get(mark.project_id)
    if current_user.id not in [project.supervisor_id, project.second_marker_id]:
        flash('Not authorized.', 'danger')
        return redirect(url_for('project.view_project', project_id=project.id))
    # TODO: Check if project is in a valid state to be marked
    # if project.status != ProjectStatus.SUBMITTED:
    #     flash('Project must be submitted before marking.', 'danger')
    #     return redirect(url_for('project.view_project', project_id=project.id))
    if mark.finalised:
        flash('Mark already finalised.', 'info')
        return redirect(url_for('project.view_project', project_id=project.id))
    mark.grade = float(request.form.get('grade'))
    mark.feedback = request.form.get('feedback')
    mark.finalised = True
    db.session.commit()
    flash('Mark submitted.', 'success')
    return redirect(url_for('project.view_project', project_id=project.id))

@project_bp.route('/project/<int:project_id>/submit', methods=['POST'])
@login_required
def submit_project(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.id != project.student_id:
        flash('Only the student can submit the project.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    # TODO: Check if project is in a valid state to be submitted
    # if project.status != 'active':
    #     flash('Project cannot be submitted.', 'danger')
    #     return redirect(url_for('project.view_project', project_id=project_id))
    # TODO: On submit, project.is_submitted = True
    db.session.commit()
    flash('NOT IMPLEMENTED: Project marked as submitted.', 'success')
    return redirect(url_for('project.view_project', project_id=project_id))


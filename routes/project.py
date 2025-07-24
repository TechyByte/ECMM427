from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from exceptions import NoConcordantProjectMarks
from models import User
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
    try:
        _ = project.get_final_mark()
        final_mark_is_ready = True
    except NoConcordantProjectMarks:
        final_mark_is_ready = False
    user_role = 'student' if current_user.id == project.student_id else (
        'supervisor' if current_user.id == project.supervisor_id else (
            'second_marker' if current_user.id == project.second_marker_id else (
                'admin' if current_user.is_admin else 'other')))
    can_create_meeting = user_role == 'supervisor'
    can_mark = user_role in ['supervisor', 'second_marker'] and project.status in [ProjectStatus.SUBMITTED, ProjectStatus.MARKING]
    can_submit = user_role == 'student' and project.status == ProjectStatus.ACTIVE
    supervisors = User.query.filter_by(is_supervisor=True, active=True).all()
    return render_template('project.html', project=project, meetings=meetings, marks=marks, user_role=user_role, can_create_meeting=can_create_meeting, can_mark=can_mark, can_submit=can_submit, final_mark_is_ready=final_mark_is_ready, supervisors=supervisors)

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
        flash('Not authorised.', 'danger')
        return redirect(url_for('project.view_project', project_id=project.id))
    if project.status not in [ProjectStatus.SUBMITTED, ProjectStatus.MARKING]:
        flash('Project must be submitted before marking.', 'danger')
        return redirect(url_for('project.view_project', project_id=project.id))
    if mark.finalised:
        flash('Mark already finalised.', 'info')
        return redirect(url_for('project.view_project', project_id=project.id))
    mark.mark = float(request.form.get('grade'))
    mark.feedback = request.form.get('feedback')
    mark.finalised = True
    db.session.commit()
    db.session.flush()
    flash('Mark submitted.', 'success')

    # Post-update check for non-concordant marks
    try:
        project.get_final_mark()
    except NoConcordantProjectMarks:
        # Find the last non-concordant pair
        finalised_marks = [m for m in project.marks if m.finalised]
        if len(finalised_marks) >= 2 and len(finalised_marks) % 2 == 0:
            # Sort by id to get the most recent pair
            marks_sorted = sorted(finalised_marks, key=lambda m: m.id)
            m1, m2 = marks_sorted[-2], marks_sorted[-1]
            # Only create new marks if not already present for these markers
            for marker in [m1.marker_id, m2.marker_id]:
                exists = ProjectMark.query.filter_by(project_id=project.id, marker_id=marker, finalised=False).first()
                if not exists:
                    new_mark = ProjectMark(project_id=project.id, marker_id=marker)
                    db.session.add(new_mark)
            db.session.commit()
            flash('Non-concordant marks detected. New marking round started for the two markers.', 'warning')

    return redirect(url_for('project.view_project', project_id=project.id))

@project_bp.route('/project/<int:project_id>/submit', methods=['POST'])
@login_required
def submit_project(project_id):
    project = Project.query.get_or_404(project_id)
    if current_user.id != project.student_id:
        flash('Only the student can submit the project.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    if project.status != ProjectStatus.ACTIVE:
        flash('Project cannot be submitted if project is not active.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    project.submitted_datetime = datetime.utcnow()
    try:
        db.session.commit()
        flash('Project marked as submitted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error submitting project: {e}', 'danger')
    return redirect(url_for('project.view_project', project_id=project_id))

@project_bp.route('/project/<int:project_id>/add_marker', methods=['POST'])
@login_required
def add_marker(project_id):
    project = Project.query.get_or_404(project_id)
    if not current_user.obj.is_admin:
        flash('Only admins can assign a second marker.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    add_marker_id = request.form.get('add_marker_id')
    if not add_marker_id:
        flash('No second marker selected.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    # Prevent assigning the supervisor as second marker
    if int(add_marker_id) == project.supervisor_id:
        flash('Supervisor cannot be assigned as second marker.', 'danger')
        return redirect(url_for('project.view_project', project_id=project_id))
    project.second_marker_id = int(add_marker_id)
    # Create ProjectMark for second marker if not already present
    from models.ProjectMark import ProjectMark
    existing = ProjectMark.query.filter_by(project_id=project.id, marker_id=project.second_marker_id).first()
    if not existing:
        new_mark = ProjectMark(project_id=project.id, marker_id=project.second_marker_id)
        db.session.add(new_mark)
    db.session.commit()
    flash('Second marker assigned successfully.', 'success')
    return redirect(url_for('project.view_project', project_id=project_id))

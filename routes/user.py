from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from models import db, User, Proposal, Project, CatalogProposal, ProjectMark
from models.Proposal import ProposalStatus
from models.Project import ProjectStatus
user_bp = Blueprint('user', __name__)

def fao_supervisor(supervisor: User) -> ([Proposal],[Project],[Project]):
    pending_proposals = [p for p in Proposal.query.filter_by(supervisor_id=supervisor.id).all() if p.status == ProposalStatus.PENDING]
    projects = [p for p in Project.query.filter_by(supervisor_id=supervisor.id).all() if p.status != ProjectStatus.ARCHIVED]
    marking_projects = [pm.project for pm in
                        ProjectMark.query.filter_by(marker_id=supervisor.id)
                        .join(Project)
                        .filter(Project.supervisor_id != supervisor.id)
                        .group_by(ProjectMark.project_id).all() if pm.project.is_submitted]
    return pending_proposals, projects, marking_projects

@user_bp.route("/", methods=["GET", "POST"])
@login_required
def home():
    user = current_user.obj

    if user.is_admin:
        # Module leader view
        students = User.query.filter_by(is_supervisor=False, is_admin=False, active=True).all()
        supervisors = User.get_active_supervisors()
        if user.is_supervisor:
            pending_proposals, projects, marking_projects = fao_supervisor(user)
            return render_template("home_admin.html", students=students, supervisors=supervisors, pending_proposals=pending_proposals, projects=projects, marking_projects=marking_projects)
        return render_template("home_admin.html", students=students, supervisors=supervisors)

    elif user.is_supervisor:
        # Supervisor view
        pending_proposals, projects, marking_projects = fao_supervisor(user)
        return render_template("home_supervisor.html", pending_proposals=pending_proposals, projects=projects, marking_projects=marking_projects)

    else:
        # Student view
        projects = [p for p in Project.query.filter_by(student_id=user.id).all() if p.status == ProjectStatus.ACTIVE]
        old_projects = [p for p in Project.query.filter_by(student_id=user.id).all() if p.status != ProjectStatus.ACTIVE]
        pending_proposals = [p for p in Proposal.query.filter_by(student_id=user.id).all() if p.status == ProposalStatus.PENDING]
        rejected_proposals = [p for p in Proposal.query.filter_by(student_id=user.id).all() if p.status == ProposalStatus.REJECTED]
        catalog = CatalogProposal.query.all()
        supervisors = User.get_active_supervisors()
        has_project = len(projects) > 0
        return render_template("home_student.html", has_project=has_project, catalog=catalog,
                               projects=projects, old_projects=old_projects, pending_proposals=pending_proposals,
                               rejected_proposals=rejected_proposals, supervisors=supervisors)




@user_bp.route("/create_user", methods=["POST"])
@login_required
def create_user():
    if not (current_user.is_authenticated and current_user.is_admin):
        flash("Only module leaders can create users.", "error")
        return redirect(url_for("user.home"))

    name = request.form.get("name")
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role")

    try:
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            is_supervisor=(role == "supervisor"),
            is_admin=False,
            active=True
        )
        db.session.add(user)
        db.session.commit()
        flash(f"{name} ({role}) created successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("user.home"))

@user_bp.route('/deactivate_user/<int:user_id>', methods=['POST'])
@login_required
def deactivate_user(user_id):
    if not (current_user.is_authenticated and current_user.is_admin):
        flash('Only module leaders can deactivate users.', 'danger')
        return redirect(url_for('user.home'))
    user = User.query.get_or_404(user_id)
    try:
        user.active = False
        db.session.commit()
        flash('User deactivated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating user: {e}', 'danger')
    return redirect(url_for('user.home'))


@user_bp.route('/change_admin/<int:user_id>/<admin>', methods=['POST'])
@login_required
def change_admin(user_id, admin):
    if not (current_user.is_authenticated and current_user.is_admin):
        flash('Only module leaders can promote users.', 'danger')
        return redirect(url_for('user.home'))
    user = User.query.get_or_404(user_id)
    admin_bool = admin.lower() == 'true'
    if user.is_admin == admin_bool:
        flash(f'User is already {"an admin" if admin_bool else "not an admin"}.', 'info')
        return redirect(url_for('user.home'))
    try:
        user.is_admin = admin_bool
        db.session.commit()
        flash(f'User {"granted" if admin_bool else "removed"} admin privileges successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error changing admin status: {e}', 'danger')
    return redirect(url_for('user.home'))
from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from models import db, User, Proposal, Project, CatalogProposal, ProjectMark
from models.Proposal import ProposalStatus
user_bp = Blueprint('user', __name__)

@user_bp.route("/", methods=["GET", "POST"])
@login_required
def home():
    user = current_user.obj

    if user.is_admin:
        # Module leader view
        students = User.query.filter_by(is_supervisor=False, is_admin=False, active=True).all()
        supervisors = User.query.filter_by(is_supervisor=True, active=True).all()
        return render_template("home_admin.html", students=students, supervisors=supervisors)

    elif user.is_supervisor:
        # Supervisor view
        proposals = Proposal.query.filter_by(supervisor_id=user.id).all()
        projects = Project.query.filter_by(supervisor_id=user.id).all()
        marking_projects = [pm.project for pm in ProjectMark.query.filter_by(marker_id=user.id).all() if pm.project.is_submitted]
        return render_template("home_supervisor.html", proposals=proposals, projects=projects, marking_projects=marking_projects)

    else:
        # Student view
        projects = Project.query.filter_by(student_id=user.id).all()
        pending_proposals = [p for p in Proposal.query.filter_by(student_id=user.id).all() if p.status == ProposalStatus.PENDING]
        rejected_proposals = [p for p in Proposal.query.filter_by(student_id=user.id).all() if p.status == ProposalStatus.REJECTED]
        catalog = CatalogProposal.query.all()
        supervisors = User.query.filter_by(is_supervisor=True, active=True).all()
        has_project = len(projects) > 0
        return render_template("home_student.html", has_project=has_project,
                               projects=projects, pending_proposals=pending_proposals, catalog=catalog,
                               rejected_proposals=rejected_proposals, supervisors=supervisors)




@user_bp.route("/create_user", methods=["POST"])
@login_required
def create_user():
    if not (current_user.is_authenticated and current_user.obj.is_admin):
        flash("Only module leaders can create users.")
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
        flash(f"{role.title()} created successfully.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}")

    return redirect(url_for("user.home"))

@user_bp.route('/deactivate_user/<int:user_id>', methods=['POST'])
@login_required
def deactivate_user(user_id):
    if not (current_user.is_authenticated and current_user.obj.is_admin):
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

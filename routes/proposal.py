from flask import Blueprint, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from datetime import datetime

from models.Proposal import ProposalStatus
from models import db, User, Project, Proposal, CatalogProposal, ProjectMark

proposal_bp = Blueprint('proposal', __name__)

@proposal_bp.route("/submit_proposal", methods=["POST"])
@login_required
def submit_proposal():
    if current_user.is_authenticated and (current_user.obj.is_admin or current_user.obj.is_supervisor):
        flash("Only students can submit proposals.")
        return redirect(url_for("user.home"))

    if not ((request.form.get("title") and request.form.get("description")) or request.form.get("catalog_id")):
        flash("Error submitting proposal: Title and description are required.", "error")
        return redirect(url_for("user.home"))

    user = current_user.obj
    title = request.form.get("title")
    description = request.form.get("description")
    catalog_id = request.form.get("catalog_id")
    supervisor_id = request.form.get("supervisor_id") if not catalog_id else None  # ignore supervisor if catalog is used

    catalog_proposal = CatalogProposal.query.get_or_404(catalog_id) if catalog_id else None

    if catalog_proposal:
        supervisor = catalog_proposal.supervisor
    else:
        supervisor = User.query.filter_by(id=supervisor_id, is_supervisor=True, active=True).first()
        if not supervisor:
            flash("Error: invalid supervisor", "error")
            return redirect(url_for("user.home"))

    try:
        proposal = Proposal(
            title=title if not catalog_proposal else catalog_proposal.title,
            description=description if not catalog_proposal else catalog_proposal.description,
            catalog_proposal_id=catalog_proposal.id if catalog_id else None,
            student_id=user.id,
            supervisor_id=supervisor.id
        )
        db.session.add(proposal)
        db.session.commit()
        flash("Proposal submitted successfully.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")

    return redirect(url_for("user.home"))

@proposal_bp.route("/proposal_action/<int:proposal_id>", methods=["POST"])
@login_required
def proposal_action(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    user = current_user.obj
    if not user.is_supervisor or proposal.supervisor_id != user.id:
        abort(403)
    action = request.form.get("action")
    if proposal.status != ProposalStatus.PENDING:
        flash("Proposal already processed.")
        return redirect(url_for("user.home"))
    if action == "accept":
        proposal.accepted_date = datetime.now()
        project = Project(
            proposal_id=proposal.id,
            student_id=proposal.student_id,
            supervisor_id=proposal.supervisor_id
        )
        db.session.add(project)
        db.session.flush()  # get project.id

        # Create ProjectMark for supervisor
        db.session.add(ProjectMark(project_id=project.id, marker_id=project.supervisor_id))

        flash("Proposal accepted and project created.")
    elif action == "reject":
        proposal.rejected_date = datetime.now()
        flash("Proposal rejected.")
    else:
        flash("Invalid action.")
        return redirect(url_for("user.home"))
    db.session.commit()
    return redirect(url_for("user.home"))


@proposal_bp.route('/withdraw_proposal/<int:proposal_id>', methods=['POST'])
@login_required
def withdraw_proposal(proposal_id):
    proposal = Proposal.query.get_or_404(proposal_id)
    user = current_user.obj
    if proposal.student_id != user.id:
        abort(403)
    if proposal.status != ProposalStatus.PENDING:
        flash('Only pending proposals can be withdrawn.', 'warning')
        return redirect(url_for('user.home'))
    try:
        db.session.delete(proposal)
        db.session.commit()
        flash('Proposal withdrawn successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error withdrawing proposal: {e}', 'danger')
    return redirect(url_for('user.home'))

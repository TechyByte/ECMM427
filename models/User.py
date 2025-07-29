from flask import flash
from flask_login import UserMixin

from sqlalchemy import and_, or_
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, validates
from werkzeug.security import check_password_hash, generate_password_hash

from models.Proposal import Proposal, ProposalStatus
from models.Project import Project, ProjectStatus
from models.ProjectMark import ProjectMark
from exceptions import ActiveUserError
from models.db import db


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    is_supervisor = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)

    projects = db.relationship('Project', back_populates='student', foreign_keys='Project.student_id')

    proposals_submitted = relationship('Proposal', back_populates='student', foreign_keys='Proposal.student_id')
    proposals_supervised = relationship('Proposal', back_populates='supervisor', foreign_keys='Proposal.supervisor_id')
    catalog_proposals = relationship('CatalogProposal', back_populates='supervisor')
    projects_supervised = relationship('Project', back_populates='supervisor', foreign_keys='Project.supervisor_id')
    projects_marked = relationship('Project', back_populates='second_marker', foreign_keys='Project.second_marker_id')
    marks_given = relationship('ProjectMark', back_populates='marker', foreign_keys='ProjectMark.marker_id')

    def set_password(self, password: str) -> bool:
        try:
            self.password_hash = generate_password_hash(password)
            return True
        except Exception as e:
            flash(f"Error setting password: {e}", "error")
            return False

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @hybrid_property
    def has_unmarked(self):
        return ProjectMark.query.filter(
                (ProjectMark.marker_id == self.id) & (ProjectMark.finalised == False)
                ).first()

    @hybrid_property
    def has_ongoing_project(self):
        return [p for p in Project.query.join(Proposal).filter(
                        or_(
                            Project.supervisor_id == self.id,
                            Project.student_id == self.id
                        )
                ) if p.status not in [ProjectStatus.ARCHIVED]]

    @hybrid_property
    def has_pending(self):
        return [p for p in Proposal.query.filter(
                or_(
                        Proposal.supervisor_id == self.id,
                        Proposal.student_id == self.id
                    )
                ) if p.status == ProposalStatus.PENDING]

    @validates('active')
    def validate_active_status(self, key, value: bool):
        if not value:
            if self.has_pending:
                raise ActiveUserError("Cannot deactivate user with pending proposals.")
            if self.has_ongoing_project:
                raise ActiveUserError("Cannot deactivate user with ongoing projects.")
            if self.has_unmarked:
                raise ActiveUserError("Cannot deactivate user with unfinalised marks.")
        return value

    @hybrid_property
    def is_student(self):
        return not (self.is_supervisor or self.is_admin)

    @hybrid_property
    def user_type(self):
        if self.is_admin and self.is_supervisor:
            return "Admin Supervisor"
        elif self.is_admin:
            return "Admin"
        elif self.is_supervisor:
            return "Supervisor"
        else:
            return "Student"

    @classmethod
    def get_active_supervisors(cls):
        return cls.query.filter_by(is_supervisor=True, active=True).all()


class LoginUser(UserMixin):
    def __init__(self, user: User):
        self.id = user.id
        self._user = user

    @property
    def email(self):
        return self._user.email

    @property
    def name(self):
        return self._user.name

    @property
    def is_supervisor(self):
        return self._user.is_supervisor

    @property
    def is_admin(self):
        return self._user.is_admin

    @property
    def is_student(self):
        return not self._user.is_supervisor and not self._user.is_admin

    @property
    def user_type(self):
        return self._user.user_type

    @property
    def obj(self):
        return self._user


from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, validates

from models.db import db

from exceptions import InvalidStudent, InvalidSupervisor, MaxProposalsReachedError

from enum import Enum


class ProposalStatus(Enum):
    PENDING = 'Pending'
    ACCEPTED = 'Accepted'
    REJECTED = 'Rejected'


class Proposal(db.Model):
    __tablename__ = 'proposal'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)

    catalog_proposal_id = db.Column(db.Integer, ForeignKey('catalog_proposal.id'), nullable=True)
    student_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)

    created_date = db.Column(db.DateTime, nullable=False, default=datetime.now())
    accepted_date = db.Column(db.DateTime, nullable=True)
    rejected_date = db.Column(db.DateTime, nullable=True)

    catalog_proposal = relationship('CatalogProposal')
    student = relationship('User', back_populates='proposals_submitted', foreign_keys=[student_id])
    supervisor = relationship('User', back_populates='proposals_supervised', foreign_keys=[supervisor_id])
    project = relationship('Project', uselist=False, back_populates='proposal')

    @validates('student')
    def validate_student(self, key, user):
        if user.is_supervisor:
            raise InvalidStudent("Received Supervisor, Expected Student")
        if user.is_admin:
            raise InvalidStudent("Received Admin, Expected Student")
        return user

    @validates('supervisor')
    def validate_supervisor(self, key, user):
        with db.session.no_autoflush:
            if not (user.is_supervisor and user.active):
                if not user.is_supervisor:
                    raise InvalidSupervisor("User is not supervisor.")
                if not user.active:
                    raise InvalidSupervisor("Supervisor must be active.")
        return user

    @hybrid_property
    def status(self):
        if self.accepted_date and not self.rejected_date:
            return ProposalStatus.ACCEPTED
        elif self.rejected_date:
            return ProposalStatus.REJECTED
        else:
            return ProposalStatus.PENDING

    @validates('student_id')
    def validate_max_active_proposal(self, key, value):
        if value is not None:
            user_proposals = Proposal.query.filter_by(student_id=value).filter(Proposal.id != self.id).all()
            pending_user_proposals = [p for p in user_proposals if p.status == ProposalStatus.PENDING]
            if len(pending_user_proposals) > 0:
                raise MaxProposalsReachedError("Student already has an active proposal.")
        return value

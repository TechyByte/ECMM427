from sqlalchemy import ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from models.db import db
from enum import Enum

class ProjectStatus(Enum):
    ACTIVE = "active"
    SUBMITTED = "submitted"
    MARKED = "marked"

class Project(db.Model):
    __tablename__ = 'project'

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, ForeignKey('proposal.id'), nullable=False)

    student_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    second_marker_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=True)

    proposal = relationship('Proposal', back_populates='project')
    meetings = relationship('Meeting', back_populates='project', cascade="all, delete-orphan")
    student = relationship('User', back_populates='projects', foreign_keys=[student_id])
    supervisor = relationship('User', back_populates='projects_supervised', foreign_keys=[supervisor_id])
    second_marker = relationship('User', back_populates='projects_marked', foreign_keys=[second_marker_id])
    marks = relationship('ProjectMark', back_populates='project', cascade="all, delete-orphan")


    @hybrid_property
    def status(self):
        #  TODO: Implement logic to determine project status based on proposal status and marks
        return ProjectStatus.ACTIVE

    def get_final_grade(self):
        final_mark = next((m for m in self.marks if m.is_reconciled), None)
        if final_mark:
            return final_mark.grade
        individual = [m.grade for m in self.marks if not m.is_reconciled and m.finalised]
        if len(individual) == 2 and abs(individual[0] - individual[1]) <= 5:
            return round(sum(individual) / 2, 2)
        return None


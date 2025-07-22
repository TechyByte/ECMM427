from sqlalchemy import ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from exceptions import NoConcordantProjectMarks
from models.db import db
from enum import Enum

class ProjectStatus(Enum):
    ACTIVE = "active"
    SUBMITTED = "submitted"
    MARKING = "marked provisionally"
    MARKS_CONFIRMED = "marks confirmed"

class Project(db.Model):
    __tablename__ = 'project'

    id = db.Column(db.Integer, primary_key=True)
    proposal_id = db.Column(db.Integer, ForeignKey('proposal.id'), nullable=False, unique=True)

    student_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    supervisor_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    second_marker_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=True)

    proposal = relationship('Proposal', back_populates='project')
    meetings = relationship('Meeting', back_populates='project', cascade="all, delete-orphan")
    student = relationship('User', back_populates='projects', foreign_keys=[student_id])
    supervisor = relationship('User', back_populates='projects_supervised', foreign_keys=[supervisor_id])
    second_marker = relationship('User', back_populates='projects_marked', foreign_keys=[second_marker_id])
    marks = relationship('ProjectMark', back_populates='project', cascade="all, delete-orphan")

    submitted_datetime = db.Column(db.DateTime, nullable=True)

    @hybrid_property
    def is_submitted(self):
        return self.submitted_datetime is not None

    @hybrid_property
    def is_finalised(self):
        # Project is finalised if all pairs of marks are finalised and concordant, and there are no unpaired marks
        marks = [m for m in self.marks if not m.is_reconciled]
        if len(marks) == 0:
            return False
        if len(marks) % 2 != 0:
            return False
        # Check all pairs for concordancy (difference <= 5)
        marks_sorted = sorted(marks, key=lambda m: m.id)
        for i in range(0, len(marks_sorted), 2):
            m1, m2 = marks_sorted[i], marks_sorted[i+1]
            if not (m1.finalised and m2.finalised):
                return False
            if abs(m1.mark - m2.mark) > 5:
                return False
        return True

    @hybrid_property
    def status(self):
        if self.is_submitted:
            try:
               final_mark = self.get_final_mark()
            except NoConcordantProjectMarks:
                return ProjectStatus.SUBMITTED
            if final_mark is not None:
                return ProjectStatus.MARKS_CONFIRMED
            else:
                return ProjectStatus.MARKING
        return ProjectStatus.ACTIVE

    def get_final_mark(self):
        # Only compute if there are pairs and all pairs are concordant
        marks = [m for m in self.marks if m.finalised]
        if len(marks) == 0 or len(marks) % 2 != 0:
            raise NoConcordantProjectMarks("Project does not have a valid pair of marks for reconciliation.")

        marks_sorted = sorted(marks, key=lambda m: m.id)

        for i in range(0, len(marks_sorted), 2):
            m1, m2 = marks_sorted[i], marks_sorted[i+1]
            if not (m1.mark and m2.mark):
                continue
            if abs(m1.mark - m2.mark) <= 5:
                return (m1.mark + m2.mark) / 2
        raise NoConcordantProjectMarks("No concordant marks found for project.")

    @hybrid_property
    def final_mark(self):
        try:
            return self.get_final_mark()
        except NoConcordantProjectMarks:
            return None

    __table_args__ = (
        db.CheckConstraint('second_marker_id IS NULL OR second_marker_id != supervisor_id',
                           name='check_second_marker_not_supervisor'),
        db.CheckConstraint('second_marker_id IS NULL OR second_marker_id != student_id',
                           name='check_second_marker_not_student'),
    )
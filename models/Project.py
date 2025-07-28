from sqlalchemy import ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from exceptions import NoConcordantProjectMarks
from models.db import db
from enum import Enum

class ProjectStatus(Enum):
    ACTIVE = "Active"
    SUBMITTED = "Submitted"
    MARKING = "Marking in Progress"
    MARKS_CONFIRMED = "Marks Confirmed"
    ARCHIVED = "Archived"

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
    archived_datetime = db.Column(db.DateTime, nullable=True)

    @hybrid_property
    def is_submitted(self):
        return self.submitted_datetime is not None

    @hybrid_property
    def is_archived(self):
        return self.archived_datetime is not None

    @hybrid_property
    def status(self):
        if self.is_archived:
            return ProjectStatus.ARCHIVED
        final_mark = None
        if self.is_submitted:
            try:
               final_mark = self.get_final_mark()
            except NoConcordantProjectMarks:
                if any(m.finalised for m in self.marks):
                    return ProjectStatus.MARKING
            if final_mark is not None:
                return ProjectStatus.MARKS_CONFIRMED
            else:
                return ProjectStatus.SUBMITTED
        return ProjectStatus.ACTIVE

    def get_final_mark(self):
        # Only compute if there are pairs and all pairs are concordant
        marks = [m for m in self.marks if m.finalised]
        if len(marks) == 0 or len(marks) % 2 != 0:
            raise NoConcordantProjectMarks("Project does not have a valid pair of marks for reconciliation.")

        marks_sorted = sorted(marks, key=lambda m: m.id)

        for i in range(0, len(marks_sorted), 2):
            m1, m2 = marks_sorted[i], marks_sorted[i+1]
            if not (m1.mark and m2.mark and m1.finalised and m2.finalised):
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

    def archive(self):
        self.archived_datetime = db.func.now()
        db.session.commit()

    __table_args__ = (
        db.CheckConstraint('second_marker_id IS NULL OR second_marker_id != supervisor_id',
                           name='check_second_marker_not_supervisor'),
        db.CheckConstraint('second_marker_id IS NULL OR second_marker_id != student_id',
                           name='check_second_marker_not_student'),
    )
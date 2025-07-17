from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from models.db import db
from sqlalchemy import CheckConstraint

class ProjectMark(db.Model):
    __tablename__ = 'project_mark'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, ForeignKey('project.id'), nullable=False)
    marker_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)

    grade = db.Column(db.Float, nullable=False)
    feedback = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    finalised = db.Column(db.Boolean, default=False)  # True once submitted
    is_reconciled = db.Column(db.Boolean, default=False)  # True if this is the agreed mark
    reconciliation_notes = db.Column(db.Text, nullable=True)

    project = relationship('Project', back_populates='marks')
    marker = relationship('User', back_populates='marks_given')

    __table_args__ = (
        CheckConstraint('grade >= 0 AND grade <= 100', name='check_grade_bounds'),
    )


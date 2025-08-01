from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, validates
from models.db import db
from sqlalchemy import CheckConstraint

class ProjectMark(db.Model):
    __tablename__ = 'project_mark'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, ForeignKey('project.id'), nullable=False)
    marker_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)

    mark = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    finalised = db.Column(db.Boolean, default=False, nullable=False)  # True once submitted

    project = relationship('Project', back_populates='marks')
    marker = relationship('User', back_populates='marks_given')

    __table_args__ = (
        CheckConstraint('mark is NULL OR (mark >= 0 AND mark <= 100)', name='check_grade_bounds'),
    )

    @validates('finalised')
    def is_finalised_valid(self, key, value: bool) -> bool:
        # if finalised and no mark is set, then it is invalid
        if value and self.mark is None:
            return False
        # leave NOT NULL constraint to handle this case
        return True

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from models.db import db


class Meeting(db.Model):
    __tablename__ = 'meeting'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, ForeignKey('project.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.now())
    meeting_start = db.Column(db.DateTime, nullable=False)
    meeting_end = db.Column(db.DateTime, nullable=True)
    location = db.Column(db.String(120), nullable=True)

    attendance = db.Column(db.Boolean, nullable=False, default=False)  # True = attended
    outcome_notes = db.Column(db.Text, nullable=True)

    project = relationship('Project', back_populates='meetings')

    @property
    def has_started(self):
        return self.meeting_start <= datetime.now()

    __table_args__ = (
        db.CheckConstraint('meeting_end IS NULL OR meeting_end > meeting_start', name='check_meeting_end_after_start'),
    )

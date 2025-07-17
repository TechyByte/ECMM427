from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, validates

from exceptions import ActiveUserError
from models.db import db

class CatalogProposal(db.Model):
    __tablename__ = 'catalog_proposal'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    supervisor_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)

    supervisor = relationship('User', back_populates='catalog_proposals')

    @validates('supervisor')
    def validate_supervisor(self, key, user):
        if not (user.is_supervisor and user.active):
            raise ActiveUserError("Catalog proposals must be assigned to an active supervisor.")
        return user

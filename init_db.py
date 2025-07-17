from app import create_app
from models.db import db
app = create_app()

from models import User, CatalogProposal
from werkzeug.security import generate_password_hash

def init_database():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Create users
        users = [
            User(
                name="Alice Student",
                email="alice@student.univ.edu",
                password_hash=generate_password_hash("password123"),
                is_supervisor=False,
                is_admin=False,
                active=True
            ),
            User(
                name="Bob Supervisor",
                email="bob@staff.univ.edu",
                password_hash=generate_password_hash("securepass"),
                is_supervisor=True,
                is_admin=False,
                active=True
            ),
            User(
                name="Carol Supervisor",
                email="carol@staff.univ.edu",
                password_hash=generate_password_hash("anotherpass"),
                is_supervisor=True,
                is_admin=False,
                active=True
            ),
            User(
                name="Dave Admin",
                email="dave@admin.univ.edu",
                password_hash=generate_password_hash("adminpass"),
                is_supervisor=True,  # Also supervises
                is_admin=True,
                active=True
            ),
            User(
                name="Eve Inactive Supervisor",
                email="eve@staff.univ.edu",
                password_hash=generate_password_hash("inactivepass"),
                is_supervisor=True,
                is_admin=False,
                active=False
            ),
        ]
        db.session.add_all(users)
        db.session.commit()

        # Lookup supervisors (must be active to create catalog proposals)
        bob = User.query.filter_by(email="bob@staff.univ.edu").first()
        carol = User.query.filter_by(email="carol@staff.univ.edu").first()

        # Create catalog proposals
        proposals = [
            CatalogProposal(
                title="AI for Social Good",
                description="Explore applications of AI in education, healthcare, or sustainability.",
                supervisor_id=bob.id
            ),
            CatalogProposal(
                title="Blockchain Voting Systems",
                description="Investigate the use of blockchain for secure electronic voting.",
                supervisor_id=carol.id
            ),
            CatalogProposal(
                title="Natural Language Interfaces",
                description="Build tools to allow users to interact with databases using plain English.",
                supervisor_id=bob.id
            )
        ]
        db.session.add_all(proposals)
        db.session.commit()

        print("Database initialized with users and catalog proposals.")

if __name__ == "__main__":
    init_database()

![Tests](https://github.com/TechyByte/ECMM427/actions/workflows/testing.yml/badge.svg?branch=main)
[![codecov](https://codecov.io/github/TechyByte/ECMM427/graph/badge.svg?token=WZGRU4GXSL)](https://codecov.io/github/TechyByte/ECMM427)

A project for managing student proposals, projects, meetings, and marking.

## Executive Summary

The Dissertation Management System addresses the university's need for a structured and transparent process to manage dissertations. This system consolidates the entire dissertation lifecycle, from proposal to final grading, into a single platform.

Projects can be proposed either by supervisors (via a catalog) or by students (with a supervisor nomination). Supervisors approve student proposals directly in the system, ensuring a documented, auditable workflow. Once approved, a project record is created, allowing supervisors to log meetings and attendance, and enabling module leaders to oversee progress via dashboards. Marking is double-blind: supervisors and second markers enter marks independently; if marks differ by more than 5 percentage points, reconciliation is triggered, and new marks/rationales are recorded.

Built on Python (Flask) and SQLite, the system is lightweight, open-source, and scalable. It enforces institutional rules (e.g., only active supervisors can be assigned) and supports role-based access control to maintain data privacy and academic integrity. By reducing administrative overhead, increasing visibility, and maintaining compliance with academic policies, the system modernizes dissertation management and improves the experience for students and staff alike.

## Architecture Overview

The system follows a classic web architecture using Flask (MVC pattern), SQLite (SQLAlchemy ORM), and Bootstrap-enhanced HTML templates. It defines six core models:

- **User**: Includes roles (can be neither, one, or both of "admin" and "supervisor"), with constraints to ensure data integrity (e.g., it is not possible to deactivate a user if they have an active project). Defines many relationships (projects, proposals_submitted/proposals_supervised, catalog_proposals, projects_supervised/projects_marked, and marks_given) and computed properties for role-based access and user information.

- **CatalogProposal**: Supervisor-published projects, available for student selection, ensures supervisor is active. Each CatalogProposal can be withdrawn by the relevant supervisor or any admin, preventing any further submissions, without affecting ongoing projects/proposals.

- **Proposal**: Student-initiated or CatalogProposal-linked proposals pending supervisor approval. Contains constraints to ensure a student cannot submit a proposal without a supervisor, and prevents students having multiple pending proposals. It also includes a computed status field to track the proposal's lifecycle:
  - _Pending_: The default state when a proposal is created.
  - _Approved_: Indicates that the proposal has been accepted by the supervisor.
  - _Rejected_: Denotes that the proposal was not accepted.

- **Project**: Represents an accepted proposal, with links to student, supervisor, and second marker. Implements a constraint to prevent the supervisor being assigned as the second marker. A project has a status as below:
  - _Active_: This is the default state for a project that has not been submitted or archived.
  - _Submitted_: Represents a project that has been submitted by the student but has not yet undergone marking.
  - _Marking in Progress_: Denotes that the project is in the process of being marked, typically when marks are incomplete or subject to reconciliation.
  - _Marks Confirmed_: Indicates that the project's marks have been finalised.
  - _Archived_: Represents a project that has been archived, ie. it is no longer active or undergoing evaluation.

- **Meeting**: Supervisor-logged attendance and notes for each project. Email contact can be logged in outcome notes.

- **ProjectMark**: Stores marks and feedback for projects while enforcing constraints and relationships to maintain data integrity. It ensures that marks are within valid bounds and that a mark must be set before finalising the record.

Flask routes control user flow: students submit proposals, supervisors approve them and log meetings, and module leaders assign markers and oversee the cohort.

The front-end uses Bootstrap modals for key interactions, maintaining a clean and responsive interface. Business logic is primarily enforced in the models, supporting data integrity and maintainability. The architecture is well-suited for extension, e.g., integrating file upload, notifications, or analytics.

## Legal and Ethical Considerations

The system handles personal data, requiring GDPR-compliant processing. Role-based access ensures users can only view/alter relevant data.

## Software Components and Licensing

| Component        | 	Vendor                       | 	Version         | 	EOL               | License | 	Cost/Model | 
|------------------|-------------------------------|------------------|--------------------|--------|-------------|
| Python           | 	Python Software  Foundation  | 	3.9.23 - 3.13.5 | Oct 2025 - Oct 2029 | PSF	  | Free  | 
| Flask            | 	Pallets Projects             | 	3.0.3           | Current            | BSD-3 | Free	 | 
| SQLite           | 	D. R. Hipp (Public  Domain)	 | 3.49.2	        | --                 | Public | Free  |
| SQLAlchemy       | 	SQLAlchemy Project           | 	2.0.x           | Active             | MIT	  | Free  |  
| Flask-SQLAlchemy | 	Pallets Projects             | 	3.0.x	        | Active             | MIT	  | Free  |
| Flask-Login      | 	Flask  ecosystem             | 	0.6.2           | Active             | MIT   | Free	  |
| Werkzeug         | 	Pallets Projects             | 	2.3.x	        | Active             | BSD-3 | Free	  |
| Jinja2           | 	Pallets Projects             | 	3.1.x	        | Active             | BSD-3 | Free	  | 
| Bootstrap        | 	Open source  (GitHub)        | 	5.2.x	        | Active             | MIT	  | Free  | 

The project uses the MIT License: permissive, compatible with all dependencies, and ideal for academic reuse or extension.

## Team Development Considerations

Developing this in a team would allow faster progress and more features, though requiring coordination. Work would be divided among UI, backend, database, and testing roles. A Scrum-based agile process would facilitate sprints and feedback loops. Git, code reviews, and task boards would support collaboration.

Challenges like merge conflicts, interface integration, and consistency would be addressed through documentation, shared architecture, and peer review. A team could deliver better testing, accessibility, and UX.
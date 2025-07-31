![Tests](https://github.com/TechyByte/ECMM427/actions/workflows/testing.yml/badge.svg?branch=main)
[![codecov](https://codecov.io/github/TechyByte/ECMM427/graph/badge.svg?token=WZGRU4GXSL)](https://codecov.io/github/TechyByte/ECMM427)

A project for managing student proposals, projects, meetings, and marking.

## Executive Summary

The Dissertation Management System addresses the university's need for a structured and transparent process to manage dissertations. This system consolidates the entire dissertation lifecycle, from proposal to final grading, into a single platform.

Projects can be proposed either by supervisors (via a catalog) or by students (with a supervisor nomination). Supervisors approve student proposals directly in the system, ensuring a documented, auditable workflow. Once approved, a project record is created, allowing supervisors to log meetings and attendance, and enabling module leaders to oversee progress via dashboards. Marking is double-blind: supervisors and second markers enter marks independently; if marks differ by more than 5 percentage points, reconciliation is triggered, and rationales are recorded.

Built on Python (Flask) and SQLite, the system is lightweight, open-source, and scalable. It enforces institutional rules (e.g., only active supervisors can be assigned) and supports role-based access control to maintain data privacy and academic integrity. By reducing administrative overhead, increasing visibility, and maintaining compliance with academic policies, the system modernizes dissertation management and improves the experience for students and staff alike.
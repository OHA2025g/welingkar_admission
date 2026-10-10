ROLES = {
    "candidate": {"label": "Candidate", "home": "/candidate/dashboard"},
    "super_admin": {"label": "Super Admin", "home": "/staff/dashboard"},
    "admissions_operator": {"label": "Admissions Operator", "home": "/staff/dashboard"},
    "document_verifier": {"label": "Document Verifier", "home": "/staff/dashboard"},
    "panelist": {"label": "GA/PI Panelist", "home": "/staff/dashboard"},
    "interview_coordinator": {"label": "Interview Coordinator", "home": "/staff/dashboard"},
    "accounts_operator": {"label": "Accounts Operator", "home": "/staff/dashboard"},
    "result_approver": {"label": "Result Approver", "home": "/staff/dashboard"},
    "auditor": {"label": "Auditor (read-only)", "home": "/staff/dashboard"},
}
STAFF_ROLES = [r for r in ROLES if r != "candidate"]

PERMISSIONS = {
    "users.manage": "Create staff users, assign roles, disable accounts",
    "roles.read": "View roles and permission matrix",
    "cycles.read": "View admission cycles",
    "cycles.write": "Create and edit admission cycles",
    "programs.read": "View programs/routes and seat capacity",
    "programs.write": "Create and edit programs/routes and seats",
    "policies.read": "View policy versions (TFW, refund)",
    "policies.write": "Draft and activate policy versions",
    "audit.read": "View the audit log",
    "candidates.read": "View candidate records",
    "applications.process": "Process candidate applications and batches",
    "applications.read": "View submitted application forms and Part A dashboard",
    "applications.correct": "Correct submitted application data (audited, versioned)",
    "applications.export": "Download Part A Excel exports",
    "documents.verify": "Review assigned documents",
    "assessments.score": "Enter GA/PI scores for assigned sessions",
    "interviews.manage": "Manage locations, sessions, allocation and attendance",
    "payments.read": "View payment orders and receipts",
    "payments.refund": "Execute approved refunds",
    "refunds.signoff": "Approve or decline large refunds before payout",
    "assessments.correct": "Correct submitted GA/PI scores (audited, versioned)",
    "evaluations.read": "View GA/PI evaluation and slot reports, export score files",
    "results.generate": "Generate result versions (rerunnable)",
    "results.read": "View generated and published result versions",
    "results.publish": "Review, approve and publish result versions",
    "partb.import": "Import merit/waitlist lists into Part B and roll back batches",
    "partb.read": "View Part B candidates, batches, allotments, vacancy and reports",
    "partb.manage": "Manage merit/waitlist batches and allot, hold, reject or cancel seats",
    "consent.correct": "Correct candidate consent (audited, versioned)",
    "seats.manage": "Set the Part B seat matrix within approved intake",
    "reports.read": "View scoped reports",
    "self.application": "Own application, payments and results",
    "payments.verify": "Verify or reject offline payments and record offline proof",
    "cancellations.review": "Approve or reject seat cancellation requests",
    "candidates.edit": "Controlled correction of candidate profile fields (audited)",
    "print.center": "Generate application, allotment, payment and cancellation documents",
}

_R = ["cycles.read", "programs.read"]
ROLE_PERMS = {
    "candidate": ["self.application"],
    "super_admin": ["users.manage", "roles.read", "cycles.read", "cycles.write", "programs.read", "programs.write",
                    "policies.read", "policies.write", "audit.read", "candidates.read", "reports.read", "payments.read",
                    "applications.read", "applications.correct", "applications.export", "assessments.correct",
                    "evaluations.read", "results.generate", "results.read", "partb.import", "partb.read", "partb.manage",
                    "consent.correct", "seats.manage", "cancellations.review", "refunds.signoff", "candidates.edit", "print.center"],
    "admissions_operator": _R + ["candidates.read", "applications.process", "applications.read", "applications.correct",
                                 "applications.export", "reports.read", "evaluations.read", "results.generate", "results.read",
                                 "partb.import", "partb.read", "partb.manage", "consent.correct", "cancellations.review",
                                 "candidates.edit", "print.center"],
    "document_verifier": ["documents.verify"],
    "panelist": ["assessments.score"],
    "interview_coordinator": _R + ["interviews.manage", "evaluations.read"],
    "accounts_operator": _R + ["payments.read", "payments.refund", "payments.verify", "reports.read", "print.center"],
    "result_approver": _R + ["results.read", "results.publish", "evaluations.read", "reports.read"],
    "auditor": _R + ["roles.read", "policies.read", "audit.read", "candidates.read", "applications.read", "reports.read",
                     "evaluations.read", "results.read", "partb.read", "payments.read"],
}

IDLE_MINUTES = {"staff": 15, "candidate": 30}
UNMASKED_CONTACT_ROLES = {"super_admin", "admissions_operator"}


def idle_for(role: str) -> int:
    return IDLE_MINUTES["candidate" if role == "candidate" else "staff"]

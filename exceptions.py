class InvalidStudent(ValueError):
    # This exception is raised when an active student is expected but not received.
    pass

class InvalidSupervisor(ValueError):
    # This exception is raised when an active supervisor is expected but not received.
    pass

class ActiveUserError(ValueError):
    # This exception is raised when it is not possible to deactivate a user.
    pass

class MaxProposalsReachedError(ValueError):
    # This exception is raised when a user tries to create more propoosals than allowed.
    pass

class ProjectNotSubmittedError(ValueError):
    # This exception is raised when a project fails to submit or if an action requires a submitted project.
    pass

class NoConcordantProjectMarks(ValueError):
    #  This exception is raised when a project has no concordant marks, thus requires additional marking
    pass
# ########################
# ##### NOTES ON IMPORT FORMAT
# ########################
#
# Imports need to be structured/formatted so as to to ensure that the broadest
# possible set of static analyzers understand this public API as intended.
# The below guidelines ensure this is the case.
#
# (1) All imports in this module intended to define exported symbols should be
# of the form `from pulse_aws.foo import X as X`. This is because imported symbols
# are not by default considered public by static analyzers. The redundant alias
# form `import X as X` overwrites the private imported `X` with a public `X`
# bound to the same value. It is also possible to expose `X` as public by
# listing it inside `__all__`, but the redundant alias form is preferred here
# due to easier maintainability.

# (2) All imports should target the module in which a symbol is actually defined, rather than a
# container module where it is imported.

from pulse_aws.config import (
	DockerBuild as DockerBuild,
)
from pulse_aws.config import (
	HealthCheckConfig as HealthCheckConfig,
)
from pulse_aws.config import (
	ReaperConfig as ReaperConfig,
)
from pulse_aws.config import (
	TaskConfig as TaskConfig,
)
from pulse_aws.deployment import (
	DeploymentError as DeploymentError,
)
from pulse_aws.deployment import (
	deploy as deploy,
)
from pulse_aws.plugin import (
	AWSECSPlugin as AWSECSPlugin,
)

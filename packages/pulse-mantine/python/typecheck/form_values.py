from typing import TypedDict

from pulse_mantine import MantineForm


class Project(TypedDict):
	name: str


class Sample(TypedDict):
	sample_id: str
	project: Project


class SampleForm(TypedDict):
	samples: list[Sample]


form: MantineForm[SampleForm] = MantineForm(
	initialValues={"samples": []},
)

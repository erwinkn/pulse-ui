import copy
import json
from typing import Any

import pulse as ps
from pulse_mantine import (
    Button,
    Card,
    Divider,
    Group,
    MantineProvider,
    Stack,
    Text,
    TextInput,
    Textarea,
    Title,
)
from pulse_mantine.form.form import MantineForm


def _new_pet() -> dict[str, str]:
    return {"name": "", "species": ""}


def _new_member(full_name: str = "") -> dict[str, object]:
    return {
        "fullName": full_name,
        "role": "",
        "bio": "",
        "pets": [_new_pet()],
    }


class DynamicHouseholdForm(MantineForm):
    def __init__(self) -> None:
        super().__init__(
            mode="controlled",
            initialValues={
                "householdName": "The Travelers",
                "members": [
                    _new_member("Avery"),
                    _new_member("River"),
                ],
            },
            syncMode="change",
            # syncDebounceMs=120,
        )

    # Member operations -----------------------------------------------------
    def add_member(self) -> None:
        self.insert_list_item("members", _new_member())

    def duplicate_member(self, index: int) -> None:
        values = self.values.get("members") or []
        try:
            original = values[index]
        except IndexError:
            return
        clone = copy.deepcopy(original)
        clone["fullName"] = f"{clone.get('fullName', 'New Member')} (copy)"
        self.insert_list_item("members", clone, index + 1)

    def remove_member(self, index: int) -> None:
        self.remove_list_item("members", index)

    # Pet operations --------------------------------------------------------
    def add_pet(self, member_index: int) -> None:
        self.insert_list_item(f"members.{member_index}.pets", _new_pet())

    def remove_pet(self, member_index: int, pet_index: int) -> None:
        self.remove_list_item(f"members.{member_index}.pets", pet_index)


@ps.component
def HouseholdFormDemo():
    form = ps.states(DynamicHouseholdForm)

    members = form.values.get("members") or []

    def render_pet(member_idx: int, pet_idx: int):
        return Card(
            key=f"pet-{member_idx}-{pet_idx}",
            withBorder=True,
            radius="md",
            padding="sm",
        )[
            Stack(gap="xs")[
                TextInput(
                    name=f"members.{member_idx}.pets.{pet_idx}.name",
                    label="Pet name",
                    placeholder="Milo",
                ),
                TextInput(
                    name=f"members.{member_idx}.pets.{pet_idx}.species",
                    label="Species",
                    placeholder="Cat",
                ),
                Button(
                    "Remove pet",
                    color="red",
                    variant="subtle",
                    onClick=lambda: form.remove_pet(member_idx, pet_idx),
                ),
            ]
        ]

    def render_member(member_idx: int):
        member = members[member_idx]
        pets = (
            member.get("pets")
            if isinstance(member, dict)
            else getattr(member, "pets", [])
        )
        pets = pets or []

        return Card(key=f"member-{member_idx}", withBorder=True, shadow="sm", mt="md")[
            Group(align="flex-start", justify="space-between")[
                Title(order=4)[f"Household member {member_idx + 1}"],
                Group(gap="xs")[
                    Button(
                        "Duplicate",
                        variant="light",
                        onClick=lambda: form.duplicate_member(member_idx),
                    ),
                    Button(
                        "Remove",
                        color="red",
                        variant="default",
                        onClick=lambda: form.remove_member(member_idx),
                    ),
                ],
            ],
            Divider(my="sm"),
            Stack(gap="sm")[
                TextInput(
                    name=f"members.{member_idx}.fullName",
                    label="Full name",
                    placeholder="Taylor Doe",
                ),
                TextInput(
                    name=f"members.{member_idx}.role",
                    label="Role",
                    placeholder="Parent, roommate, ...",
                ),
                Textarea(
                    name=f"members.{member_idx}.bio",
                    autosize=True,
                    minRows=2,
                    label="Short bio",
                    placeholder="What should we know about this person?",
                ),
                Stack(mt="sm", gap="xs")[
                    Group(align="center", justify="space-between")[
                        Text(size="sm")["Pets"],
                        Button(
                            "Add pet",
                            variant="light",
                            size="xs",
                            onClick=lambda: form.add_pet(member_idx),
                        ),
                    ],
                    ps.If(
                        len(pets) == 0,
                        Button(
                            "Add first pet",
                            variant="outline",
                            onClick=lambda: form.add_pet(member_idx),
                        ),
                        Stack(gap="xs")[
                            ps.For(
                                list(range(len(pets))),
                                lambda pet_idx: render_pet(member_idx, pet_idx),
                            )
                        ],
                    ),
                ],
            ],
        ]

    async def submit(values: dict[str, Any]):
        print("Submitted:", json.dumps(values, indent=2))

    return MantineProvider(withNormalizeCSS=True, withGlobalStyles=True)[
        Stack(gap="lg", p="lg", maw=780, mx="auto")[
            Title(order=2)["Dynamic household form"],
            Text(color="dimmed")[
                "Add people and their pets. Try editing values to see them stay in sync with the server even before submit."
            ],
            form.render(onSubmit=submit)[
                TextInput(
                    name="householdName",
                    label="Household name",
                    placeholder="The Explorers",
                ),
                ps.If(
                    len(members) == 0,
                    Button("Add first member", mt="md", onClick=form.add_member),
                    Stack(gap="md")[
                        ps.For(list(range(len(members))), render_member),
                        Group(mt="md", gap="sm")[
                            Button(
                                "Add another member",
                                variant="light",
                                onClick=form.add_member,
                            ),
                            Button("Submit", type="submit"),
                        ],
                    ],
                ),
            ],
            Card(withBorder=True, shadow="sm")[
                Title(order=5)["Server-side snapshot"],
                Text(color="dimmed", size="sm", mb="xs")[
                    "Live values stored on the Python side (syncMode='onChange'):"
                ],
                ps.pre(
                    style={
                        "fontFamily": "monospace",
                        "fontSize": "12px",
                        "background": "var(--mantine-color-gray-1)",
                        "padding": "12px",
                        "borderRadius": "8px",
                        "whiteSpace": "pre-wrap",
                    }
                )[json.dumps(ps.unwrap(form.values), indent=2)],
            ],
        ]
    ]


app = ps.App([ps.Route("/", HouseholdFormDemo)])

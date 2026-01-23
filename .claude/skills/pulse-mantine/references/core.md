# Mantine Core Components

All `@mantine/core` components wrapped for Pulse. Props mirror Mantine docs exactly.

## Layout

### Stack
Vertical flex container with gap.
```python
Stack(gap="md", align="center", justify="flex-start")[
    Text("Item 1"),
    Text("Item 2"),
]
```
Props: `gap`, `align`, `justify`

### Group
Horizontal flex container with gap.
```python
Group(gap="sm", justify="space-between")[
    Button("Cancel", variant="outline"),
    Button("Submit"),
]
```
Props: `gap`, `justify`, `align`, `wrap`, `grow`, `preventGrowOverflow`

### Grid / GridCol
CSS grid layout.
```python
Grid(gutter="md")[
    GridCol(span=6)[Content1()],
    GridCol(span=6)[Content2()],
    GridCol(span={"base": 12, "md": 6})[Responsive()],  # responsive span
]
```
Props: `gutter`, `grow`, `columns`, `justify`, `align`
GridCol props: `span`, `offset`, `order`

### Flex
Flexbox container.
```python
Flex(direction="row", wrap="wrap", gap="md")[items]
```
Props: `direction`, `wrap`, `gap`, `justify`, `align`, `rowGap`, `columnGap`

### Container
Centered container with max-width.
```python
Container(size="sm")[Content()]  # sizes: xs, sm, md, lg, xl
```
Props: `size`, `fluid`

### Center
Center content horizontally and vertically.
```python
Center(h=200)[Loader()]
```
Props: `inline`

### Space
Add vertical/horizontal space.
```python
Space(h="md")  # vertical space
Space(w="xl")  # horizontal space
```

### SimpleGrid
Simple responsive grid.
```python
SimpleGrid(cols={"base": 1, "sm": 2, "lg": 4}, spacing="md")[items]
```
Props: `cols`, `spacing`, `verticalSpacing`

### AspectRatio
Maintain aspect ratio.
```python
AspectRatio(ratio=16/9)[Image(src="...")]
```

### AppShell
Application layout with header, navbar, aside, footer.
```python
AppShell(
    header={"height": 60},
    navbar={"width": 300, "breakpoint": "sm", "collapsed": {"mobile": not opened}},
)[
    AppShellHeader()[Header()],
    AppShellNavbar()[Navbar()],
    AppShellMain()[Content()],
]
```
Subcomponents: `AppShellHeader`, `AppShellNavbar`, `AppShellAside`, `AppShellFooter`, `AppShellMain`, `AppShellSection`

## Inputs

### TextInput
```python
TextInput(
    name="email",  # for forms
    label="Email",
    placeholder="you@example.com",
    description="Your work email",
    error="Invalid email",  # manual error
    withAsterisk=True,
    leftSection=Icon(),
    rightSection=Button(),
)
```

### Textarea
```python
Textarea(name="bio", label="Bio", minRows=3, maxRows=6, autosize=True)
```

### NumberInput
```python
NumberInput(
    name="age",
    label="Age",
    min=0,
    max=120,
    step=1,
    allowNegative=False,
    decimalScale=0,
)
```

### PasswordInput
```python
PasswordInput(name="password", label="Password", visible=False)
```
Props: `visible`, `visibilityToggleIcon`, `visibilityToggleButtonProps`

### Select
```python
Select(
    name="country",
    label="Country",
    data=["USA", "Canada", "Mexico"],
    # or with values:
    data=[
        {"value": "us", "label": "United States"},
        {"value": "ca", "label": "Canada"},
    ],
    searchable=True,
    clearable=True,
    nothingFoundMessage="No options",
)
```

### MultiSelect
```python
MultiSelect(
    name="tags",
    label="Tags",
    data=["React", "Vue", "Angular"],
    maxValues=3,
    searchable=True,
)
```

### Checkbox
```python
Checkbox(name="agree", label="I agree to terms")
CheckboxGroup(name="features", label="Features")[
    Checkbox(value="a", label="Feature A"),
    Checkbox(value="b", label="Feature B"),
]
```

### Switch
```python
Switch(name="notifications", label="Enable notifications", onLabel="ON", offLabel="OFF")
```

### Radio
```python
RadioGroup(name="plan", label="Plan")[
    Radio(value="free", label="Free"),
    Radio(value="pro", label="Pro"),
]
```

### Slider / RangeSlider
```python
Slider(name="volume", min=0, max=100, step=1, marks=[{"value": 50, "label": "50%"}])
RangeSlider(name="priceRange", min=0, max=1000, minRange=100)
```

### ColorInput / ColorPicker
```python
ColorInput(name="color", label="Pick color", format="hex", swatches=["#ff0000", "#00ff00"])
ColorPicker(format="rgba", swatchesPerRow=8)
```

### FileInput
```python
FileInput(
    name="avatar",
    label="Upload avatar",
    accept="image/*",
    multiple=False,
    clearable=True,
)
```

### PinInput
```python
PinInput(name="otp", length=6, type="number", mask=True)
```

### JsonInput
```python
JsonInput(name="config", label="JSON Config", formatOnBlur=True, autosize=True, minRows=4)
```

### Rating
```python
Rating(name="rating", count=5, fractions=2)
```

### Autocomplete
```python
Autocomplete(
    name="search",
    label="Search",
    data=["React", "Vue", "Angular"],
    limit=5,
)
```

### TagsInput
```python
TagsInput(
    name="tags",
    label="Tags",
    data=["existing", "tags"],  # suggestions
    maxTags=5,
    allowDuplicates=False,
)
```

### Fieldset
```python
Fieldset(legend="Personal Info")[
    TextInput(name="name"),
    TextInput(name="email"),
]
```

### Input (base)
Low-level input wrapper.
```python
Input(component="input", placeholder="Custom input")
InputWrapper(label="Field", description="Help text", error="Error")[
    Input()
]
```

## Buttons

### Button
```python
Button(
    "Click me",
    variant="filled",  # filled, light, outline, transparent, white, subtle, default, gradient
    color="blue",
    size="md",  # xs, sm, md, lg, xl
    radius="md",
    loading=is_loading,
    disabled=is_disabled,
    leftSection=Icon(),
    rightSection=Icon(),
    fullWidth=True,
    onClick=handle_click,
)
ButtonGroup()[Button("A"), Button("B")]
```

### ActionIcon
Icon-only button.
```python
ActionIcon(
    variant="filled",
    color="blue",
    size="lg",
    radius="xl",
    onClick=handle,
)[IconPlus()]
ActionIconGroup()[ActionIcon()[Icon1()], ActionIcon()[Icon2()]]
```

### CloseButton
```python
CloseButton(onClick=close, size="md")
```

### CopyButton
```python
CopyButton(value="text to copy")[
    lambda copied: Button("Copied!" if copied else "Copy")
]
```

### FileButton
```python
FileButton(onChange=handle_file, accept="image/*")[
    lambda on_click: Button("Upload", onClick=on_click)
]
```

### UnstyledButton
```python
UnstyledButton(onClick=handle)[Custom content]
```

## Overlays

### Modal
```python
with ps.init():
    opened = ps.use_state(False)

Modal(
    opened=opened.value,
    onClose=lambda: opened.set(False),
    title="Modal Title",
    size="md",  # xs, sm, md, lg, xl, or number
    centered=True,
    withCloseButton=True,
    closeOnClickOutside=True,
    closeOnEscape=True,
    overlayProps={"blur": 3},
)[
    ModalBody()[Content()],
]
```
Compound: `ModalRoot`, `ModalOverlay`, `ModalContent`, `ModalHeader`, `ModalTitle`, `ModalCloseButton`, `ModalBody`

### Drawer
```python
Drawer(
    opened=opened.value,
    onClose=close,
    title="Drawer",
    position="right",  # left, right, top, bottom
    size="md",
)[Content()]
```
Compound: `DrawerRoot`, `DrawerOverlay`, `DrawerContent`, `DrawerHeader`, `DrawerTitle`, `DrawerCloseButton`, `DrawerBody`

### Menu
```python
Menu(shadow="md", width=200)[
    MenuTarget()[Button("Open menu")],
    MenuDropdown()[
        MenuLabel()["Application"],
        MenuItem(leftSection=IconSettings())["Settings"],
        MenuItem(color="red", leftSection=IconTrash())["Delete"],
        MenuDivider(),
        MenuSub()[
            MenuTarget()[MenuItem()["More"]],
            MenuDropdown()[MenuItem()["Sub item"]],
        ],
    ],
]
```

### Popover
```python
Popover(width=200, position="bottom", withArrow=True, shadow="md")[
    PopoverTarget()[Button("Toggle")],
    PopoverDropdown()[Content()],
]
```

### Tooltip
```python
Tooltip(label="Tooltip text", position="top", withArrow=True)[
    Button("Hover me")
]
TooltipGroup(openDelay=300, closeDelay=100)[tooltips]  # shared delay
TooltipFloating(label="Floating")[target]  # follows cursor
```

### HoverCard
```python
HoverCard(width=280, shadow="md")[
    HoverCardTarget()[Text("Hover")],
    HoverCardDropdown()[Content()],
]
```

### Dialog
Non-modal dialog.
```python
Dialog(opened=opened, withCloseButton=True, onClose=close, size="lg", radius="md")[
    Text("Dialog content")
]
```

### LoadingOverlay
```python
LoadingOverlay(visible=is_loading, overlayBlur=2)
```

### Overlay
```python
Overlay(color="#000", backgroundOpacity=0.5, blur=3)
```

### Affix
Fixed position element.
```python
Affix(position={"bottom": 20, "right": 20})[
    Button("Scroll to top", onClick=scroll_top)
]
```

## Feedback

### Alert
```python
Alert(
    title="Warning",
    color="yellow",
    icon=IconAlertCircle(),
    withCloseButton=True,
    onClose=handle_close,
)["Alert message content"]
```

### Notification
```python
Notification(
    title="Success",
    color="green",
    icon=IconCheck(),
    withCloseButton=True,
    onClose=close,
)["Operation completed"]
```

### Notifications (toast system)
```python
from pulse_mantine import Notifications, notifications

# Add to layout:
Notifications(position="top-right")

# Show notification:
notifications.show(
    title="Success",
    message="File uploaded",
    color="green",
    autoClose=5000,
)
notifications.update(id="...", title="Updated")
notifications.hide(id="...")
notifications.clean()
notifications.cleanQueue()
```

### Progress
```python
Progress(value=50, color="blue", size="md", striped=True, animated=True)
# Sections:
ProgressRoot(size="xl")[
    ProgressSection(value=40, color="cyan"),
    ProgressSection(value=30, color="pink"),
]
```

### RingProgress
```python
RingProgress(
    sections=[
        {"value": 40, "color": "cyan"},
        {"value": 30, "color": "orange"},
    ],
    label=Center()[Text("70%")],
)
```

### Loader
```python
Loader(color="blue", size="md", type="bars")  # oval, bars, dots
```

### Skeleton
```python
Skeleton(height=50, radius="md", animate=True)
Skeleton(height=8, width="70%", mt=6)
```

## Data Display

### Card
```python
Card(shadow="sm", padding="lg", radius="md", withBorder=True)[
    CardSection()[Image(src="...")],
    Text("Card content", mt="md"),
]
```

### Table
```python
Table(striped=True, highlightOnHover=True, withTableBorder=True, withColumnBorders=True)[
    TableThead()[
        TableTr()[
            TableTh()["Name"],
            TableTh()["Email"],
        ]
    ],
    TableTbody()[
        TableTr()[
            TableTd()["John"],
            TableTd()["john@example.com"],
        ]
    ],
]
# Or with data:
TableDataRenderer(
    data={
        "head": ["Name", "Email"],
        "body": [["John", "john@..."], ["Jane", "jane@..."]],
    }
)
```

### Accordion
```python
Accordion(defaultValue="item1", variant="contained")[
    AccordionItem(value="item1")[
        AccordionControl()["Section 1"],
        AccordionPanel()["Content 1"],
    ],
    AccordionItem(value="item2")[
        AccordionControl()["Section 2"],
        AccordionPanel()["Content 2"],
    ],
]
```
Props: `multiple`, `variant` (default, contained, filled, separated), `chevronPosition`

### Badge
```python
Badge(color="blue", variant="filled", size="md", radius="sm")["Badge text"]
```
Variants: filled, light, outline, dot, gradient

### Avatar
```python
Avatar(src="url", alt="Name", radius="xl", size="lg", color="blue")
AvatarGroup(spacing="sm")[avatars]
```

### Image
```python
Image(src="url", alt="Description", radius="md", h=200, w="auto", fit="cover", fallbackSrc="fallback.png")
```

### BackgroundImage
```python
BackgroundImage(src="url", radius="md")[Content()]
```

### ThemeIcon
```python
ThemeIcon(variant="filled", color="blue", size="lg", radius="md")[Icon()]
```

### Indicator
```python
Indicator(color="red", size=12, processing=True, position="top-end")[
    Avatar(src="...")
]
```

### Spoiler
```python
Spoiler(maxHeight={120}, showLabel="Show more", hideLabel="Hide")[
    LongContent()
]
```

### Timeline
```python
Timeline(active=1, bulletSize={24}, lineWidth={2})[
    TimelineItem(bullet=Icon(), title="Step 1")["Description"],
    TimelineItem(bullet=Icon(), title="Step 2")["Description"],
]
```

### Kbd
```python
Kbd()["Ctrl"]
Group()[Kbd()["Ctrl"], Text("+"), Kbd()["K"]]
```

### ColorSwatch
```python
ColorSwatch(color="#ff0000", size={30})
```

### NumberFormatter
```python
NumberFormatter(value=1234.56, prefix="$", thousandSeparator=",", decimalScale=2)
```

## Navigation

### Tabs
```python
Tabs(defaultValue="first", orientation="horizontal", variant="default")[
    TabsList()[
        TabsTab("First Tab", value="first", leftSection=Icon()),
        TabsTab("Second Tab", value="second"),
    ],
    TabsPanel(value="first")["First panel content"],
    TabsPanel(value="second")["Second panel content"],
]
```
Variants: default, outline, pills

### NavLink
```python
NavLink(
    label="Dashboard",
    leftSection=Icon(),
    rightSection=Badge(),
    active=is_active,
    onClick=navigate,
    href="/dashboard",
    childrenOffset={28},
)[
    NavLink(label="Sub item", href="/sub"),
]
```

### Breadcrumbs
```python
Breadcrumbs(separator="→")[
    Anchor(href="/")["Home"],
    Anchor(href="/products")["Products"],
    Text()["Current"],
]
```

### Pagination
```python
Pagination(
    total=10,
    value=page,
    onChange=set_page,
    withEdges=True,
    siblings=1,
    boundaries=1,
)
```

### Stepper
```python
Stepper(active=active_step, onStepClick=set_step)[
    StepperStep(label="Step 1", description="Create account")[
        Step1Content()
    ],
    StepperStep(label="Step 2", description="Verify email")[
        Step2Content()
    ],
    StepperCompleted()[Done()],
]
```

### Anchor
```python
Anchor(href="/page", target="_blank", underline="hover")["Link text"]
```

### Burger
```python
Burger(opened=nav_opened, onClick=toggle, size="sm")
```

## Typography

### Text
```python
Text(
    "Text content",
    size="md",  # xs, sm, md, lg, xl
    fw=500,  # font weight
    c="dimmed",  # color: dimmed, red, blue, etc.
    ta="center",  # text-align
    td="underline",  # text-decoration
    tt="uppercase",  # text-transform
    truncate=True,  # or "end", "start"
    lineClamp=2,
    inherit=True,  # inherit parent styles
)
```

### Title
```python
Title("Heading", order=1)  # order 1-6 = h1-h6
Title("Subheading", order=2, c="dimmed")
```

### Highlight
```python
Highlight("Search results for react", highlight="react", highlightStyles={"background": "yellow"})
Highlight("Multiple words", highlight=["multiple", "words"])
```

### Mark
```python
Mark(color="yellow")["Marked text"]
```

### Code
```python
Code()["inline code"]
Code(block=True)["code block"]
```

### Blockquote
```python
Blockquote(cite="– Author", icon=Icon())["Quote text"]
```

### List
```python
List(type="ordered", withPadding=True, spacing="sm")[
    ListItem()["Item 1"],
    ListItem()["Item 2"],
    ListItem()[
        "Nested",
        List()[ListItem()["Sub item"]],
    ],
]
```

## Miscellaneous

### Paper
Surface with shadow.
```python
Paper(shadow="xs", radius="md", p="xl", withBorder=True)[Content()]
```

### Box
Base component for custom styling.
```python
Box(p="md", bg="gray.1", style={"borderRadius": 8})[Content()]
```

### Divider
```python
Divider(my="md", label="Or", labelPosition="center", variant="dashed")
```

### ScrollArea
```python
ScrollArea(h={250}, type="auto", offsetScrollbars=True)[LongContent()]
ScrollAreaAutosize(maxHeight={300})[Content()]
```

### Collapse
```python
Collapse(in_=is_open, transitionDuration=200)[Content()]
```

### Transition
```python
Transition(mounted=is_visible, transition="fade", duration=400)[
    lambda styles: Box(style=styles)[Content()]
]
```

### Portal
Render outside parent DOM.
```python
Portal()[OverlayContent()]
```

### FocusTrap
```python
FocusTrap(active=is_open)[ModalContent()]
```

### VisuallyHidden
```python
VisuallyHidden()["Screen reader only text"]
```

## Style Props

All components accept Mantine style props:
- Spacing: `m`, `mt`, `mb`, `ml`, `mr`, `mx`, `my`, `p`, `pt`, `pb`, `pl`, `pr`, `px`, `py`
- Size: `w`, `h`, `miw`, `maw`, `mih`, `mah`
- Colors: `c` (text color), `bg` (background)
- Display: `display`, `hiddenFrom`, `visibleFrom`

```python
Button("Click", mt="md", px="xl", c="white", bg="blue")
```

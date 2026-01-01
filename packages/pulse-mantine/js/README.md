# Pulse Mantine (JS)

JavaScript/TypeScript companion library for pulse-mantine Python bindings. Provides client-side form integration, notifications, and date handling.

## Architecture

Extends the Mantine React components with Pulse-specific functionality for form state management and real-time updates.

```
Python pulse_mantine → VDOM → pulse-client → pulse-mantine JS → Mantine React
```

## Folder Structure

```
src/
├── index.ts              # Public exports
├── dates.tsx             # Date component integrations
├── notifications.tsx     # Notification system
├── tree.tsx              # Tree component state
│
└── form/                 # Form state management
    ├── form.tsx          # MantineFormProvider
    ├── connect.tsx       # createConnectedField, useFieldProps
    ├── context.tsx       # Form context
    ├── fields.tsx        # Field components
    └── validators.ts     # Client-side validators
```

## Key Concepts

### Form Integration

Bridges Python form definitions to client-side Mantine form state:

```tsx
// Automatically connected via pulse-mantine Python
// Form state syncs between server and client
<MantineFormProvider form={form}>
  <TextInput {...form.getInputProps("email")} />
</MantineFormProvider>
```

### Connected Fields

`createConnectedField` wraps Mantine inputs for automatic form binding:

```tsx
import { createConnectedField } from "pulse-mantine";

const ConnectedTextInput = createConnectedField(TextInput);
```

### Notifications

Server-triggered notifications:

```python
# Python
from pulse_mantine import notifications
notifications.show(title="Success", message="Saved!")
```

```tsx
// Rendered via JS notifications API
import { notifications } from "pulse-mantine";
```

### Date Components

Client-side date handling with dayjs integration for DatesProvider, DatePicker, etc.

## Main Exports

**Form**:
- `createConnectedField(Component)` - wrap input for form binding
- `useFieldProps(name)` - get field props from form context

**Notifications**:
- `notifications` - notification API
- `showNotification`, `updateNotification`, `hideNotification`

**Context**:
- `MantineFormContext` - form context
- `useMantineForm()` - access form state

**Tree**:
- Tree state management utilities

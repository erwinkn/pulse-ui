import React, { type ComponentProps } from "react";
import {
  Calendar,
  CalendarHeader,
  DatesProvider,
  Day,
  DecadeLevel,
  DecadeLevelGroup,
  HiddenDatesInput,
  LevelsGroup,
  MiniCalendar,
  Month,
  MonthLevel,
  MonthLevelGroup,
  MonthsList,
  PickerControl,
  PickerInputBase,
  TimeGrid,
  TimeValue,
  WeekdaysRow,
  YearLevel,
  YearLevelGroup,
  YearsList,
  DateInput as MantineDateInput,
  DatePicker as MantineDatePicker,
  DatePickerInput as MantineDatePickerInput,
  DateTimePicker as MantineDateTimePicker,
  MonthPicker as MantineMonthPicker,
  MonthPickerInput as MantineMonthPickerInput,
  TimeInput as MantineTimeInput,
  TimePicker as MantineTimePicker,
  YearPicker as MantineYearPicker,
  YearPickerInput as MantineYearPickerInput,
} from "@mantine/dates";
import { useFormContext } from "./form/context";

type ChangeHandler = (...args: any[]) => void;

interface ConnectedFieldOptions {
  coerceEmptyString?: boolean;
}

function createConnectedField<
  P extends { name?: string; onChange?: ChangeHandler },
>(Component: React.ComponentType<P>, options?: ConnectedFieldOptions) {
  const ConnectedField = (props: P) => {
    const name = props.name;
    const ctx = useFormContext();
    if (name && ctx) {
      const mantineProps = ctx.getInputProps(name);
      const isControlled = mantineProps.hasOwnProperty("value");
      if (
        isControlled &&
        options?.coerceEmptyString &&
        mantineProps.value == null
      ) {
        mantineProps.value = "";
      }
      return <Component {...props} {...mantineProps} />;
    }
    return <Component {...props} />;
  };
  const display =
    (Component as any).displayName || Component.name || "Component";
  ConnectedField.displayName = `Connected${display}`;
  return ConnectedField;
}

export type DateInputProps = ComponentProps<typeof MantineDateInput> & {
  name?: string;
};
export const DateInput = createConnectedField<DateInputProps>(
  MantineDateInput as any
);

export type DatePickerProps = ComponentProps<typeof MantineDatePicker> & {
  name?: string;
};
export const DatePicker = createConnectedField<DatePickerProps>(
  MantineDatePicker as any
);

export type DatePickerInputProps = ComponentProps<
  typeof MantineDatePickerInput
> & {
  name?: string;
};
export const DatePickerInput = createConnectedField<DatePickerInputProps>(
  MantineDatePickerInput as any
);

export type DateTimePickerProps = ComponentProps<
  typeof MantineDateTimePicker
> & {
  name?: string;
};
export const DateTimePicker = createConnectedField<DateTimePickerProps>(
  MantineDateTimePicker as any
);

export type TimeInputProps = ComponentProps<typeof MantineTimeInput> & {
  name?: string;
};
export const TimeInput = createConnectedField<TimeInputProps>(
  MantineTimeInput as any,
  {
    coerceEmptyString: true,
  }
);

export type TimePickerProps = ComponentProps<typeof MantineTimePicker> & {
  name?: string;
};
export const TimePicker = createConnectedField<TimePickerProps>(
  MantineTimePicker as any,
  {
    coerceEmptyString: true,
  }
);

export type MonthPickerInputProps = ComponentProps<
  typeof MantineMonthPickerInput
> & {
  name?: string;
};
export const MonthPickerInput = createConnectedField<MonthPickerInputProps>(
  MantineMonthPickerInput as any
);

export type MonthPickerProps = ComponentProps<typeof MantineMonthPicker> & {
  name?: string;
};
export const MonthPicker = createConnectedField<MonthPickerProps>(
  MantineMonthPicker as any
);

export type YearPickerInputProps = ComponentProps<
  typeof MantineYearPickerInput
> & {
  name?: string;
};
export const YearPickerInput = createConnectedField<YearPickerInputProps>(
  MantineYearPickerInput as any
);

export type YearPickerProps = ComponentProps<typeof MantineYearPicker> & {
  name?: string;
};
export const YearPicker = createConnectedField<YearPickerProps>(
  MantineYearPicker as any
);

export {
  Calendar,
  CalendarHeader,
  DatesProvider,
  Day,
  DecadeLevel,
  DecadeLevelGroup,
  HiddenDatesInput,
  LevelsGroup,
  MiniCalendar,
  Month,
  MonthLevel,
  MonthLevelGroup,
  MonthsList,
  PickerControl,
  PickerInputBase,
  TimeGrid,
  TimeValue,
  WeekdaysRow,
  YearLevel,
  YearLevelGroup,
  YearsList,
};

export type {
  DatePickerType,
  DateValue,
  DatesRangeValue,
} from "@mantine/dates";

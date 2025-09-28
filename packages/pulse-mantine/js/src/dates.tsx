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

import { createConnectedField } from "./form/connect";

export const DateInput = createConnectedField(MantineDateInput);
export const DatePicker = createConnectedField(MantineDatePicker);
export const DatePickerInput = createConnectedField(MantineDatePickerInput);

export const DateTimePicker = createConnectedField(MantineDateTimePicker);
export const TimeInput = createConnectedField(MantineTimeInput, {
  coerceEmptyString: true,
  debounceOnChange: true,
});
export const TimePicker = createConnectedField(MantineTimePicker, {
  coerceEmptyString: true,
  debounceOnChange: true,
});
export const MonthPickerInput = createConnectedField(MantineMonthPickerInput);
export const MonthPicker = createConnectedField(MantineMonthPicker);
export const YearPickerInput = createConnectedField(MantineYearPickerInput);
export const YearPicker = createConnectedField(MantineYearPicker);

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

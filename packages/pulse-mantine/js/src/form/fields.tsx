import {
  TextInput as MantineTextInput,
  NumberInput as MantineNumberInput,
  Checkbox as MantineCheckbox,
  SegmentedControl as MantineSegmentedControl,
  Select as MantineSelect,
  Textarea as MantineTextarea,
  Switch as MantineSwitch,
  Slider as MantineSlider,
  RangeSlider as MantineRangeSlider,
  NativeSelect as MantineNativeSelect,
  PasswordInput as MantinePasswordInput,
  PinInput as MantinePinInput,
  JsonInput as MantineJsonInput,
  ColorInput as MantineColorInput,
  ColorPicker as MantineColorPicker,
  AngleSlider as MantineAngleSlider,
  Rating as MantineRating,
  Chip as MantineChip,
  Radio as MantineRadio,
  FileInput as MantineFileInput,
} from "@mantine/core";

import { createConnectedField } from "./connect";

export const TextInput = createConnectedField(MantineTextInput, {
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const NumberInput = createConnectedField(MantineNumberInput, {
  inputType: "input",
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const Checkbox = createConnectedField(MantineCheckbox, {
  inputType: "checkbox",
});
export const SegmentedControl = createConnectedField(MantineSegmentedControl);
export const Select = createConnectedField(MantineSelect);
export const Textarea = createConnectedField(MantineTextarea, {
  coerceEmptyString: true,
  debounceOnChange: true,
});
export const Switch = createConnectedField(MantineSwitch, {
  inputType: "checkbox",
});
export const Slider = createConnectedField(MantineSlider);
export const RangeSlider = createConnectedField(MantineRangeSlider);
export const NativeSelect = createConnectedField(MantineNativeSelect);
export const PasswordInput = createConnectedField(MantinePasswordInput, {
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const PinInput = createConnectedField(MantinePinInput, {
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const JsonInput = createConnectedField(MantineJsonInput, {
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const ColorInput = createConnectedField(MantineColorInput, {
  debounceOnChange: true,
  coerceEmptyString: true,
});
export const ColorPicker = createConnectedField(MantineColorPicker);
export const AngleSlider = createConnectedField(MantineAngleSlider);
export const Rating = createConnectedField(MantineRating);
export const Chip = createConnectedField(MantineChip);
// Only Radio component that needs to be registered as a form input
export const RadioGroup = createConnectedField(MantineRadio.Group);
export const FileInput = createConnectedField(MantineFileInput, {
  // transform: ({ bind, rest, props, context }) => {
  //   if (!props.name) {
  //     return { bind, rest };
  //   }
  //   const { onChange, ...restWithoutOnChange } = rest as any;
  //   return {
  //     bind: {
  //       ...bind,
  //       onChange: (payload: any) => {
  //         context.setFieldValue(props.name!, payload);
  //         onChange?.(payload);
  //       },
  //     },
  //     rest: restWithoutOnChange,
  //   };
  // },
});

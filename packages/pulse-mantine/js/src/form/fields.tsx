import React, { type ComponentProps } from "react";
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
import { useFormContext } from "./context";

type TextInputProps = ComponentProps<typeof MantineTextInput> & { name?: string };
type NumberInputProps = ComponentProps<typeof MantineNumberInput> & { name?: string };
type CheckboxProps = ComponentProps<typeof MantineCheckbox> & { name?: string };
type SegmentedControlProps = ComponentProps<typeof MantineSegmentedControl> & { name?: string };
type SelectProps = ComponentProps<typeof MantineSelect> & { name?: string };
type TextareaProps = ComponentProps<typeof MantineTextarea> & { name?: string };
type SwitchProps = ComponentProps<typeof MantineSwitch> & { name?: string };
type SliderProps = ComponentProps<typeof MantineSlider> & { name?: string };
type RangeSliderProps = ComponentProps<typeof MantineRangeSlider> & { name?: string };
type NativeSelectProps = ComponentProps<typeof MantineNativeSelect> & { name?: string };
type PasswordInputProps = ComponentProps<typeof MantinePasswordInput> & { name?: string };
type PinInputProps = ComponentProps<typeof MantinePinInput> & { name?: string };
type JsonInputProps = ComponentProps<typeof MantineJsonInput> & { name?: string };
type ColorInputProps = ComponentProps<typeof MantineColorInput> & { name?: string };
type ColorPickerProps = ComponentProps<typeof MantineColorPicker> & { name?: string };
type AngleSliderProps = ComponentProps<typeof MantineAngleSlider> & { name?: string };
type RatingProps = ComponentProps<typeof MantineRating> & { name?: string };
type ChipProps = ComponentProps<typeof MantineChip> & { name?: string };
type RadioGroupProps = ComponentProps<typeof MantineRadio.Group> & { name?: string };
type RadioProps = ComponentProps<typeof MantineRadio>;
type FileInputProps = ComponentProps<typeof MantineFileInput> & { name?: string };

export function TextInput(props: TextInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineTextInput {...bind} {...rest} />;
}

export function NumberInput(props: NumberInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name, { type: "input" }) : {};
  return <MantineNumberInput {...bind} {...rest} />;
}

export function Checkbox(props: CheckboxProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name, { type: "checkbox" }) : {};
  return <MantineCheckbox {...bind} {...rest} />;
}

export function SegmentedControl(props: SegmentedControlProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineSegmentedControl {...bind} {...rest} />;
}

export function Select(props: SelectProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineSelect {...bind} {...rest} />;
}

export function Textarea(props: TextareaProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineTextarea {...bind} {...rest} />;
}

export function Switch(props: SwitchProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name, { type: "checkbox" }) : {};
  return <MantineSwitch {...bind} {...rest} />;
}

export function Slider(props: SliderProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineSlider {...bind} {...rest} />;
}

export function RangeSlider(props: RangeSliderProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineRangeSlider {...bind} {...rest} />;
}

export function NativeSelect(props: NativeSelectProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineNativeSelect {...bind} {...rest} />;
}

export function PasswordInput(props: PasswordInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantinePasswordInput {...bind} {...rest} />;
}

export function PinInput(props: PinInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantinePinInput {...bind} {...rest} />;
}

export function JsonInput(props: JsonInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineJsonInput {...bind} {...rest} />;
}

export function ColorInput(props: ColorInputProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineColorInput {...bind} {...rest} />;
}

export function ColorPicker(props: ColorPickerProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineColorPicker {...bind} {...rest} />;
}

export function AngleSlider(props: AngleSliderProps) {
  const { name, ...rest } = props;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineAngleSlider {...bind} {...rest} />;
}

export function Rating(props: RatingProps) {
  const { name, ...rest } = props as any;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineRating {...bind} {...(rest as any)} />;
}

export function Chip(props: ChipProps) {
  const { name, ...rest } = props as any;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineChip {...bind} {...(rest as any)} />;
}

export function Radio(props: RadioProps) {
  return <MantineRadio {...props} />;
}

export function RadioGroup(props: RadioGroupProps) {
  const { name, ...rest } = props as any;
  const ctx = useFormContext();
  const bind = name && ctx ? ctx.getInputProps(name) : {};
  return <MantineRadio.Group {...bind} {...(rest as any)} />;
}

export function FileInput(props: FileInputProps) {
  const { name, onChange, ...rest } = props as any;
  const ctx = useFormContext();
  if (name && ctx) {
    const handleChange: any = (payload: any) => {
      ctx.form.setFieldValue(name, payload);
      onChange?.(payload);
    };
    return <MantineFileInput onChange={handleChange} {...(rest as any)} />;
  }
  return <MantineFileInput {...(props as any)} />;
}

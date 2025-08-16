import React, { useState } from "react";
import DatePicker from "react-datepicker";
import "react-datepicker/dist/react-datepicker.css";

interface CustomDatePickerProps {
  value?: string;
  onChange?: (date: string) => void;
  placeholder?: string;
  className?: string;
  minDate?: Date;
  maxDate?: Date;
  showTimeSelect?: boolean;
  timeFormat?: string;
  timeIntervals?: number;
  dateFormat?: string;
  disabled?: boolean;
}

const CustomDatePicker: React.FC<CustomDatePickerProps> = ({
  value,
  onChange,
  placeholder = "Select a date",
  className = "",
  minDate,
  maxDate,
  showTimeSelect = false,
  timeFormat = "HH:mm",
  timeIntervals = 15,
  dateFormat = showTimeSelect ? "MM/dd/yyyy HH:mm" : "MM/dd/yyyy",
  disabled = false,
}) => {
  console.log("Rendering CustomDatePicker");
  const [selectedDate, setSelectedDate] = useState<Date | null>(
    value ? new Date(value) : null
  );

  const handleChange = (date: Date | null) => {
    setSelectedDate(date);
    if (onChange && date) {
      // Format date to ISO string for consistent handling
      onChange(date.toISOString());
    } else if (onChange) {
      onChange("");
    }
  };

  return (
    <div className={`relative ${className}`}>
      <DatePicker
        selected={selectedDate}
        onChange={handleChange}
        placeholderText={placeholder}
        minDate={minDate}
        maxDate={maxDate}
        showTimeSelect={showTimeSelect}
        timeFormat={timeFormat}
        timeIntervals={timeIntervals}
        dateFormat={dateFormat}
        disabled={disabled}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
        calendarClassName="shadow-lg border border-gray-200 rounded-lg"
        popperClassName="z-50"
        showPopperArrow={false}
      />
    </div>
  );
};

export default CustomDatePicker;

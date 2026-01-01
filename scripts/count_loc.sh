#!/bin/bash
# Count lines of code in library source directories (excludes tests, deps, etc.)

count_loc() {
    local name=$1
    local path=$2
    local ext=$3

    if [ -d "$path" ]; then
        local count=$(find "$path" -name "*.$ext" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
        echo "${count:-0}"
    else
        echo "0"
    fi
}

# Package counts
pulse_py=$(count_loc "pulse" "packages/pulse/python/src" "py")
pulse_js=$(count_loc "pulse" "packages/pulse/js/src" "ts")
pulse_jsx=$(count_loc "pulse" "packages/pulse/js/src" "tsx")
pulse_ts=$((pulse_js + pulse_jsx))

mantine_py=$(count_loc "pulse-mantine" "packages/pulse-mantine/python/src" "py")
mantine_js=$(count_loc "pulse-mantine" "packages/pulse-mantine/js/src" "ts")
mantine_jsx=$(count_loc "pulse-mantine" "packages/pulse-mantine/js/src" "tsx")
mantine_ts=$((mantine_js + mantine_jsx))

ag_grid_py=$(count_loc "pulse-ag-grid" "packages/pulse-ag-grid/src" "py")
lucide_py=$(count_loc "pulse-lucide" "packages/pulse-lucide/src" "py")
recharts_py=$(count_loc "pulse-recharts" "packages/pulse-recharts/src" "py")
msal_py=$(count_loc "pulse-msal" "packages/pulse-msal/src" "py")
aws_py=$(count_loc "pulse-aws" "packages/pulse-aws/src" "py")

# Totals
total_py=$((pulse_py + mantine_py + ag_grid_py + lucide_py + recharts_py + msal_py + aws_py))
total_ts=$((pulse_ts + mantine_ts))
grand_total=$((total_py + total_ts))

# Output
printf "%-20s %10s %10s %10s\n" "Package" "Python" "JS/TS" "Total"
printf "%-20s %10s %10s %10s\n" "-------" "------" "-----" "-----"
printf "%-20s %10d %10d %10d\n" "pulse" "$pulse_py" "$pulse_ts" "$((pulse_py + pulse_ts))"
printf "%-20s %10d %10d %10d\n" "pulse-mantine" "$mantine_py" "$mantine_ts" "$((mantine_py + mantine_ts))"
printf "%-20s %10d %10s %10d\n" "pulse-ag-grid" "$ag_grid_py" "-" "$ag_grid_py"
printf "%-20s %10d %10s %10d\n" "pulse-lucide" "$lucide_py" "-" "$lucide_py"
printf "%-20s %10d %10s %10d\n" "pulse-recharts" "$recharts_py" "-" "$recharts_py"
printf "%-20s %10d %10s %10d\n" "pulse-msal" "$msal_py" "-" "$msal_py"
printf "%-20s %10d %10s %10d\n" "pulse-aws" "$aws_py" "-" "$aws_py"
printf "%-20s %10s %10s %10s\n" "-------" "------" "-----" "-----"
printf "%-20s %10d %10d %10d\n" "TOTAL" "$total_py" "$total_ts" "$grand_total"

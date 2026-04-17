# Repository Guidelines

## Project Structure & Module Organization
The firmware entrypoint lives in `main/`, with `main.cpp`, shared `commons.*`, hardware drivers such as `st7789.*`, and FreeRTOS tasks under `main/tasks/`. Shared component code (LVGL fork, queue helpers, configuration) resides under `components/`. Assets such as certificates (`main/certs/`) and UI images (`main/images/`) should be kept small and source-controlled. Generated output goes under `build/` or `cmake-build-debug/`; clean these before committing. Host-side simulations and doctest suites live in `tests/host/`, while Unity-based on-target tests live in `test/`.

## Build, Test, and Development Commands
Run `idf.py set-target esp32s3` once per checkout. Build the default firmware with `idf.py build`; use `idf.py flash` followed by `idf.py monitor` to deploy and observe logs. For PSRAM-specific builds, use `./2m_build.sh` or `./8m_build.sh` to swap the appropriate `sdkconfig.defaults`, reconfigure, and rebuild cleanly. The `monitor.sh` script wraps the common serial port parameters. Host logic tests: `cmake -S tests/host -B tests/host/build && cmake --build tests/host/build && ctest --test-dir tests/host/build`. Unity firmware tests: `idf.py -T test build flash monitor`.

## Coding Style & Naming Conventions
Follow ESP-IDF defaults: 4-space indentation, braces on their own line for functions, and `snake_case` for FreeRTOS tasks and helpers (e.g., `start_time_service`). Use `PascalCase` for classes/structs when writing C++. Group related `#include`s and keep log tags (`TAG`, `ESP_LOGx`) short. Avoid heap allocations inside tight loops; prefer static buffers or the slab utilities already present in `commons.*`.

## Testing Guidelines
Keep Unity tests (`test/test_*.cpp`) focused on hardware-facing components; name cases `test_<topic>()` so they aggregate cleanly in CI output. Before flashing, ensure queues and drivers are initialized just like in `run_all_tests()`. Expand the doctest suites in `tests/host/src/` for pure logic, and gate new behaviour behind passing `ctest`. Aim to cover queue handling, MQTT parsing, and watchdog logic whenever you touch them.

## Commit & Pull Request Guidelines
Commits should stay small, use present-tense summaries (`update mqtt parameters`), and mention affected subsystems. Reference GitHub issues in the body when relevant. Pull requests need: a concise summary, screenshots or serial logs when touching UI/network flows, a checklist of commands executed (`idf.py build`, host tests), and any configuration changes (e.g., PSRAM profile) called out explicitly.

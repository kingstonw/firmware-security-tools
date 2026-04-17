Modify LVGL UI behavior:

<INSERT REQUIREMENT>

Constraints:
- Do not create/delete screens repeatedly
- Use container-based switching
- Reuse UI components (header icons, status views)
- UI must be state-driven

DO NOT:
- call lv_scr_load() repeatedly unless required
- create objects in loops

Verification:
- Provide expected UI state transitions
- Provide log points for UI changes
- Provide test steps to trigger each state
- Ensure no memory growth over time

Output:
1. Modified UI structure
2. Key LVGL changes
3. Expected screen transitions
4. Test steps
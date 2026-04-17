# Screen Category Migration Plan

## Goal
Consolidate legacy screen IDs into category-driven LVGL screens, then control each category with sub-states instead of creating one LVGL screen per legacy state.

## Is 10 screens in create_screens() too much?
Short answer: no, 10 is reasonable on ESP32-S3 with PSRAM.

Guidance for this codebase:
- Create 10 root category screens in create_screens().
- Do not preload heavy image assets for all 10 at boot.
- Keep shared widgets (title, status, progress, buttons, icon slot) and only update content per sub-state.
- Use lazy asset binding for icons/raw images when a category becomes active.
- Keep critical overlays separate (fatal error/alert popup layer) so navigation remains simple.

## Recommended Category Screens (10)
1. ScreenBootSystem
2. ScreenHomeOperation
3. ScreenProvisioning
4. ScreenConnectivity
5. ScreenUpdateOta
6. ScreenMaintenanceService
7. ScreenDiagnostics
8. ScreenAlertRecovery
9. ScreenInterDrawerSync
10. ScreenUtilityInfo

## Legacy Screen Mapping (33 active screens)
Note: Legacy Screen 23 is commented out in current build and excluded from the active 33.

| Legacy ID | Legacy Name | New Category Screen | Suggested Sub-State Key |
|---|---|---|---|
| 0 | Sleep | ScreenBootSystem | sleep_idle |
| 1 | QR Code / Device Unprovisioned | ScreenProvisioning | qr_unprovisioned |
| 2 | Downloading Firmware | ScreenUpdateOta | esp_download_in_progress |
| 3 | Firmware Download Complete | ScreenUpdateOta | esp_download_complete |
| 4 | Ready | ScreenHomeOperation | ready |
| 5 | WiFi Connect | ScreenConnectivity | wifi_connecting |
| 6 | Check Updates | ScreenUpdateOta | check_updates |
| 7 | Running (cycle timer) | ScreenHomeOperation | running |
| 8 | Waiting for BLE | ScreenProvisioning | ble_waiting |
| 9 | Provisioning In Progress | ScreenProvisioning | provisioning_in_progress |
| 10 | Asset Downloading | ScreenUpdateOta | assets_downloading |
| 11 | Motor Running (Stop button) | ScreenMaintenanceService | motor_running |
| 12 | Boot / Logo | ScreenBootSystem | boot_logo_version |
| 13 | General Working (no buttons) | ScreenUtilityInfo | working_message |
| 14 | Welcome | ScreenProvisioning | welcome_continue |
| 15 | Generic Error | ScreenAlertRecovery | generic_error |
| 16 | Done (generic complete) | ScreenUtilityInfo | done_message |
| 17 | Loading Settings | ScreenBootSystem | loading_settings |
| 18 | Pump Running | ScreenMaintenanceService | pump_running |
| 19 | Firmware Update Prompt | ScreenUpdateOta | update_prompt |
| 20 | No WiFi / Reprovision Prompt | ScreenConnectivity | wifi_reprovision_prompt |
| 21 | Factory Reset Confirmation | ScreenMaintenanceService | factory_reset_confirm |
| 22 | BLE / Provisioning Failed | ScreenAlertRecovery | provisioning_failed |
| 24 | Drawer Open (no icon) | ScreenHomeOperation | drawer_open |
| 25 | Cooling (cycle timer) | ScreenHomeOperation | cooling |
| 26 | Self-Test Running | ScreenDiagnostics | selftest_running |
| 27 | Drawer Open (with WARNING icon) | ScreenAlertRecovery | drawer_open_warning |
| 28 | Self-Test OK | ScreenDiagnostics | selftest_ok |
| 29 | Self-Test Errors | ScreenDiagnostics | selftest_error |
| 30 | STM32 Sensor Error (2033-2059) | ScreenAlertRecovery | stm_sensor_error |
| 31 | Updating STM32 Firmware | ScreenUpdateOta | stm_update_in_progress |
| 32 | Bucket Jam | ScreenAlertRecovery | bucket_jam |
| 33 | Drawer 2 Waiting for Drawer 1 | ScreenInterDrawerSync | wait_for_drawer1 |

## What to do with Legacy Screen 23?
- Keep as deprecated: not migrated in phase 1.
- If needed later, map to ScreenUpdateOta sub-state auto_update_prompt.

## Development Sequence Recommendation
Yes, starting from Screen 12 is a good choice.

Suggested order:
1. ScreenBootSystem first
- Implement sub-states: boot_logo_version (ID 12), loading_settings (ID 17), sleep_idle (ID 0)
- Reason: always shown at startup, low risk, validates font/version/device-id rendering.

2. ScreenHomeOperation second
- Implement ready/running/cooling/drawer-open (IDs 4, 7, 25, 24)
- Reason: highest runtime frequency.

3. ScreenProvisioning third
- Implement QR/welcome/wait/progress (IDs 1, 14, 8, 9)
- Reason: critical for first-time setup and BLE flow.

4. ScreenConnectivity fourth
- Implement wifi_connecting/reprovision_prompt (IDs 5, 20)

5. ScreenUpdateOta fifth
- Implement update check/prompt/download/progress (IDs 6, 19, 2, 3, 10, 31)

6. ScreenAlertRecovery sixth
- Implement error surfaces (IDs 15, 22, 27, 30, 32)

7. ScreenDiagnostics seventh
- Implement self-test states (IDs 26, 28, 29)

8. ScreenMaintenanceService eighth
- Implement motor/pump/factory reset (IDs 11, 18, 21)

9. ScreenInterDrawerSync ninth
- Implement drawer coordination (ID 33)

10. ScreenUtilityInfo last
- Implement generic working/done text screens (IDs 13, 16)

## Implementation Notes for create_screens()
- Create all 10 category root lv_obj screens there.
- For each category, create one setup function and one update function:
  - setup_screen_xxx()
  - render_screen_xxx(sub_state, data)
- Replace direct load_screen(legacy_id, ...) with:
  - ui_show(category, sub_state, payload)
- Keep a temporary compatibility mapper during migration:
  - map_legacy_to_category(legacy_id) -> (category, sub_state)

## Suggested Enum Naming
- ui_category_t: UI_CAT_BOOT_SYSTEM, UI_CAT_HOME_OPERATION, ...
- ui_substate_t: UI_SUB_BOOT_LOGO_VERSION, UI_SUB_RUNNING, UI_SUB_BUCKET_JAM, ...

This approach keeps RAM/flash usage controlled and makes behavior easier to test than maintaining 33+ separate layout trees.

# Top-Right High-Temperature Icon Logic (Show/Hide)

## Scope
This document explains **only** the top-right header hot icon behavior (sprite id `temp`, icon `ICON_HOT`) in this project.

It is intended for porting the same logic to another ESP-IDF project.

---

## 1) Where this icon is controlled

## Primary control point
- File: `SCREEN.cpp`
- Function: `SCREEN::SPRITE_updateHeader(bool wifi, bool aws, bool ble, bool drawer, bool hot)`

Top-right hot icon section:
```cpp
if (hot != prev_hot) {
    int idx = SPRITE_find("temp");
    if (hot) {
        Asset tempAsset = { "temp", tft.width() - 45, t, 37, 33, 255, config::COLORS::ORANGEBRIGHT, HEADER, "ICON_HOT", true, true, 2, NONE, 0, "", 0 };
        if (idx < 0) SPRITE_create(tempAsset);
        else { spriteAssets[idx] = tempAsset; spriteAssets[idx].dirty = true; }
    } else {
        if (idx >= 0) SPRITE_delete("temp");
    }
    prev_hot = hot;
}
```

### Position / style used by current code
- ID: `"temp"`
- Icon resource: `"ICON_HOT"`
- Type: `HEADER`
- Position: `x = tft.width() - 45`, `y = 10` (where `t=10`)
- Size: `37 x 33`
- Tint: `config::COLORS::ORANGEBRIGHT`

---

## 2) Who passes `hot=true/false`

In `main.ino::loop()`:
```cpp
mydisplay.SPRITE_updateHeader(
    gSYSTEM_WIFI,
    gSYSTEM_AWS,
    myble.pServer != nullptr,
    myhardware.isDrawerOpen(),
    myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)
);
```

So the hot icon is driven by:
```cpp
myhardware.isAnyBucketTempAbove56(gSYSTEM_drawer)
```

---

## 3) Temperature condition that triggers the icon

File: `HARDWARE.cpp`
Function: `HARDWARE::isAnyBucketTempAbove56(int drawer)`

```cpp
if (drawer == 1) {
  return (temp_ntc_bucket1 > 580 || temp_rtd_heater1 > 580);
} else if (drawer == 2) {
  return (temp_ntc_bucket2 > 580 || temp_rtd_heater2 > 580);
}
return false;
```

## Actual threshold in running code
- Uses `> 580` in tenths °C units
- Equivalent to **> 58.0C**

> Note: comments mention 56.0C/560, but implementation is 580.
> For behavior-compatible port, follow code (`>580`).

---

## 4) Show conditions (exact)

Top-right hot icon appears when all are true:
1. `SCREEN::SPRITE_updateHeader(...)` is called
2. `isAnyBucketTempAbove56(gSYSTEM_drawer)` returns `true`
3. Cached state transition occurs: `hot != prev_hot` (i.e., false -> true)

After creation, icon stays visible until explicit delete on a true->false transition.

---

## 5) Hide conditions (exact)

Top-right hot icon is removed when:
1. `SCREEN::SPRITE_updateHeader(...)` is called
2. `isAnyBucketTempAbove56(gSYSTEM_drawer)` returns `false`
3. Cached edge transition occurs: `hot != prev_hot` (i.e., true -> false)
4. `SPRITE_delete("temp")` executes

If temperature remains false and was already false, no action is performed (edge-triggered update).

---

## 6) Update frequency and lifecycle behavior

- `SPRITE_updateHeader(...)` is called once per main loop iteration (normal path).
- `SPRITE_renderDirty()` is called right after, so show/hide is rendered immediately in next frame.

Important exception:
- In `main.ino::loop()`, when `gDeviceStatus == FIRMWARETRANSFERTOSTM`, function returns early before header update.
- In that mode, hot icon will not refresh until normal loop resumes.

---

## 7) Drawer coupling (which drawer’s temperature is used)

Hot condition is evaluated against `gSYSTEM_drawer`.

`gSYSTEM_drawer` may be updated dynamically in `checkDrawerUIPageIds()`:
```cpp
if (myhardware.device_id >= 1 && myhardware.device_id <= 2 && gSYSTEM_drawer != myhardware.device_id) {
    gSYSTEM_drawer = myhardware.device_id;
    spiff.setSystemDetailByField(SPIFF_Manager::DRAWER, String(gSYSTEM_drawer));
}
```

So icon source temperature can switch between drawer1/drawer2 depending on active `device_id` updates.

---

## 8) Persistence across screen changes

Hot icon is a `HEADER` sprite and is not cleared by normal screen transitions.

`SCREEN::SPRITE_clearAll()` behavior:
- Deletes non-header assets
- Keeps header assets alive

Therefore, hot icon visibility is controlled by header logic transitions, not by individual screen templates.

---

## 9) Avoid confusion: center warning icon is different logic

There are separate **center** warning icon flows (`alert_icon`, `/assets/WARNING.raw`) for states like drawer-open/pause/hot alerts.

Those are **not** the top-right header hot icon.

For top-right behavior, only follow:
- `SPRITE_updateHeader(... hot ...)`
- `isAnyBucketTempAbove56(...)`
- sprite id `temp` / `ICON_HOT`

---

## 10) ESP-IDF port contract (recommended)

Implement these rules:

1. Keep a cached bool `prev_hot` (initial `false`).
2. Each UI tick:
   - `hot_now = overtemp(active_drawer)`
3. If `hot_now != prev_hot`:
   - if `hot_now == true`: create/show top-right hot icon
   - else: remove/hide top-right hot icon
   - set `prev_hot = hot_now`
4. Use active-drawer threshold:
   - drawer1: `bucket1 > 580 || heater1 > 580`
   - drawer2: `bucket2 > 580 || heater2 > 580`

---

## 11) Reference pseudocode

```c
void header_update(bool wifi, bool aws, bool ble, bool drawer_open, bool hot_now) {
    // ... wifi/aws/ble/drawer icons ...

    if (hot_now != prev_hot) {
        if (hot_now) {
            ui_create_or_update_icon("temp", ICON_HOT, x_right_top, y_top);
        } else {
            ui_delete_icon("temp");
        }
        prev_hot = hot_now;
    }
}

bool overtemp_for_active_drawer(int active_drawer) {
    if (active_drawer == 1) return (temp_ntc_bucket1 > 580 || temp_rtd_heater1 > 580);
    if (active_drawer == 2) return (temp_ntc_bucket2 > 580 || temp_rtd_heater2 > 580);
    return false;
}
```

---

## 12) Quick file index

- Header icon control: `SCREEN.cpp` (`SPRITE_updateHeader`)
- Header API + cache variable: `SCREEN.h` (`prev_hot`)
- Temp predicate: `HARDWARE.cpp` (`isAnyBucketTempAbove56`)
- Header update callsite: `main.ino` (`loop`, `SPRITE_updateHeader(...)`)
- Drawer switching that affects temp source: `main.ino` (`checkDrawerUIPageIds`)


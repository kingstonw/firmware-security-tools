# AI Coding Guidelines – ESP32 Firmware (LVGL + OTA + BLE)

## 1. Purpose

This document defines strict rules for AI-assisted code generation for the ESP32 firmware.

**Scope:**
- ESP32 firmware ONLY
- Includes:
  - LVGL UI
  - BLE provisioning
  - WiFi handling
  - OTA logic
  - STM32 communication (UART)

**EXCLUDES:**
- Backend (Go, Rust)
- NATS / MQTT server design
- PostgreSQL
- Web frontend

---

## 2. Core Principles (MUST FOLLOW)

### 2.1 DO NOT GUESS
- Only use logic found in:
  - existing source code
  - provided documents
- If not found:
  - say "Not found in current implementation"
  - or "Unclear from current code"

**DO NOT:**
- invent UI behavior
- assume OTA logic
- assume BLE flow

---

### 2.2 Keep Changes Minimal
- Modify only necessary code
- Do NOT redesign architecture
- Preserve existing behavior unless explicitly fixing a bug

---

### 2.3 Embedded Constraints First
- Always consider:
  - memory usage
  - CPU usage
  - task safety
  - real-time constraints

---

## 3. UI Rules (LVGL)

### 3.1 Screen Management
- Prefer:
  - pre-created screens
  - container-based views

**DO NOT:**
- repeatedly create/delete full screens
- cause memory fragmentation

---

### 3.2 View Switching
- Use:
  - container show/hide
  - state-driven UI updates

**DO NOT:**
- call `lv_scr_load()` repeatedly unless required

---

### 3.3 Shared Components
- Header icons (WiFi, BLE, warning, drawer status):
  - MUST be reusable components
  - Should NOT be recreated per screen

---

### 3.4 UI Update Flow
- UI must be driven by:
  - device state changes
  - event callbacks

**DO NOT:**
- poll UI unnecessarily
- update UI from multiple uncontrolled contexts

---

## 4. Memory & Performance Rules

### 4.1 Allocation
- Prefer:
  - static allocation
  - pre-allocated buffers

**Avoid:**
- frequent malloc/free
- large dynamic allocations

---

### 4.2 Data Structures
- Use:
  - ring buffers
  - fixed-size arrays

---

### 4.3 LVGL Objects
- Create once, reuse
- Avoid deleting objects during normal operation

---

## 5. Tasking & Concurrency (FreeRTOS)

- UI updates must run in:
  - UI task / LVGL task context

**DO NOT:**
- update LVGL directly from ISR
- update LVGL from random tasks

**Use:**
- message queue
- event queue
- task notification

---

## 6. OTA Rules

### 6.1 OTA Decision
- MUST be based on:
  - `version.json`
  - actual implemented logic

**DO NOT:**
- assume version comparison logic
- assume targeting rules

---

### 6.2 OTA Flow
- Follow existing implementation exactly
- If logic is missing:
  - mark as "Not implemented"

---

### 6.3 Safety
- Ensure:
  - no memory overflow
  - no blocking UI during OTA
  - proper state transitions

---

## 7. BLE Provisioning Rules

### 7.1 Source of Truth
- MUST follow:
  - `docs/ble/BLE_PROVISIONING.md`

---

### 7.2 Flow Constraints
**DO NOT:**
- change message sequence
- reorder steps without validation

---

### 7.3 Multi-device (Top/Bottom Drawer)
- Pay attention to:
  - bridge messages
  - provisioning handoff

**DO NOT:**
- assume missing messages
- guess transition logic

---

## 8. STM32 Communication

- Communication via UART

**Rules:**
- Do NOT change protocol format
- Do NOT invent new commands
- Only use defined message structure

---

## 9. Logging Rules

- Use consistent logging tags
- Important events MUST log:
  - state changes
  - OTA progress
  - BLE provisioning steps

---

## 10. Code Generation Rules

### 10.1 When modifying code
- Show:
  - file name
  - function name
  - exact changes

---

### 10.2 When analyzing code
Must include:
1. What is confirmed
2. What is not confirmed
3. Where logic is located

---

### 10.3 When unclear
Explicitly state:
- "Not found in current code"
- "Needs clarification"

---

## 11. Examples

**GOOD**
- "OTA trigger condition not found in current implementation"
- "BLE step after file transfer is unclear"

**BAD**
- "It probably compares versions"
- "It should send a ready message"

---

## 12. Verification Requirements (MANDATORY)

AI-generated code MUST be verifiable.

### 12.1 Build Verification
- Code MUST compile:
  - ESP-IDF: `idf.py build`
  - Arduino: project must compile
- DO NOT use undefined APIs or placeholders

---

### 12.2 Logging Requirements
- MUST add logs for:
  - state transitions
  - OTA decision points
  - BLE provisioning steps
  - error paths

Logs must be:
- clear
- consistent
- sufficient for debugging

---

### 12.3 Testability (VERY IMPORTANT)
AI MUST:
- provide a way to trigger logic without full system dependency

Examples:
- mock state transitions
- simulate BLE completion
- simulate OTA response
- inject test events

DO NOT:
- require full cloud/app flow for testing

---

### 12.4 Expected Runtime Behavior
AI MUST provide:
- expected log sequence
- expected state transitions

---

### 12.5 Manual Test Steps
AI MUST provide:
1. how to trigger the feature
2. what to observe
3. expected result
4. failure cases

---

### 12.6 Regression Awareness
AI MUST state:
- what existing features may be affected
- what needs re-testing

---

### 12.7 When Not Possible
If verification cannot be implemented:
- explicitly state:
  - "Cannot be verified without external dependency"

 
## 13. Summary

AI must:
	•	Not guess missing logic
	•	Keep firmware stable
	•	Respect embedded constraints
	•	Use LVGL efficiently
	•	Follow BLE and OTA design strictly

⸻

This document overrides default AI assumptions.

---

## 14. Prompt Usage Policy

Prompt templates MUST NOT be embedded in this document.

All task-specific prompts (OTA, UI, BLE, bugfix, analysis, etc.) MUST be maintained in:

```
docs/ai_prompts/
```

Each module MUST have its own prompt file.

---

### 14.1 Usage Rules

- ALWAYS use:
  - Base prompt + module-specific prompt
- NEVER write free-form prompts without constraints
- ALWAYS include verification requirements

---

### 14.2 Prompt Structure

Each prompt MUST include:

- Requirements
- Constraints
- Verification section

---

### 14.3 Separation of Concerns

This file defines:
- system rules
- architecture constraints
- verification requirements

Prompt templates MUST be:
- modular
- reusable
- stored separately

---

## 15. Summary for AI Behavior

AI MUST:

- Follow AI_GUIDELINES.md strictly
- Use external prompt templates from docs/ai_prompts/
- Never guess missing logic
- Always produce verifiable outputs
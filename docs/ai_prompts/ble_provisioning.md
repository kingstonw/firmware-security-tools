Fix BLE provisioning logic:

<INSERT ISSUE>

Constraints:
- MUST follow docs/ble/BLE_PROVISIONING.md
- Do not reorder steps
- Do not invent messages
- Use existing message definitions only

Focus:
- top drawer → bottom drawer transition
- bridge messages between devices

Verification:
- Provide expected message sequence
- Provide logs for each step:
  - file received
  - provisioning complete
  - bridge message sent
  - bottom drawer ready
- Explain failure points

Output:
1. Identified issue
2. Code changes
3. Expected message/log sequence
4. Test steps (top + bottom drawer)
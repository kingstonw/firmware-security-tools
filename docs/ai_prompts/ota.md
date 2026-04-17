Implement or fix OTA logic:

<INSERT REQUIREMENT>

Constraints:
- MUST be based on version.json
- Do not assume version comparison logic
- Do not guess device targeting rules
- Use only existing OTA flow

DO NOT:
- invent new OTA states
- assume cloud behavior

Verification:
- Show decision path logs (why OTA / why skip)
- Provide test steps with mock version.json
- Ensure OTA does not block UI
- Ensure memory safety

Output:
1. OTA decision logic
2. Code changes
3. Expected logs (decision path)
4. Test steps (with mock input)
Make the solution verifiable:

Requirements:
- Code must compile (idf.py build)
- Add logs for all key transitions
- Provide expected runtime behavior
- Provide manual test steps
- Add debug/test hooks if possible

Testability:
- Must allow triggering logic without full system
- Use mock inputs where possible

DO NOT:
- require cloud/app dependency to test

Output:
1. Logs added
2. Expected log sequence
3. Test steps
4. Debug hooks (if added)
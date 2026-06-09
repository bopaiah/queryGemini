import sys
sys.path.insert(0, '/mnt/c/GitRepos/queryGemini')

from gemini_utils import parse_response_text
import json

# Test 1: Raw JSON string (no markdown fences) - the case from edit_image
result = parse_response_text('{\n  "image_understanding": "The original image shows a bald male head.",\n  "generated_image": "Here is the face: "\n}')
print("Test 1 - Raw JSON string:")
print("  content_type:", result['content_type'])
assert result['content_type'] == 'json', "FAIL: expected json"
print("  PASS")

# Test 2: Raw JSON with a literal newline INSIDE a string value (the actual failing case)
# The model returned: "generated_image": "...: \n"  <- literal \n inside the JSON string value
raw = '{\n  "image_understanding": "The original image shows a bald male head.",\n  "generated_image": "Here\'s the face: \n"\n}'
result2 = parse_response_text(raw)
print("\nTest 2 - Raw JSON with literal newline in value:")
print("  content_type:", result2['content_type'])
print("  raw repr:", repr(raw))
try:
    parsed = json.loads(raw)
    print("  json.loads strict succeeds:", parsed)
except json.JSONDecodeError as e:
    print("  json.loads strict FAILS:", e)
try:
    parsed = json.loads(raw, strict=False)
    print("  json.loads strict=False succeeds:", parsed)
except json.JSONDecodeError as e:
    print("  json.loads strict=False FAILS:", e)
assert result2['content_type'] == 'json', "FAIL: expected json"
print("  PASS")

# Test 3: JSON in markdown fence
result3 = parse_response_text('```json\n{"key": "value"}\n```')
print("\nTest 3 - JSON in markdown fence:")
print("  content_type:", result3['content_type'])
assert result3['content_type'] == 'json', "FAIL: expected json"
print("  PASS")

# Test 4: Plain text
result4 = parse_response_text("This is just plain text.")
print("\nTest 4 - Plain text:")
print("  content_type:", result4['content_type'])
assert result4['content_type'] == 'text', "FAIL: expected text"
print("  PASS")

# Test 5: Empty string
result5 = parse_response_text("")
print("\nTest 5 - Empty string:")
print("  content_type:", result5['content_type'])
assert result5['content_type'] == 'text', "FAIL: expected text"
print("  PASS")

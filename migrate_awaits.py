import os
import re

# We will regex match sql_ helper function calls and prepend await if missing
# Note: we also have to make the parent functions async if they aren't already.
# But looking at Pyrogram handlers, they are usually defined as async def.

target_dir = "/Users/moxi/Library/Mobile Documents/com~apple~CloudDocs/MyFile/Code/EmbyBoss/Sakura_embyboss/bot"

# List of all our async sql functions
sql_funcs = [
    "migrate_add_game_stats_fields",
    "sql_add_emby",
    "sql_delete_emby_by_tg",
    "sql_clear_emby_iv",
    "sql_delete_emby",
    "sql_update_embys",
    "sql_get_emby",
    "get_all_emby",
    "sql_update_emby",
    "sql_count_emby",
    "sql_add_emby2",
    "sql_get_emby2",
    "get_all_emby2",
    "sql_update_emby2",
    "sql_delete_emby2",
    "sql_delete_emby2_by_name",
    "sql_add_code",
    "sql_update_code",
    "sql_get_code",
    "sql_count_code",
    "sql_count_p_code",
    "sql_count_c_code",
    "sql_delete_unused_by_days",
    "sql_delete_all_unused",
    "sql_add_request_record",
    "sql_get_request_record_by_tg",
    "sql_get_request_record_by_download_id",
    "sql_get_request_record_by_transfer_state",
    "sql_update_request_status",
    "sql_add_favorites",
    "sql_clear_favorites",
    "sql_get_favorites",
    "sql_update_favorites"
]

# Create a regex pattern to match these function calls not preceded by await
# Negative lookbehind: (?<!await\s)
# Match word boundary: \b
# Match any func name: (func1|func2|...)
# Match opening paren: \(
pattern = r'(?<!await\s)(?<!def\s)\b(' + '|'.join(sql_funcs) + r')\s*\('

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Skip if file defines one of these functions (sql helper files themselves)
    if "def sql_get_emby" in content and filepath.endswith("sql_emby.py"):
        return

    # check if any function call exists
    if not re.search(pattern, content):
        return

    # Replacement: await \1(
    new_content = re.sub(pattern, r'await \1(', content)

    # Some replacements might be inside a synchronous function if the codebase is mixed.
    # Pyrogram app handlers should be async. But we'll just prepend await.
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"Updated: {filepath}")

for root, dirs, files in os.walk(target_dir):
    # skip .git or other ignored dirs if any
    if "sql_helper" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            process_file(filepath)

print("Done replacing.")

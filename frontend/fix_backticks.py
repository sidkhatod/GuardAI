import os, re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    
    # We have things like: fetch(${API_BASE}/agents) missing backticks: fetch(/agents)
    # Let's use a regex to find \$\{API_BASE\}[^,)\s]*
    # and wrap them in backticks IF they are not already.
    # Actually, let's just do it simple:
    content = re.sub(r'(?<!)\$\{API_BASE\}(.*?)(?=[,)\s])', r"${API_BASE}\1", content)
    content = re.sub(r'(?<!)\$\{WS_BASE\}(.*?)(?=[,)\s])', r"${WS_BASE}\1", content)

    if original != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed {filepath}")

for root, _, files in os.walk('src'):
    for f in files:
        if f.endswith('.js') or f.endswith('.jsx'):
            process_file(os.path.join(root, f))


import os, re

def process_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    content = re.sub(r"(?<!`)\$\{API_BASE\}([^\s,\)\}]*)", r"`${API_BASE}\1`", content)
    content = re.sub(r"(?<!`)\$\{WS_BASE\}([^\s,\)\}]*)", r"`${WS_BASE}\1`", content)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print("Fixed " + filepath)

for root, _, files in os.walk("src"):
    for f in files:
        if f.endswith(".js") or f.endswith(".jsx"):
            process_file(os.path.join(root, f))


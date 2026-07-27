import os, glob, re

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    
    parts = filepath.replace('\\', '/').split('/')
    try:
        src_idx = parts.index('src')
        rel_depth = len(parts) - src_idx - 2
    except ValueError:
        rel_depth = 0
    
    import_path = '../' * rel_depth + 'config' if rel_depth > 0 else './config'

    needs_api = 'http://localhost:8000' in content
    needs_ws = 'ws://localhost:8000' in content

    if not needs_api and not needs_ws:
        return

    # Replace 'http://localhost:8000/...' with \\/...\
    content = re.sub(r"'http://localhost:8000(.*?)'", r"${API_BASE}\1", content)
    content = re.sub(r"http://localhost:8000(.*?)", r"${API_BASE}\1", content)
    
    # Replace 'ws://localhost:8000/...' with \\/...\
    content = re.sub(r"'ws://localhost:8000(.*?)'", r"${WS_BASE}\1", content)
    content = re.sub(r"ws://localhost:8000(.*?)", r"${WS_BASE}\1", content)

    if original != content:
        imports = []
        if needs_api: imports.append('API_BASE')
        if needs_ws: imports.append('WS_BASE')
        
        import_stmt = f"import {{ {', '.join(imports)} }} from '{import_path}';\n"
        
        lines = content.split('\n')
        last_import = -1
        for i, line in enumerate(lines):
            if line.startswith('import '):
                last_import = i
        
        lines.insert(last_import + 1, import_stmt)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"Updated {filepath}")

for root, _, files in os.walk('src'):
    for f in files:
        if f.endswith('.js') or f.endswith('.jsx'):
            process_file(os.path.join(root, f))

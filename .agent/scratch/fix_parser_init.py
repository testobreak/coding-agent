import re

# In tree-sitter 0.22+, Parser is constructed with the language:
#   _PARSER = Parser(_LANG)
# NOT:
#   _PARSER = Parser()
#   _PARSER.set_language(_LANG)

files = [
    r'd:\HRMS\.agent\parsers\java_parser.py',
    r'd:\HRMS\.agent\parsers\python_parser.py',
    r'd:\HRMS\.agent\parsers\js_parser.py',
    r'd:\HRMS\.agent\parsers\ts_parser.py',
]

for path in files:
    text = open(path, encoding='utf-8').read()
    original = text

    # Replace:  _PARSER = Parser()\n_PARSER.set_language(_LANG)
    # with:     _PARSER = Parser(_LANG)
    # (handles any var name: _PARSER, _TS_PARSER, _TSX_PARSER etc.)
    text = re.sub(
        r'(_\w*PARSER\w*)\s*=\s*Parser\(\)\s*\n\s*\1\.set_language\((_\w+)\)',
        r'\1 = Parser(\2)',
        text
    )
    if text != original:
        open(path, 'w', encoding='utf-8').write(text)
        print(f'  Fixed: {path.split(chr(92))[-1]}')
    else:
        print(f'  No match in: {path.split(chr(92))[-1]} (checking pattern manually)')
        # Show the relevant lines
        for line in text.splitlines():
            if 'Parser' in line or 'set_language' in line:
                print(f'    >> {line.strip()}')

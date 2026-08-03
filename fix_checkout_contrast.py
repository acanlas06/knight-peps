from pathlib import Path
for p in Path('.').glob('*.html'):
    s=p.read_text(encoding='utf-8', errors='ignore')
    add='.summary .mini-item{color:var(--ink,#11100b)}.summary .mini-item span{color:var(--muted,#716958)}'
    if add not in s:
        s=s.replace('</style>', add+'</style>', 1)
    p.write_text(s, encoding='utf-8')
print('fixed checkout summary item contrast')

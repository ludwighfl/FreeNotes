import os

total = 0
print(f"{'Lines':>5} | File")
print("-" * 50)

files = []
for dp, dn, fn in os.walk('.'):
    if '.venv' in dp or '__pycache__' in dp or '.git' in dp:
        continue
    for f in fn:
        if f.endswith('.py'):
            files.append(os.path.join(dp, f))

files.sort()

for f in files:
    try:
        with open(f, encoding='utf-8', errors='ignore') as file:
            lines = sum(1 for _ in file)
            total += lines
            print(f"{lines:5d} | {f.replace(chr(92), '/')}")
    except Exception as e:
        pass

print("-" * 50)
print(f"{total:5d} | TOTAL")

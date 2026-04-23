import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 注释掉除了 DEBUG 之外的所有 print
lines = content.split('\n')
new_lines = []
for line in lines:
    if line.strip().startswith('print(') and '[DEBUG]' not in line:
        new_lines.append('# ' + line)
    else:
        new_lines.append(line)

content = '\n'.join(new_lines)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')

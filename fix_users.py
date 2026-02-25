import sys
filepath = r'c:\Users\USER\Desktop\PETSTELLON STUDIOS\PYTHON FILES\2026 PROJECTS\HERIGLOBAL-POS\blueprints\users.py'
with open(filepath, 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace('\\"\\"\\"', '"""')
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(c)
print('Fixed successfully')

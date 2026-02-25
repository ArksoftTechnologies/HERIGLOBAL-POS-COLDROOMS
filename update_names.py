import os
import re

templates_dir = r'c:\Users\USER\Desktop\PETSTELLON STUDIOS\PYTHON FILES\2026 PROJECTS\HERIGLOBAL-POS\templates'

for root, dirs, files in os.walk(templates_dir):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Replace 'Heriglobal POS' with '{{ app_name }}'
            new_content = re.sub(r'Heriglobal\s+POS', '{{ app_name }}', content, flags=re.IGNORECASE)
            
            # Replace 'HERIGLOBAL LTD' mostly in receipts
            new_content = re.sub(r'HERIGLOBAL\s+LTD', '{{ app_name | upper }}', new_content, flags=re.IGNORECASE)
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print('Updated HTML:', filepath)

# Also update pdf_generator.py explicitly
pdf_gen_path = r'c:\Users\USER\Desktop\PETSTELLON STUDIOS\PYTHON FILES\2026 PROJECTS\HERIGLOBAL-POS\utils\pdf_generator.py'
with open(pdf_gen_path, 'r', encoding='utf-8') as f:
    pdf_content = f.read()

new_pdf_content = pdf_content.replace("'company_name': 'HERIGLOBAL LTD'", "'company_name': current_app.config.get('APP_NAME', 'Heriglobal POS').upper()")

if 'current_app' not in new_pdf_content:
    new_pdf_content = new_pdf_content.replace('from flask import render_template', 'from flask import render_template, current_app')

if new_pdf_content != pdf_content:
    with open(pdf_gen_path, 'w', encoding='utf-8') as f:
        f.write(new_pdf_content)
    print('Updated python:', pdf_gen_path)

auth_path = r'c:\Users\USER\Desktop\PETSTELLON STUDIOS\PYTHON FILES\2026 PROJECTS\HERIGLOBAL-POS\blueprints\auth.py'
with open(auth_path, 'r', encoding='utf-8') as f:
    auth_content = f.read()

new_auth_content = auth_content.replace("f'Heriglobal POS <{mail_username}>'", "f'{current_app.config.get(\"APP_NAME\", \"Heriglobal POS\")} <{mail_username}>'")
new_auth_content = new_auth_content.replace("'Subject'] = 'Password Reset Request – Heriglobal POS'", "'Subject'] = f'Password Reset Request – {current_app.config.get(\"APP_NAME\", \"Heriglobal POS\")}'")

if new_auth_content != auth_content:
    with open(auth_path, 'w', encoding='utf-8') as f:
        f.write(new_auth_content)
    print('Updated python:', auth_path)

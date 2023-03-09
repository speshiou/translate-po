import sys
import subprocess
import glob
import os
import argparse
import re
from google.cloud import translate

python_dir = os.path.join(os.path.dirname(sys.executable), "../")
python_i18n_tools_dir = "share/doc/python3.8/examples/Tools/i18n"

pygettext = os.path.join(python_dir, python_i18n_tools_dir, "pygettext.py")
msgfmt = os.path.join(python_dir, python_i18n_tools_dir, "msgfmt.py")

# TODO: Set the variables before running the sample.
source_language_code = 'en'
support_langs = ['zh_TW', 'zh_CN']

def build_msgstr_map(content):
    msgstr_map = {}
    lines = content.split('\n')
    msgid = ''
    msgstr = ''
    for line in lines:
        matches_msgid = re.match('^msgid "(.*)"$', line)
        if matches_msgid:
            msgid = matches_msgid.group(1)
            continue
        matches_msgstr = re.match('^msgstr "(.*)"$', line)
        if matches_msgstr:
            msgstr = matches_msgstr.group(1)
            msgstr_map[msgid] = msgstr
    return msgstr_map

def update_po_from_pot(content, pot):
    msgstr_map = build_msgstr_map(content)
    lines = pot.split('\n')
    msgid = ''
    existing = 0
    not_found = 0
    for i in range(len(lines)):
        line = lines[i]
        matches_msgid = re.match('^msgid "(.*)"$', line)
        if matches_msgid:
            msgid = matches_msgid.group(1)
            continue
        matches_msgstr = re.match('^(msgstr ").*("$)', line)
        if matches_msgstr:
            if msgid in msgstr_map:
                existing += 1
                lines[i] = f'{matches_msgstr.group(1)}{msgstr_map.get(msgid, "")}{matches_msgstr.group(2)}'
            else:
                not_found += 1
    print(f'Added {not_found} new strings, removed {len(msgstr_map) - existing} strings')
    return '\n'.join(lines)

def parse_msg_ids(content):
    contents = []
    lines = content.split("\n")
    msgid = ""
    msgstr = ""
    for line in lines:
        matches_msgid = re.match(r'^msgid "(.*)"$', line)
        if matches_msgid:
            msgid = matches_msgid.group(1)
            continue
        matches_msgstr = re.match(r'^msgstr "(.*)"$', line)
        if matches_msgstr:
            msgstr = matches_msgstr.group(1)
            if msgid and not msgstr:
                contents.append(msgid)
    return contents

def sanitize_text(text):
    return text.replace("％s", "%s")

def replace_msgstr(content, translations):
    lines = content.split("\n")
    msgid = ""
    msgstr = ""
    translations_index = 0
    for i in range(len(lines)):
        line = lines[i]
        matches_msgid = re.match(r'^msgid "(.*)"$', line)
        if matches_msgid:
            msgid = matches_msgid.group(1)
            continue
        matches_msgstr = re.match(r'^msgstr "(.*)"$', line)
        if matches_msgstr:
            msgstr = matches_msgstr.group(1)
            if msgid and not msgstr:
                lines[i] = re.sub(r'^(msgstr ").*(")$', lambda m: m.group(1) + sanitize_text(translations[translations_index].translated_text) + m.group(2), line)
                translations_index += 1
    return "\n".join(lines)

def get_locale_dir(locale):
    return os.path.join(args.locale_dir, locale, "LC_MESSAGES")

def translate_po():
    pot_filename = os.path.join(args.locale_dir, f'{args.textdomain}.pot')
    
    if not os.path.isfile(pot_filename):
        return f"{pot_filename} not exists"
    
    with open(pot_filename, 'r', encoding='utf-8') as pot_file:
        pot = pot_file.read()

    client = translate.TranslationServiceClient()
    parent = f"projects/{args.gc_project_id}/locations/{args.gc_location}"
    for lang in support_langs:
        print(f'Translating {lang} ...')
        lang_dir = get_locale_dir(lang)
        # mkdir if not exists
        os.makedirs(lang_dir, exist_ok=True)
        po_file_path = os.path.join(lang_dir, f'{args.textdomain}.po')
        content = ""
        if os.path.isfile(po_file_path):
            with open(po_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        content = update_po_from_pot(content, pot)
        contents = parse_msg_ids(content)
        print(f'{len(contents)} new strings for {lang}')
        if not contents:
            continue
        
        request = {
            'parent': parent,
            'contents': contents,
            'mime_type': 'text/plain', # mime types: text/plain, text/html
            'source_language_code': source_language_code,
            'target_language_code': lang.replace("_", "-"),
        }

        response = client.translate_text(request)
        translated = replace_msgstr(content, response.translations)
        with open(po_file_path, 'w', encoding='utf-8') as f:
            f.write(translated)

def generate_pot():
    if not os.path.isfile(pygettext):
        print(f"{pygettext} not exists. Please create the pot file manually")
        return
    py_files = glob.glob(os.path.join(args.src, '*.py'))
    pot_filename = os.path.join(args.locale_dir, f'{args.textdomain}.pot')
    subprocess.run([pygettext, '-d', args.textdomain, '-o', pot_filename] + py_files, capture_output=True, text=True)

def generate_mo():
    if not os.path.isfile(msgfmt):
        print(f"{msgfmt} not exists. Please compile po files into mo format manually")
        return
    po_files = glob.glob(os.path.join(args.locale_dir, '**', '*.po'), recursive=True)
    subprocess.run([msgfmt] + po_files, capture_output=True, text=True)

def main():
    generate_pot()
    translate_po()
    generate_mo()

parser = argparse.ArgumentParser(description="Translate po files")
parser.add_argument("locale_dir", help="Path to locale directory")
parser.add_argument("-d", "--textdomain", type=str, required=True, help="Text domain")
parser.add_argument("--src", type=str, required=True, help="Python codebase dir")
parser.add_argument("--gc_project_id", type=str, required=True, help="Google Cloud Project ID")
parser.add_argument("--gc_location", type=str, required=True, help="Google Cloud Project Location")
args = parser.parse_args()

if __name__ == '__main__':
    main()


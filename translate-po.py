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
source_language_code = 'en_US'
support_langs = [
    source_language_code, 
    'zh_TW', 
    'zh_CN', 
    'es_ES', 
    'fr_FR',
    'ko_KR',
    'ja_JP',
    'id_ID',
    'pt_BR',
    'ru_RU',
]

def update_po_from_pot(po_msg_map, pot):
    lines = pot.split('\n')

    msgid = ""
    state = None

    data = []
    for line in lines:
        m = re.match(r'^"(.*)"$', line)
        if m:
            if state == "msgid":
                msgid += m[1]
            data.append(line)
        elif line.startswith("msgid"):
            m = re.match('^msgid "(.*)"$', line)
            if m:
                state = "msgid"
                msgid = m[1]
            data.append(line)
        elif line.startswith("msgstr"):
            if msgid and msgid in po_msg_map:
                data.append(f"msgstr \"{po_msg_map[msgid]}\"")
            else:
                data.append(line)
            state = "msgstr"
        else:
            data.append(line)

    return '\n'.join(data)

def _pot_filename():
    return os.path.join(args.src, args.locale_dir, f'{args.textdomain}.pot')

def parse_po(content):
    data = {}

    lines = content.split("\n")
    msgid = ""
    msgstr = ""
    state = None
    for line in lines:
        m = re.match(r'^"(.*)"$', line)
        if m:
            if state == "msgid":
                msgid += m[1]
            elif state == "msgstr":
                msgstr += m[1]
        elif line.startswith("msgid"):
            m = re.match(r'^msgid "(.*)"$', line)
            if m:
                msgid = m[1]
                state = "msgid"
        elif line.startswith("msgstr"):
            m = re.match(r'^msgstr "(.*)"$', line)
            if m:
                msgstr = m[1]
                state = "msgstr"
        elif state == "msgstr":
            state = None
            data[msgid] = msgstr
        
    return data

def sanitize_text(text):
    return text.replace("％s", "%s")

def get_locale_dir(locale: str):
    if "_" not in locale:
        locale = f"{locale}_{locale.upper()}"
    return os.path.join(args.src, args.locale_dir, locale, "LC_MESSAGES")

def translate_po():
    pot_filename = _pot_filename()
    
    if not os.path.isfile(pot_filename):
        return f"{pot_filename} not exists"
    
    with open(pot_filename, 'r', encoding='utf-8') as pot_file:
        pot = pot_file.read()

    pot_msg_map = parse_po(pot)
    pot_msg_keys = set(pot_msg_map.keys())

    client = translate.TranslationServiceClient()
    parent = f"projects/{args.gc_project_id}/locations/{args.gc_location}"
    for lang in support_langs:
        print(f'Translating {lang} ...')
        lang_dir = get_locale_dir(lang)
        # mkdir if not exists
        os.makedirs(lang_dir, exist_ok=True)
        po_file_path = os.path.join(lang_dir, f'{args.textdomain}.po')
        content = pot
        if os.path.isfile(po_file_path):
            with open(po_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                po_msg_map = parse_po(content)
        else:
            po_msg_map = {}
        po_msg_keys = set(po_msg_map.keys())
        print(f'Added {len(pot_msg_keys - po_msg_keys)}, removed {len(po_msg_keys - pot_msg_keys)}')

        content = update_po_from_pot(po_msg_map, pot)
        
        po_msg_map = parse_po(content)
        po_msg_keys = set(po_msg_map.keys())
        
        to_translate = []
        for key, value in po_msg_map.items():
            if not value:
                to_translate.append(key)
        
        if lang != source_language_code and len(to_translate) > 0:
            request = {
                'parent': parent,
                'contents': to_translate,
                'mime_type': 'text/plain', # mime types: text/plain, text/html
                'source_language_code': source_language_code,
                'target_language_code': lang.replace("_", "-"),
            }

            response = client.translate_text(request)

            i = 0
            for key, value in po_msg_map.items():
                if not value:
                    row = response.translations[i]
                    po_msg_map[key] = sanitize_text(row.translated_text)
                    i += 1

        content = update_po_from_pot(po_msg_map, pot)

        with open(po_file_path, 'w', encoding='utf-8') as f:
            f.write(content)

def generate_pot():
    pot_filename = _pot_filename()
    if not args.pot:
        print(f"--src not provided, skip generating pot file from codebase")
        return
    if not os.path.isfile(pygettext):
        print(f"{pygettext} not exists. Please create the pot file manually")
        return
    print("Parsing codebase to generate the pot file ...")
    py_files = glob.glob(os.path.join(args.src, '*.py'))
    result = subprocess.run([pygettext, '-d', args.textdomain, '-o', pot_filename] + py_files, capture_output=True, text=True)
    print(result.stderr)

def generate_mo():
    po_files = glob.glob(os.path.join(args.src, args.locale_dir, '**', '*.po'), recursive=True)

    if os.path.isfile(msgfmt):
        subprocess.run([msgfmt] + po_files, capture_output=True, text=True)
    else:
        for po_file in po_files:
            mo_file = os.path.splitext(po_file)[0] + ".mo"
            subprocess.run([ "msgfmt", "-o", mo_file, po_file ], capture_output=True, text=True)  

def main():
    generate_pot()
    translate_po()
    generate_mo()

parser = argparse.ArgumentParser(description="Translate po files")
parser.add_argument("src", type=str, help="Python codebase dir")
parser.add_argument("--locale_dir", type=str, help="Path to locale directory")
parser.add_argument("-d", "--textdomain", type=str, required=True, help="Text domain")
parser.add_argument("--gc_project_id", type=str, required=True, help="Google Cloud Project ID")
parser.add_argument("--gc_location", type=str, required=True, help="Google Cloud Project Location")
parser.add_argument("--pot")
args = parser.parse_args()

if __name__ == '__main__':
    main()


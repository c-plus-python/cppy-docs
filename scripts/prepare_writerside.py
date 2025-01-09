# This script moves the compiled PDFs to the resources folder
# of the Writerside project. It then generates the download page.

# A file containing checksums is first obtained from the server.
# Compiled PDFs are checked against the checksums to determine
# whether they were modified.

# The script also generates a new checksum file for uploading.

import os
import subprocess
import tomllib
import hashlib
import requests
from datetime import datetime, timezone
from PIL import Image
import numpy as np

GITHUB_PAGES_URL = 'https://c-plus-python.github.io/cppy-docs/'
CHECKSUM_URL =  GITHUB_PAGES_URL + 'resources/std_checksum.toml'
AUTOMATION_CACHE_DIR = 'scripts/__automation_cache__'

def output(msg: str):
    print('\033[94m', end='') # blue
    print('(SCRIPT) >>> ')
    print('\033[0m', end='') # reset
    print(msg)

# Run the script in the root directory of the project.

# Delete the arbitrary-pdf.pdf file
os.remove('pages_src/resources/arbitrary-pdf.pdf')
output('Deleted arbitrary-pdf.pdf')

# Obtain the checksum file from the server via HTTP as plaintext
# MD5 checksums are abandoned and not used for comparison since they are not reliable.
# But they are kept for compatibility.
output(f'Obtaining checksum file from {CHECKSUM_URL}')
response = requests.get(CHECKSUM_URL)
if response.status_code != 200:
    checksum_data = None
    output('Checksum file does not exist. Will handle checksums.')
else:
    output(f'Obtained information:\n{response.text}')
    checksum_data = tomllib.loads(response.text)

# ==== Format of the checksum file ====
# [ID]
# checksum = "hash"
# last_modified = utc_datetime

new_checksum_data = {}
os.makedirs(AUTOMATION_CACHE_DIR, exist_ok=False)
output(f'Created dir: {AUTOMATION_CACHE_DIR}')
is_modified = False

# Handle the compiled PDFs
with open('scripts/compile_list.toml', 'rb') as f:
    entries = tomllib.load(f)['entries']
for entry in entries:
    pdf_path = entry['file'][:-4] + '.pdf' # Remove the .tex extension and add .pdf
    output(f'Handling {pdf_path}')

    # generate checksum
    hash_md5 = hashlib.md5()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    entry['checksum'] = hash_md5.hexdigest()

    pdf_filename = pdf_path.split('/')[-1]
    os.makedirs(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}', exist_ok=False)
    output(f'Created dir: {AUTOMATION_CACHE_DIR}/{entry["id"]}')
    os.makedirs(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old', exist_ok=False)
    output(f'Created dir: {AUTOMATION_CACHE_DIR}/{entry["id"]}/old')

    # download old PDF
    output(f'Downloading old PDF from {GITHUB_PAGES_URL}resources/{pdf_filename}')
    response = requests.get(GITHUB_PAGES_URL + 'resources/' + pdf_filename)
    if response.status_code != 200:
        # old PDF does not exist
        is_modified = True
        output('Old PDF does not exist. Will use the new PDF.')
    else:
        with open(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old_{pdf_filename}', 'wb') as f:
            f.write(response.content)
        # convert to PNG
        output('Converting old PDF to PNG...')
        command = [
            'gs',
            '-dBatch',
            '-dNOPAUSE',
            '-sDEVICE=png16m',
            f'-sOutputFile={AUTOMATION_CACHE_DIR}/{entry["id"]}/old/page_%03d.png',
            f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old_{pdf_filename}'
        ]
        subprocess.run(command)

    # convert PDF to PNG for comparison
    if not is_modified:
        os.makedirs(AUTOMATION_CACHE_DIR + f'/{entry["id"]}/new', exist_ok=False)
        output(f'Created dir: {AUTOMATION_CACHE_DIR}/{entry["id"]}/new')
        command[-2] = f'-sOutputFile={AUTOMATION_CACHE_DIR}/{entry["id"]}/new/page_%03d.png'
        command[-1] = pdf_path
        output('Converting new PDF to PNG...')
        subprocess.run(command)

        # compare PNGs
        output('Comparing PNGs...')
        old_pngs = sorted(os.listdir(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old'))
        new_pngs = sorted(os.listdir(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/new'))

        if len(old_pngs) != len(new_pngs):
            is_modified = True # mismatched number of pages
        
    if not is_modified:
        for old_png, new_png in zip(old_pngs, new_pngs):
            old_image = Image.open(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old/{old_png}')
            new_image = Image.open(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/new/{new_png}')

            if old_image.size != new_image.size:
                is_modified = True
                break
            
            arr_old = np.array(old_image).astype(np.float64)
            arr_new = np.array(new_image).astype(np.float64)
            mse = np.mean((arr_old - arr_new) ** 2)
            rmse = np.sqrt(mse)
            output(f'PNG {old_png} \t RMSE = {rmse}')
            if rmse > 1:
                is_modified = True
                break

    # move the file
    if is_modified: # use the new PDF
        output('The document is modified. Moving new PDF to resources folder.')
        os.rename(pdf_path, 'pages_src/resources/' + pdf_filename)
    else: # use the old PDF
        output('The document is not modified. Moving old PDF to resources folder.')
        os.rename(f'{AUTOMATION_CACHE_DIR}/{entry["id"]}/old_{pdf_filename}', 'pages_src/resources/' + pdf_filename)
    
    # generate table row
    output('Generating table row...')
    modified_time = datetime.now(timezone.utc) if is_modified else checksum_data[entry['id']]['last_modified']
    file_checksum = entry['checksum'] if is_modified else checksum_data[entry['id']]['checksum']
    match entry['status']:
        case 'draft':
            status_text = '📝 Draft'
        case 'released':
            status_text = '📃 Released'
        case 'deprecated':
            status_text = '🚫 Deprecated'
        case _:
            status_text = '❓ Unknown'
    entry['row'] =  '<tr>' \
                   f'<td>{entry["id"]}</td>' \
                   f'<td>{status_text}</td>' \
                   f'<td>{modified_time.strftime("%Y-%m-%d %H:%M:%S")} (UTC)</td>' \
                   f'<td><resource src=\"{pdf_filename}\">Download PDF</resource><br/>' \
                   f'MD5 Checksum: <code>{file_checksum}</code></td>' \
                    '</tr>'
    output(f'Generated:\n{entry["row"]}')
    new_checksum_data[entry['id']] = {'checksum': file_checksum, 'last_modified': modified_time}

# create the new checksum file
with open('pages_src/resources/std_checksum.toml', 'w') as f:
    for id in new_checksum_data:
        checksum, last_modified = new_checksum_data[id].values()
        f.write(f'[{id}]\nchecksum = "{checksum}"\nlast_modified = {last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")}\n\n')
output('Generated the new checksum file.')

# replace @REPLACE_START to @REPLACE_END with the new table rows
with open('pages_src/topics/standards.topic', 'r') as f:
    lines = f.readlines()
for line_no, line in enumerate(lines):
    if '@REPLACE_START' in line:
        start_line = line_no
    if '@REPLACE_END' in line:
        end_line = line_no
        break
lines[start_line:end_line] = [entry['row'] for entry in entries]
output('Writing into standards.topic...')
with open('pages_src/topics/standards.topic', 'w') as f:
    f.writelines(lines)

output('Script finished.')
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

# Run the script in the root directory of the project.

# Delete the arbitrary-pdf.pdf file
os.remove('pages_src/resources/arbitrary-pdf.pdf')

# Obtain the checksum file from the server via HTTP as plaintext
# MD5 checksums are abandoned and not used for comparison since they are not reliable.
# But they are kept for compatibility.
response = requests.get(CHECKSUM_URL)
if response.status_code != 200:
    checksum_data = None
else:
    checksum_data = tomllib.loads(response.text)

# ==== Format of the checksum file ====
# [ID]
# checksum = "hash"
# last_modified = utc_datetime

new_checksum_data = {}
os.makedirs(AUTOMATION_CACHE_DIR, exist_ok=False)
is_modified = False

# Handle the compiled PDFs
with open('scripts/compile_list.toml', 'rb') as f:
    entries = tomllib.load(f)['entries']
for entry in entries:
    pdf_path = entry['file'][:-4] + '.pdf' # Remove the .tex extension and add .pdf

    # generate checksum
    hash_md5 = hashlib.md5()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    entry['checksum'] = hash_md5.hexdigest()
    pdf_filename = pdf_path.split('/')[-1]

    # download old PDF
    response = requests.get(GITHUB_PAGES_URL + 'resources/' + pdf_filename)
    if response.status_code != 200:
        # old PDF does not exist
        is_modified = True
    else:
        with open(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/old_{pdf_filename}', 'wb') as f:
            f.write(response.content)
        # convert to PNG
        command = [
            'gs',
            '-dBatch',
            '-dNOPAUSE',
            '-sDEVICE=png16m',
            f'-sOutputFile={AUTOMATION_CACHE_DIR}/{pdf_filename}/old/page_%03d.png',
            f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/old_{pdf_filename}'
        ]
        subprocess.run(command)

    # convert PDF to PNG for comparison
    if not is_modified:
        os.makedirs(AUTOMATION_CACHE_DIR + f'{pdf_filename}/new', exist_ok=False)
        command[-2] = f'-sOutputFile={AUTOMATION_CACHE_DIR}/{pdf_filename}/new/page_%03d.png'
        command[-1] = pdf_path
        subprocess.run(command)

        # compare PNGs
        old_pngs = sorted(os.listdir(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/old'))
        new_pngs = sorted(os.listdir(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/new'))

        if len(old_pngs) != len(new_pngs):
            is_modified = True
        else:
            for old_png, new_png in zip(old_pngs, new_pngs):
                old_image = Image.open(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/old/{old_png}')
                new_image = Image.open(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/new/{new_png}')

                if old_image.size != new_image.size:
                    is_modified = True
                    break
                
                arr_old = np.array(old_image).astype(np.float64)
                arr_new = np.array(new_image).astype(np.float64)
                mse = np.mean((arr_old - arr_new) ** 2)
                rmse = np.sqrt(mse)
                if rmse > 1:
                    is_modified = True
                    break

    # move the file
    if is_modified: # use the new PDF
        os.rename(pdf_path, 'pages_src/resources/' + pdf_filename)
    else: # use the old PDF
        os.rename(f'{AUTOMATION_CACHE_DIR}/{pdf_filename}/old_{pdf_filename}', 'pages_src/resources/' + pdf_filename)
    
    # generate table row
    modified_time = datetime.now(timezone.utc) if is_modified else checksum_data[entry['id']]['last_modified']
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
                   f'MD5 Checksum: <code>{entry["checksum"]}</code></td>' \
                    '</tr>'
    new_checksum_data[entry['id']] = {'checksum': entry['checksum'], 'last_modified': modified_time}

# create the new checksum file
with open('pages_src/resources/std_checksum.toml', 'w') as f:
    for id in new_checksum_data:
        checksum, last_modified = new_checksum_data[id].values()
        f.write(f'[{id}]\nchecksum = "{checksum}"\nlast_modified = {last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")}\n\n')

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
with open('pages_src/topics/standards.topic', 'w') as f:
    f.writelines(lines)
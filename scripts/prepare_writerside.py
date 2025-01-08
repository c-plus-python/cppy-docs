# This script moves the compiled PDFs to the resources folder
# of the Writerside project. It then generates the download page.

# A file containing checksums is first obtained from the server.
# Compiled PDFs are checked against the checksums to determine
# whether they were modified.

# The script also generates a new checksum file for uploading.

import os
import tomllib
import hashlib
import requests
from datetime import datetime, timezone

GITHUB_PAGES_URL = 'https://c-plus-python.github.io/cppy-docs/'
CHECKSUM_URL =  GITHUB_PAGES_URL + 'resources/std_checksum.toml'

# Run the script in the root directory of the project.

# Delete the arbitrary-pdf.pdf file
os.remove('pages_src/resources/arbitrary-pdf.pdf')

# Obtain the checksum file from the server via HTTP as plaintext
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

    # move the file
    pdf_filename = pdf_path.split('/')[-1]
    os.rename(pdf_path, 'pages_src/resources/' + pdf_filename)
    
    # generate table row
    is_modified = entry['checksum'] != checksum_data[entry['id']]['checksum'] if checksum_data else True
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
                   f'<td>{modified_time.strftime('%Y-%m-%d %H:%M:%S')} (UTC)</td>' \
                   f'<td><resource src=\"{pdf_filename}\">Download PDF</resource></td>' \
                    '</tr>'
    new_checksum_data[entry['id']] = {'checksum': entry['checksum'], 'last_modified': modified_time}

# create the new checksum file
with open('pages_src/resources/std_checksum.toml', 'w') as f:
    for id in new_checksum_data:
        checksum, last_modified = new_checksum_data[id].values()
        f.write(f'[{id}]\nchecksum = "{checksum}"\nlast_modified = "{last_modified.strftime("%Y-%m-%dT%H:%M:%SZ")}"\n\n')

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
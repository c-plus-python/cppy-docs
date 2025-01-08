import tomllib

# Get the list of all the TeX files that are required to compile
# and print them line by line.

# Run the script from the root directory of the project.
# i.e. The working directory should be the root directory of the project.

with open('scripts/compile_list.toml', 'rb') as f:
    entries = tomllib.load(f)['entries']

for entry in entries:
    print(entry['file'])
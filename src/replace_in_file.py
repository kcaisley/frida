import sys

def replace_in_file(file_path, old_str, new_str):
    try:
        with open(file_path, 'r') as file:
            file_content = file.read()
        
        updated_content = file_content.replace(old_str, new_str)
        
        with open(file_path, 'w') as file:
            file.write(updated_content)
        
        print(f'Replaced all occurrences of "{old_str}" with "{new_str}" in "{file_path}"')
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python replace_string.py <file_path> <old_str> <new_str>", file=sys.stderr)
        sys.exit(1)
    
    file_path = sys.argv[1]
    old_str = sys.argv[2]
    new_str = sys.argv[3]
    
    replace_in_file(file_path, old_str, new_str)
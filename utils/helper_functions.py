import os

def find_tsconfig_dir(start_dir: str) -> str:
    """
    Walk upward from `start_dir` until we find a 'tsconfig.json'.
    Return the directory containing it, or None if not found.
    """
    current_dir = os.path.abspath(start_dir)
    while True:
        tsconfig_path = os.path.join(current_dir, "tsconfig.json")
        if os.path.isfile(tsconfig_path):
            return current_dir  # found it
        
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            break
        current_dir = parent_dir

    return None
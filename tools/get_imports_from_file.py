import os
from typing import Any, Dict, List
import json
from tree_sitter import Language, Parser, Tree, Node
from py2neo import Graph, Node as NeoNode, Relationship
from typing import Generator

import tree_sitter_javascript as tspython
PY_LANGUAGE = Language(tspython.language())
parser_ts = Parser(PY_LANGUAGE)

def read_file_bytes(file_path: str) -> bytes:
    """Read file contents as bytes."""
    with open(file_path, 'rb') as f:
        return f.read()


def parse_file(file_path: str) -> Tree:
    """Parse a single file and return its Tree-sitter parse tree."""
    file_bytes = read_file_bytes(file_path)
    return parser_ts.parse(file_bytes)


def traverse_tree(tree: Tree) -> Generator[Node, None, None]:
    """
    Depth-first traversal over the tree-sitter parse tree.
    Yields each node exactly once.
    """
    cursor = tree.walk()
    visited_children = False

    while True:
        if not visited_children:
            yield cursor.node
            if not cursor.goto_first_child():
                visited_children = True
        elif cursor.goto_next_sibling():
            visited_children = False
        elif not cursor.goto_parent():
            break


def extract_imports(file_path: str) -> Dict[str, Any]:
    """
    Return a structure like:
      {
        "file": "/absolute/path/to/file.tsx",
        "imports": [
          "/absolute/path/to/otherFile.tsx",   # local resolved
          "sonner",                            # external package
          ...
        ]
      }
    """

    tree = parse_file(file_path)
    file_bytes = read_file_bytes(file_path)
    base_dir = os.path.dirname(file_path)

    imports_info = {
        "file": file_path,
        "imports": []
    }

    for node in traverse_tree(tree):
        if node.type == "import_statement":
            import_path_node = None
            for child in node.children:
                if child.type == "string":
                    import_path_node = child
                    break

            if import_path_node:
                raw_text = file_bytes[
                           import_path_node.start_byte: import_path_node.end_byte
                           ].decode("utf-8")
                import_path = raw_text.strip('"').strip("'")

                # Handle local or aliased imports the same as before:
                if import_path.startswith('next'):
                    continue

                if (
                        import_path.startswith('.')
                        or import_path.startswith('/')
                        or import_path.startswith('@')
                ):
                    full_path = resolve_import_path(base_dir, import_path)
                    if full_path:
                        imports_info["imports"].append(full_path)
                    else:
                        # If we can't resolve it, store the raw import string if desired
                        imports_info["imports"].append(import_path)
                else:
                    # It's likely an external/package import (e.g. "react", "sonner", "next/router").
                    # Instead of skipping, store it in the "imports" list as a string.
                    imports_info["imports"].append(import_path)

    return imports_info


def create_graph_in_neo4j(files_info, neo4j_uri="bolt://localhost:7687", user="neo4j", password="test"):
    """
    Takes a list of file info dicts and inserts them into Neo4j.
    Each file is a node, each function is a node, and each call is a relationship.
    """
    # Connect to Neo4j
    graph = Graph(neo4j_uri, auth=(user, password))

    # Optionally, clear the database (be careful!)
    graph.delete_all()

    # Create constraints or indexes if desired
    graph.run("CREATE CONSTRAINT IF NOT EXISTS ON (f:File) ASSERT f.path IS UNIQUE;")
    graph.run("CREATE CONSTRAINT IF NOT EXISTS ON (fn:Function) ASSERT fn.id IS UNIQUE;")

    tx = graph.begin()

    for file_info in files_info:
        file_path = file_info["file"]
        # Create a File node
        file_node = NeoNode("File", path=file_path)
        tx.merge(file_node, "File", "path")  # merge based on the unique property `path`

        for func in file_info["functions"]:
            func_name = func["name"]
            func_id = f"{file_path}:{func_name}"  # unique ID for function node
            # Create a Function node
            func_node = NeoNode(
                "Function",
                id=func_id,
                name=func_name,
                file=file_path,
                start_byte=func["start_byte"],
                end_byte=func["end_byte"]
            )
            tx.merge(func_node, "Function", "id")

            # Create relationship: (File)-[:CONTAINS]->(Function)
            rel_contains = Relationship(file_node, "CONTAINS", func_node)
            tx.merge(rel_contains)

            # Insert calls as edges: (Function)-[:CALLS]->(Function)
            for called in func["calls"]:
                # The naive approach is to store the called function name as a node
                # (in real usage, you'd want to map function name to a file or a known function if possible)
                called_id = f"UNKNOWN_FILE:{called}"  # if you can't resolve the file for the call
                called_node = NeoNode("Function", id=called_id, name=called)
                tx.merge(called_node, "Function", "id")

                rel_call = Relationship(func_node, "CALLS", called_node)
                tx.merge(rel_call)

    graph.commit(tx)


def create_file_dependency_graph(files_import_info: List[Dict[str, Any]],
                                 neo4j_uri="bolt://localhost:7687",
                                 user="neo4j",
                                 password="test"):
    """
    Insert a graph of file dependencies:
    (File)-[:IMPORTS]->(File)
    """
    graph = Graph(neo4j_uri, auth=(user, password))
    graph.delete_all()  # BE CAREFUL: This wipes the database

    # Updated constraint creation syntax
    graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:File) REQUIRE f.path IS UNIQUE;")

    tx = graph.begin()
    for fi in files_import_info:
        source_file = fi["file"]
        imports = fi["imports"]

        # Create a node for the source file
        file_node = NeoNode("File", path=source_file)
        tx.merge(file_node, "File", "path")

        for imported_file in imports:
            if not imported_file:
                continue
            target_node = NeoNode("File", path=imported_file)
            tx.merge(target_node, "File", "path")

            rel = Relationship(file_node, "IMPORTS", target_node)
            tx.merge(rel)
    graph.commit(tx)

    print("Finished creating file dependency graph in Neo4j!")



def get_tsconfig_base_url(start_dir: str) -> str:
    """
    Walk upwards from `start_dir` to find a 'tsconfig.json'.
    Return the 'baseUrl' string if present, otherwise None.
    """
    current_dir = os.path.abspath(start_dir)
    while True:
        tsconfig_path = os.path.join(current_dir, "tsconfig.json")
        if os.path.isfile(tsconfig_path):
            try:
                with open(tsconfig_path, "r", encoding="utf-8") as f:
                    tsconfig = json.load(f)
                compiler_opts = tsconfig.get("compilerOptions", {})
                return compiler_opts.get("baseUrl")  # might be "src" or similar
            except (json.JSONDecodeError, OSError):
                pass

        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent

    return None


def resolve_import_path(base_dir: str, import_path: str) -> str:
    # 1) If it starts with `@/`, attempt to map it to `baseUrl`
    if import_path.startswith("@/"):
        base_url = get_tsconfig_base_url(base_dir)  # could cache this if desired
        if base_url:
            # We remove "@/" and then prepend baseUrl + "/"
            # So "@/components/ui" -> "src/components/ui" (if baseUrl == "src")
            import_path = os.path.join(base_url, import_path[2:])
            # Note: import_path[2:] removes "@/"
            # This doesn't handle multiple aliases—just '@/'.
        else:
            # If no baseUrl is found, we can still attempt to treat "@/xxx" as relative
            # or just skip. For now let's try removing '@' and treat it as normal:
            import_path = import_path[2:]  # might not resolve, but we try

    potential_extensions = [".ts", ".tsx", ".js", ".jsx"]

    # 2) Try appending known extensions directly
    for ext in potential_extensions:
        candidate = os.path.join(base_dir, import_path + ext)
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    # 3) Try index file if referencing a folder
    for ext in potential_extensions:
        candidate_index = os.path.join(base_dir, import_path, "index" + ext)
        if os.path.isfile(candidate_index):
            return os.path.abspath(candidate_index)

    # 4) If none found, return None
    return None


def find_tsconfig_json(start_dir: str) -> str:
    """
    Walk upward from `start_dir` until we find `tsconfig.json`.
    Return the absolute path to it, or None if not found.
    """
    current_dir = os.path.abspath(start_dir)
    while True:
        tsconfig_path = os.path.join(current_dir, "tsconfig.json")
        if os.path.isfile(tsconfig_path):
            return tsconfig_path

        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:
            # Reached root, no tsconfig found
            return None
        current_dir = parent_dir


def parse_tsconfig(tsconfig_path: str) -> dict:
    """
    Parse tsconfig.json and return a dict with relevant info:
      {
        "baseUrl": <string or None>,
        "paths": {
          "aliasPattern": [ "mappedPattern1", "mappedPattern2", ... ],
          ...
        },
        "tsconfigDir": "/path/to/tsconfig/folder"
      }
    """
    if not tsconfig_path or not os.path.isfile(tsconfig_path):
        return {"baseUrl": None, "paths": {}, "tsconfigDir": None}

    with open(tsconfig_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    compiler_opts = config.get("compilerOptions", {})
    base_url = compiler_opts.get("baseUrl")  # e.g. "src"
    paths = compiler_opts.get("paths", {})  # e.g. { "@/*": ["*"], "@lib/*": ["lib/*"], ... }

    return {
        "baseUrl": base_url,
        "paths": paths,
        "tsconfigDir": os.path.dirname(os.path.abspath(tsconfig_path))
    }

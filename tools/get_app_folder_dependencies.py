from py2neo import Graph

def get_app_folder_dependencies(uri, user, password):
    """
    Returns a dictionary like:
        {
            "/absolute/path/to/app/page.tsx": [
                "/absolute/path/to/dep1.tsx",
                "/absolute/path/to/dep2.tsx",
                ...
            ],
            ...
        }
    """
    graph = Graph(uri, auth=(user, password))

    query = """
    MATCH (f:File)
    WHERE f.path CONTAINS '/app/'
    OPTIONAL MATCH (f)-[:IMPORTS*1..]->(dep:File)
    WITH f, collect(DISTINCT dep.path) as dependencies
    RETURN f.path as file, dependencies
    """

    results = graph.run(query).data()

    # Convert the list of dicts to a Python dict
    # { "file.tsx": [dep1, dep2, ...], ... }
    dependency_map = {}
    for record in results:
        file_path = record["file"]
        deps = record["dependencies"] or []


        if file_path in deps:
            deps.remove(file_path)

        dependency_map[file_path] = deps
    
    return dependency_map
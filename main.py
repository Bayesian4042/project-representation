    
from tools.get_app_folder_dependencies import get_app_folder_dependencies
from tools.get_feature_summary import generate_feature_summary
from tools.get_imports_from_file import create_file_dependency_graph, extract_imports
import os

from dotenv import load_dotenv
load_dotenv()


uri ='neo4j+s://a2dcd7b9.databases.neo4j.io'
user = "neo4j"
password = os.environ.get("DATABASE_PWD")

dependencies = get_app_folder_dependencies(uri, user, password)

for app_file, dep_list in dependencies.items():
    print(f"File: {app_file}")
    print("  Transitive deps:")
    for d in dep_list:
        print(f"    - {d}")
    print()

code_dir = "full-stack-nextjs/app"
repo = "full-stack-nextjs"

ts_files = []
for root, dirs, files in os.walk(code_dir):
    for f in files:
        if f.endswith(".ts") or f.endswith(".tsx"):
            ts_files.append(os.path.join(root, f))

dependencies = []
for fpath in ts_files:
    info = extract_imports(fpath)
    dependencies.append(info)

create_file_dependency_graph(dependencies,
                            neo4j_uri=uri,
                            user="neo4j",
                            password=password)


with open("feature_summaries.txt", "w", encoding="utf-8") as outfile:
    for dependency_map in dependencies:
        for file, imports in dependency_map.items():
            main_file = dependency_map['file']
            deps = dependency_map['imports']
            all_files_for_feature = [main_file] + deps

            print(f"\nGenerating summary for {main_file}...")
            summary = generate_feature_summary(all_files_for_feature)

            # Write the summary to the file
            outfile.write(f"=== Feature Summary for {main_file} ===\n")
            outfile.write(summary)
            outfile.write("\n" + ("-" * 80) + "\n")

            print(f"Summary for {main_file} written to feature_summaries.txt.")
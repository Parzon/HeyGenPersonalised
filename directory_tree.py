import os

def save_directory_tree(root_dir, output_file):
    with open(output_file, "w", encoding="utf-8") as f:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            level = dirpath.replace(root_dir, "").count(os.sep)
            indent = " " * (level * 4)
            f.write(f"{indent}{os.path.basename(dirpath)}/\n")
            subindent = " " * ((level + 1) * 4)
            for filename in filenames:
                f.write(f"{subindent}{filename}\n")

if __name__ == "__main__":
    root_directory = os.getcwd()  # Change this if you want to specify another directory
    output_file = "directory_tree.txt"
    save_directory_tree(root_directory, output_file)
    print(f"Directory tree saved to {output_file}")

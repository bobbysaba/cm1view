"""MkDocs hook: build the site's home page from README.md, with its links rewritten
for the site (docs/x.md -> x.md, repo files -> GitHub)."""
import os
import re

from mkdocs.structure.files import File

REPO = "https://github.com/bobbysaba/cm1view/blob/master/"


def on_files(files, config):
    root = os.path.dirname(config.config_file_path)
    with open(os.path.join(root, "README.md")) as f:
        text = f.read()

    def link(m):
        target = m.group(1)
        if re.match(r"[a-z]+:|#", target):
            return m.group(0)
        if target.startswith("docs/"):
            return f"]({target[5:]})"
        return f"]({REPO}{target})"

    text = re.sub(r"\]\(([^)]+)\)", link, text)
    files.append(File.generated(config, "index.md", content=text))
    return files

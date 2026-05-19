import os
import json
import re
import subprocess
from pathlib import Path
import structlog

logger = structlog.get_logger()

def setup_directories():
    os.makedirs("data/corpus", exist_ok=True)

def clone_pandas_docs():
    """Clones the pandas repository to extract documentation."""
    tmp_dir = "/tmp/pandas_docs"
    if not os.path.exists(tmp_dir):
        logger.info("Cloning pandas repository for docs...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "https://github.com/pandas-dev/pandas.git", tmp_dir],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    return os.path.join(tmp_dir, "doc", "source")

def strip_html_or_rst(text: str) -> str:
    """Removes HTML and basic RST tags from text."""
    clean = re.compile('<.*?>')
    text = re.sub(clean, '', text)
    # Basic RST cleanup
    text = re.sub(r'.. \w+::.*', '', text)
    return text

def parse_rst_docs(docs_dir: str, output_file: str):
    """Parses rst files, splitting them by headers."""
    logger.info("Parsing pandas documentation...")
    chunks = []
    
    for root, _, files in os.walk(docs_dir):
        for file in files:
            if not file.endswith(".rst") and not file.endswith(".md"):
                continue
            
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Naive split by RST Header (e.g. ==== or ---- or ##)
            sections = re.split(r'\n(?:=|-|#|~){3,}\n', content)
            
            for i, section in enumerate(sections):
                if not section.strip():
                    continue
                
                title = file
                if i > 0:
                    title = section.split('\n')[0][:100] # Use first line as title proxy
                    
                cleaned_text = strip_html_or_rst(section).strip()
                cleaned_text = re.sub(r'\s+', ' ', cleaned_text) # normalize whitespace
                
                if len(cleaned_text) > 50: # only keep meaningful chunks
                    chunks.append({
                        "source": f"pandas_docs/{file}",
                        "title": title.strip(),
                        "text": cleaned_text
                    })
                    
    with open(output_file, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk) + "\n")
    logger.info("Saved docs chunks", count=len(chunks), file=output_file)

def parse_resolved_issues(raw_issues_file: str, train_files: list, output_file: str):
    """Extracts held-out issues to act as RAG knowledge."""
    logger.info("Processing resolved issues...")
    
    # 1. Gather all IDs used in training/testing to prevent leakage
    used_ids = set()
    for tf in train_files:
        if os.path.exists(tf):
            with open(tf, "r", encoding="utf-8") as f:
                for line in f:
                    data = json.loads(line)
                    used_ids.add(data["id"])
                    
    logger.info("Excluded used issue IDs", count=len(used_ids))
    
    # 2. Extract issues
    corpus_issues = []
    if os.path.exists(raw_issues_file):
        with open(raw_issues_file, "r", encoding="utf-8") as f:
            for line in f:
                issue = json.loads(line)
                if issue["id"] not in used_ids and issue.get("state") == "closed":
                    
                    title = issue.get("title", "")
                    body = issue.get("body", "") or ""
                    
                    # For issues, body + closing comment is ideal.
                    # Since we don't have the comments locally in raw_issues.jsonl and want to avoid rate-limits,
                    # we will use the body as the knowledge chunk (assuming maintainers often update the main body or it contains the solution code).
                    cleaned_body = strip_html_or_rst(body).strip()
                    cleaned_body = re.sub(r'\s+', ' ', cleaned_body)
                    
                    text_content = f"Title: {title}\nBody: {cleaned_body}"
                    
                    if len(text_content) > 100:
                        corpus_issues.append({
                            "source": f"issue_{issue['id']}",
                            "title": title,
                            "text": text_content
                        })
                        
                        # Just grab around 500 issues max to keep the DB small and fast for the prototype
                        if len(corpus_issues) >= 500:
                            break

    with open(output_file, "w", encoding="utf-8") as f:
        for issue in corpus_issues:
            f.write(json.dumps(issue) + "\n")
            
    logger.info("Saved resolved issues", count=len(corpus_issues), file=output_file)

if __name__ == "__main__":
    setup_directories()
    
    docs_dir = clone_pandas_docs()
    parse_rst_docs(docs_dir, "data/corpus/docs.jsonl")
    
    train_splits = ["data/train.jsonl", "data/val.jsonl", "data/test.jsonl"]
    parse_resolved_issues("data/raw_issues.jsonl", train_splits, "data/corpus/resolved_issues.jsonl")

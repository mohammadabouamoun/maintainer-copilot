import os
import json
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from openai import AsyncOpenAI

async def generate_golden_set():
    load_dotenv()
    db_url = "postgresql+asyncpg://user:password@localhost:5432/dbname"
    engine = create_async_engine(db_url)
    
    client = AsyncOpenAI(
        api_key=os.environ.get("LLM_API_KEY"),
        base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    )
    model = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
    
    print("Fetching candidate chunks from the vector database...")
    query = text("""
        SELECT id, content 
        FROM corpus_chunks 
        WHERE source_type = 'doc' AND length(content) > 300
        ORDER BY RANDOM() 
        LIMIT 45
    """)
    
    golden_set = []
    
    async with engine.connect() as conn:
        rows = await conn.execute(query)
        chunks = rows.fetchall()
        
    print(f"Generating 20 highly-specific synthetic questions using Groq ({model})...")
    successful_count = 0
    chunk_index = 0
    
    while successful_count < 20 and chunk_index < len(chunks):
        row = chunks[chunk_index]
        chunk_id = str(row.id)
        content = row.content
        chunk_index += 1
        
        prompt = f"""
        You are a pandas expert. Given the following documentation chunk, generate a realistic user question that can be answered by this text. Also generate the ideal concise answer.
        
        CRITICAL RULES FOR SPECIFICITY:
        1. The generated question MUST be highly specific, detailed, and completely unambiguous. 
        2. It MUST contain unique technical terms, function names, parameter names, version numbers, or specific scenarios mentioned in the chunk.
        3. The question must uniquely identify this chunk. Avoid generic questions like "what is new in version X" or "how do I use method Y". Instead, ask about the specific parameters or edge cases detailed in the text.
        4. Output MUST be in strict JSON format with exactly two keys: "question" and "ideal_answer".
        Do not output any markdown formatting like ```json, just raw JSON. Escape all double quotes inside strings properly.
        
        Chunk:
        {content[:1800]}
        """
        
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300
            )
            
            raw_json = response.choices[0].message.content.strip()
            if raw_json.startswith("```json"):
                raw_json = raw_json[7:-3].strip()
            elif raw_json.startswith("```"):
                raw_json = raw_json[3:-3].strip()
                
            data = json.loads(raw_json)
            
            # Basic validation
            if "question" in data and "ideal_answer" in data:
                golden_set.append({
                    "id": str(successful_count + 1),
                    "question": data["question"],
                    "ideal_answer": data["ideal_answer"],
                    "ground_truth_chunk_ids": [chunk_id]
                })
                successful_count += 1
                print(f"Generated specific Q&A pair {successful_count}/20: '{data['question'][:60]}...'")
        except Exception as e:
            pass
            
    print("Adding 5 hand-labeled edge cases...")
    manual_cases = [
        {
            "id": "21",
            "question": "How do I drop missing values but only if the whole row is NA?",
            "ideal_answer": "You can use the `dropna` method on your DataFrame and pass the argument `how='all'`. For example: `df.dropna(how='all')`.",
            "ground_truth_chunk_ids": []
        },
        {
            "id": "22",
            "question": "What is the difference between loc and iloc in pandas?",
            "ideal_answer": "`loc` is primarily label-based data selection, meaning you use row and column labels to access data. `iloc` is integer position-based, meaning you use the numerical index position (0 to n-1).",
            "ground_truth_chunk_ids": []
        },
        {
            "id": "23",
            "question": "How can I merge two DataFrames on an index instead of a column?",
            "ideal_answer": "You can use the `merge` function and pass `left_index=True` and `right_index=True` to merge on the indices of both DataFrames.",
            "ground_truth_chunk_ids": []
        },
        {
            "id": "24",
            "question": "Is it possible to read a CSV file but only load specific columns to save memory?",
            "ideal_answer": "Yes, you can use the `usecols` parameter in `pd.read_csv()` and pass a list of the column names or indices you want to load.",
            "ground_truth_chunk_ids": []
        },
        {
            "id": "25",
            "question": "How do I convert a string column containing dates into actual datetime objects?",
            "ideal_answer": "Use the `pd.to_datetime()` function and pass your string column to it. This will parse the strings and return a datetime Series.",
            "ground_truth_chunk_ids": []
        }
    ]
    
    golden_set.extend(manual_cases)
    
    os.makedirs("evals/golden_sets", exist_ok=True)
    out_path = "evals/golden_sets/rag_golden.json"
    with open(out_path, "w") as f:
        json.dump(golden_set, f, indent=2)
        
    print(f"\\nSuccessfully generated Golden Set with {len(golden_set)} items at {out_path}!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(generate_golden_set())

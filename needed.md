# ENGINEERING_STANDARDS.md# Engineering Standards for AI ProjectsPurpose: This file defines the engineering standards the AI system and developers should follow while building and reviewing AI services.These rules are mandatory and act as architectural constraints.---# 1. Async All The Way Down## RuleAll I/O operations must be asynchronous.## Applies To- API requests- Database calls- LLM requests- External services- File/network operations## Never```pythonrequests.get(...)time.sleep(...)openai.chat.completions.create(...)
Inside async routes.
Blocking calls stop the event loop.
Use
httpx.AsyncClient()await asyncio.sleep()AsyncOpenAI()await asyncio.gather(...)
Notes
CPU-heavy work is not async.
Examples:


large ML inference


parsing huge files


expensive computations


Move these to:
await asyncio.to_thread(...)

2. Dependency Injection
Rule
Routes declare dependencies.
Dependencies do not create resources directly.
Never
Global objects:
engine = ...llm = ...
Or:
@app.post(...)async def route():    token=request.headers.get(...)    session=...
Use
async def get_session():    yield sessiondef get_llm():    return app.state.llm@app.post(...)async def route(    session=Depends(get_session),    llm=Depends(get_llm))
Benefits


testability


dependency overrides


composability


cleaner architecture



3. Singletons Done Correctly
Rule
Heavy resources load once during app startup.
Examples:


ML models


embedding models


DB engines


HTTP clients


vector stores


LLM clients


Never
@app.post(...)async def route():    model=joblib.load(...)
Also Avoid
Import-time initialization:
model=joblib.load(...)
Use lifespan
@asynccontextmanagerasync def lifespan(app):    app.state.model=...    app.state.llm=...    yield    await cleanup()
Access through dependencies:
Depends(get_model)

4. Caching
Two cache patterns exist.
A. lru_cache
Use for:


deterministic functions


settings


pure expensive computations


Example:
@lru_cache(maxsize=1)def get_settings():    return Settings()
Do NOT use:


mutable arguments


time-sensitive data


expiring values



B. TTL Cache
Use for:


weather


exchange rates


short-lived API responses


Example:
TTLCache(maxsize=500,ttl=600)
Always:


document TTL choice


prevent thundering herd


lock concurrent access



5. Configuration
Rule
All configuration goes through a single Settings class.
Never use:
os.getenv(...)
throughout code.
Use
class Settings(BaseSettings):    openai_key:str    database_url:str    cheap_model="gpt-4o-mini"    model_config=SettingsConfigDict(        extra="forbid"    )
Rules
Required values:
Field(...)
Unknown environment variables:
extra="forbid"

6. Type Boundaries
Rule
Validate data at system boundaries.
Outside world:
Untrusted.
Inside system:
Trusted.
Boundary examples


HTTP requests


Tool inputs


LLM outputs


webhooks


serialized DB data


Use:
class InputModel(BaseModel):
and:
class OutputModel(BaseModel):
Avoid defensive code everywhere.
Bad:
if x: if isinstance(...)
Validation belongs at entry points.

7. Errors and Failure Isolation
External calls fail.
Always assume:


timeouts


network errors


API outages


rate limits



Layer 1
Timeouts
AsyncClient(timeout=10)

Layer 2
Retries with exponential backoff
@retry(...)
Retry:


timeout


temporary network errors


Never retry:


4xx errors



Layer 3
Failure isolation
Do not crash agents.
Bad:
raise Exception(...)
Use:
class ToolError(BaseModel):    error:str    retryable:bool
Return structured errors.

8. Code Hygiene
Recommended structure:
app/    main.py    config.py    dependencies.py    routes/    services/    tools/    models/    db/tests/

Logging
Never:
print(...)
Use:
structlog
Structured logs:
log.info(...)

Formatting
Required:


ruff


formatter


pre-commit hooks



README
README should explain:


architecture


setup


config


major components



9. Tests
Required minimum:
Pydantic tests
Validate:


valid input


invalid input



Tool tests
Mock:


APIs


LLM calls



End-to-end test
One full happy path.

CI
Tests run automatically:
pytestruff
on:


push


pull request



Final Checklist
Before shipping:
[ ] No blocking I/O
[ ] Dependencies use Depends()
[ ] Heavy resources loaded in lifespan
[ ] Proper cache strategy
[ ] Settings class only
[ ] Pydantic at boundaries
[ ] Timeouts and retries
[ ] Structured logging
[ ] Modular project structure
[ ] Tests + CI

Engineering is writing code that others can change without fear.
This structure is optimized for an AI/code assistant to read as rules rather than as a narrative document.
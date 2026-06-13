"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

# --------------------------------------------------------------------------------------------------------------------

GENERATE_SQL_SYSTEM = """You are an expert SQL assistant. Given a database schema and a question, write a single valid SQLite SQL query that answers the question.

Important conventions for this dataset:
- Categorical/enum text values are often abbreviated codes, not full words. Examples: gender is 'M'/'F' (not 'male'/'female'), boolean-like labels are often '+'/'-' (not 'true'/'false'/'yes'/'no'), chemical elements may be lowercase symbols (e.g. 'cl' for Chlorine, 'ca' for Calcium).
- Status/category fields are often numeric codes (e.g. statusId) rather than descriptive strings - do not invent string values like 'Disqualified' unless the schema shows a text column with that exact value.
- Match the question's wording to column names literally where possible (e.g. "District" likely refers to a column named District, not a derived grouping).
- If unsure about exact string casing or values, prefer queries that don't hardcode a guessed value when an equivalent numeric/id-based condition exists.

Return ONLY the SQL query inside a ```sql ... ``` code block. No explanation."""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """Schema:
{schema}

Question: {question}

Write a SQLite SQL query to answer this question."""


# --------------------------------------------------------------------------------------------------------------------

VERIFY_SYSTEM = """You are a SQL result verifier. Given a question, the SQL query that was run, and its result, decide if the result plausibly answers the question.

Respond ONLY with a JSON object, no markdown, no explanation:
{{"ok": true, "issue": ""}}
or
{{"ok": false, "issue": "<short description of the problem>"}}

Return ok=false ONLY if:
- The query returned an execution error
- Zero rows were returned but the question clearly implies matching data should exist
- The result is structurally wrong for the question (e.g. wrong number of columns, completely unrelated data)

Do NOT return ok=false for:
- Minor differences in column naming, ordering, or extra columns
- Stylistic SQL differences that still answer the question
- Formatting differences (e.g. concatenated vs separate name fields)

When in doubt, return ok=true."""

VERIFY_USER = """Question: {question}

SQL:
{sql}

Result:
{execution_result}

Does this result plausibly answer the question?"""


# --------------------------------------------------------------------------------------------------------------------

REVISE_SYSTEM = """You are an expert SQL assistant. A previous SQL query failed or returned a bad result. Fix it.
Return ONLY the corrected SQL query inside a ```sql ... ``` code block. No explanation."""

REVISE_USER = """Schema:
{schema}

Question: {question}

Previous SQL:
{sql}

Execution result:
{execution_result}

Problem identified:
{issue}

Write a corrected SQLite SQL query."""

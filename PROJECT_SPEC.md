# AI Document Research Agent — Complete Project Specification

**Version:** 1.0  
**Project Type:** AI-powered Document Research Platform  
**Architecture:** Angular + FastAPI + RAG  
**Status:** Under Development

---

# 1. Project Overview

Build an AI-powered document research platform that allows users to upload documents, ask natural-language questions, search document contents, and receive accurate answers with source citations.

The system must use Retrieval-Augmented Generation (RAG) to generate answers grounded in uploaded documents rather than relying only on the language model's general knowledge.

## Main Objectives

1. Upload and manage documents.
2. Extract text from PDF, DOCX, and TXT files.
3. Automatically process and index documents.
4. Search document content using vector embeddings.
5. Ask questions about uploaded documents.
6. Generate answers with page-level citations.
7. Maintain conversation history.
8. Enforce strict user-level document access.
9. Provide document-processing status and error handling.
10. Build a clean, responsive Angular interface.

# 2. Technology Stack

## Frontend

- Angular
- TypeScript
- SCSS
- Angular Router
- Angular Reactive Forms
- Angular HTTP Client
- JWT authentication interceptor
- Route guards

## Backend

- Python 3.10
- FastAPI
- SQLAlchemy 2.x
- Pydantic v2
- Alembic
- Async PostgreSQL driver
- JWT authentication
- Argon2 password hashing

## AI and RAG

- OpenAI API or Gemini API
- Embedding model: text-embedding-3-small
- Embedding dimension: 1536
- Vector database: Qdrant
- Retrieval-Augmented Generation (RAG)
- Prompt engineering
- Context retrieval and citation generation

## Background Processing

- Celery
- Redis

## Document Processing

- PyMuPDF for PDF
- python-docx for DOCX
- Python file processing for TXT

## Infrastructure

- Docker
- Docker Compose
- PostgreSQL 16
- Qdrant
- Redis
- Nginx (future deployment)

# 3. System Architecture

Angular frontend communicates with FastAPI.

FastAPI handles authentication, document management, chat, and search.

PostgreSQL stores application data and document metadata.

Qdrant stores vector embeddings and searchable chunk metadata.

Redis and Celery process document ingestion asynchronously.

The LLM generates answers using retrieved document context.

Architecture:

Angular Frontend
    |
    v
FastAPI Backend
    |
    +---- Authentication and Authorization
    |
    +---- Document Management
    |
    +---- Chat and Search
    |
    +---- Document Processing
    |         |
    |         +---- PDF/DOCX/TXT Extraction
    |         +---- Text Chunking
    |         +---- Embedding Generation
    |         +---- Qdrant Indexing
    |
    +---- RAG Pipeline
              |
              +---- Query Embedding
              +---- Vector Retrieval
              +---- Context Preparation
              +---- LLM Generation
              +---- Citation Validation
    |
    +---- PostgreSQL
    +---- Qdrant
    +---- Redis/Celery

# 4. Project Directory Structure

ai-document-research-agent/
│
├── PROJECT_SPEC.md
├── README.md
├── .env
├── .env.example
├── .gitignore
├── docker-compose.yml
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   │
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── processors/
│   │   ├── ai/
│   │   │   ├── embeddings/
│   │   │   ├── retrieval/
│   │   │   ├── generation/
│   │   │   ├── prompts/
│   │   │   └── skills/
│   │   │       └── document_research/
│   │   │           └── SKILL.md
│   │   │
│   │   ├── workers/
│   │   └── utils/
│   │
│   ├── migrations/
│   ├── tests/
│   ├── requirements.txt
│   └── alembic.ini
│
├── frontend/
│   └── src/
│       └── app/
│           ├── core/
│           ├── shared/
│           ├── features/
│           │   ├── auth/
│           │   ├── dashboard/
│           │   ├── documents/
│           │   ├── chat/
│           │   └── settings/
│           └── app.routes.ts
│
├── infrastructure/
│   ├── docker/
│   └── nginx/
│
└── docs/
    ├── architecture.md
    ├── database-design.md
    ├── api-documentation.md
    └── rag-workflow.md

# 5. Authentication Module

Implement secure user authentication.

Features:

- User registration.
- User login.
- JWT access token.
- Password hashing using Argon2.
- Current-user endpoint.
- Logout handling on frontend.
- Protected API endpoints.
- Protected Angular routes.
- Account activation status.

Database table: users

Fields:

- id: UUID primary key
- full_name
- email: unique
- password_hash
- is_active
- created_at
- updated_at

Never store plain-text passwords.

# 6. Document Management Module

Users must be able to:

- Upload documents.
- View uploaded documents.
- View document details.
- Check processing status.
- Search documents.
- Delete documents.
- Retry failed processing.
- View extracted content where authorized.

Supported formats:

- PDF
- DOCX
- TXT

Document statuses:

- uploaded
- processing
- completed
- failed
- deleting

Database table: documents

Fields:

- id: UUID
- user_id: UUID foreign key
- original_filename
- stored_filename
- file_type
- file_size
- storage_path
- page_count
- status
- error_message
- created_at
- updated_at
- processed_at

Store original files in local storage initially. Design the storage service so it can later support S3 or Wasabi.

# 7. Document Processing Pipeline

Implement asynchronous processing.

Workflow:

1. User uploads a document.
2. Validate extension, MIME type, and file size.
3. Store original document.
4. Create PostgreSQL document record.
5. Submit Celery processing task.
6. Extract text from document.
7. Preserve page numbers and metadata.
8. Clean extracted content.
9. Split text into chunks.
10. Generate embeddings.
11. Store chunks in PostgreSQL.
12. Store embeddings in Qdrant.
13. Update document status to completed.

If any stage fails:

- Record the error.
- Mark the document as failed.
- Allow retry.
- Avoid duplicate chunk indexing.

Default chunking:

- Chunk size: approximately 800 tokens.
- Chunk overlap: approximately 120 tokens.

These must be configurable and evaluated using real documents.

# 8. Vector Database Design

Use Qdrant collection:

document_chunks

Configuration:

- Vector size: 1536
- Distance: COSINE
- Embedding model: text-embedding-3-small

Each vector point must include:

- user_id
- document_id
- chunk_id
- page_number
- chunk_index
- document_name
- text

Use UUID-based identifiers.

Every retrieval query must filter by the authenticated user and authorized document IDs.

Never rely only on frontend filtering for data isolation.

# 9. RAG Question Answering Module

Implement the following workflow:

1. Receive user question.
2. Authenticate the user.
3. Determine accessible documents.
4. Generate query embedding.
5. Search Qdrant.
6. Apply user and document filters.
7. Retrieve relevant chunks.
8. Rank results.
9. Prepare context.
10. Send context and question to the LLM.
11. Generate grounded answer.
12. Validate source references.
13. Return answer and citations.

Initial retrieval configuration:

- Top K: 5
- Chunk size: 800 tokens
- Overlap: 120 tokens

Tune these values through testing.

## Answer Rules

- Answer using document evidence.
- Never fabricate facts.
- Include citations for factual claims.
- Never invent page numbers.
- Explain conflicting information.
- Clearly state when information is unavailable.
- Distinguish evidence from interpretation.

Example:

Question:
What is the recommended mixing time?

Answer:
The document specifies a mixing time of 20 minutes.

Sources:
- Document: Production SOP.pdf
- Page: 4
- Chunk: chunk_001

If evidence is missing:

"I could not find sufficient information in your uploaded documents to answer this question."

# 10. Chat Module

Users must be able to:

- Create chat sessions.
- Rename sessions.
- View chat history.
- Send questions.
- Receive answers.
- View citations.
- Delete conversations.

Database tables:

## chat_sessions

- id
- user_id
- title
- created_at
- updated_at

## chat_messages

- id
- session_id
- role
- content
- citations
- created_at

Message roles:

- user
- assistant
- system (internal use only)

Each session must belong to an authenticated user.

# 11. Database Design

Required initial tables:

1. users
2. documents
3. document_chunks
4. chat_sessions
5. chat_messages
6. ai_usage_logs

Use:

- UUID primary keys.
- Foreign key constraints.
- Unique constraints.
- Appropriate indexes.
- Created and updated timestamps.
- Alembic migrations.

PostgreSQL is the source of truth for application metadata.

Qdrant is the vector retrieval store.

Keep database models, schemas, services, and routes separated.

# 12. API Design

Use versioned API routes:

/api/v1

## Authentication

POST /api/v1/auth/register

POST /api/v1/auth/login

GET /api/v1/auth/me

## Documents

POST /api/v1/documents/upload

GET /api/v1/documents

GET /api/v1/documents/{document_id}

GET /api/v1/documents/{document_id}/status

DELETE /api/v1/documents/{document_id}

POST /api/v1/documents/{document_id}/reprocess

## Chat

POST /api/v1/chat/sessions

GET /api/v1/chat/sessions

GET /api/v1/chat/sessions/{session_id}

DELETE /api/v1/chat/sessions/{session_id}

POST /api/v1/chat/sessions/{session_id}/messages

GET /api/v1/chat/sessions/{session_id}/messages

## Search

POST /api/v1/search/semantic

## Usage

GET /api/v1/usage/summary

All protected endpoints must validate JWT and resource ownership.

# 13. Angular Frontend

Build a professional, responsive dashboard.

## Authentication

- Login page.
- Registration page.
- Form validation.
- Error messages.
- Loading states.

## Dashboard

Display:

- Total documents.
- Processed documents.
- Processing documents.
- Failed documents.
- Recent activity.
- Recent conversations.

## Document Management

- Document upload.
- Drag-and-drop upload.
- Document list.
- Search and filters.
- Status indicators.
- Document details.
- Retry processing.
- Delete confirmation.

## AI Chat

- Chat session sidebar.
- New conversation.
- Message input.
- Answer rendering.
- Source citations.
- Referenced document details.
- Loading indicators.
- Error handling.

Use reusable Angular components and services.

Use an HTTP interceptor for JWT authorization and route guards for protected pages.

Do not store JWT tokens in localStorage by default. Evaluate secure HttpOnly cookie authentication for production. If using cookies, implement CSRF protections.

# 14. Security Requirements

Security is a core requirement.

Implement:

- JWT validation.
- Argon2 password hashing.
- User-level data isolation.
- Document-level access validation.
- Upload size limits.
- File type validation.
- Safe file storage names.
- API input validation.
- Rate limiting for sensitive endpoints.
- Secure error handling.
- Environment-based secrets.
- CORS restrictions.
- Prompt injection protection.

Treat document contents as untrusted evidence, never as instructions that override the agent's system rules.

Never expose one user's documents, vectors, or conversations to another user.

# 15. Error Handling and Logging

Handle:

- Invalid credentials.
- Duplicate email.
- Expired JWT.
- Unauthorized document access.
- Unsupported files.
- Empty documents.
- Extraction failures.
- Embedding failures.
- Qdrant failures.
- Redis failures.
- LLM failures.
- Background task failures.

Use structured application logs.

Never log passwords, API keys, access tokens, or sensitive document content.

# 16. Testing Requirements

Backend tests:

- User registration.
- Duplicate registration.
- Login success.
- Login failure.
- JWT validation.
- User access restrictions.
- Document upload.
- Document extraction.
- Chunking.
- Embedding generation.
- Vector search.
- Citation correctness.
- Document deletion.
- Chat history isolation.

Frontend tests:

- Login form.
- Registration form.
- Route guards.
- HTTP interceptor.
- Document upload.
- Chat interaction.
- Error states.

Integration tests:

- Upload to completed indexing.
- Question to cited answer.
- Unauthorized cross-user retrieval.
- Document deletion and vector cleanup.

# 17. Development Phases

## Phase 1 — Project Foundation

- Project structure.
- FastAPI setup.
- Angular setup.
- Docker Compose.
- PostgreSQL.
- Qdrant.
- Redis.
- Environment configuration.

## Phase 2 — Authentication

- User model.
- Alembic migrations.
- Password hashing.
- JWT generation.
- Register API.
- Login API.
- Current-user API.
- Angular authentication.

## Phase 3 — Document Management

- Document model.
- Upload API.
- File validation.
- File storage.
- Document listing.
- Document status.
- Delete API.

## Phase 4 — Document Processing

- PDF extraction.
- DOCX extraction.
- TXT extraction.
- Page tracking.
- Text cleaning.
- Chunking.
- Celery tasks.

## Phase 5 — Embeddings and Qdrant

- Embedding service.
- Qdrant collection.
- Vector insertion.
- Metadata filtering.
- Semantic search.
- Retry and idempotency.

## Phase 6 — RAG Pipeline

- Query embedding.
- Retrieval.
- Context building.
- LLM integration.
- Grounded answers.
- Citation validation.
- No-answer handling.

## Phase 7 — Chat System

- Chat sessions.
- Message storage.
- Conversation history.
- Document-based questions.
- Citation display.

## Phase 8 — Angular Dashboard

- Dashboard.
- Document management UI.
- Upload UI.
- AI chat UI.
- Citation interface.
- Responsive design.

## Phase 9 — Testing and Optimization

- Unit tests.
- Integration tests.
- Security tests.
- Performance optimization.
- Retrieval quality evaluation.

## Phase 10 — Deployment

- Dockerized application.
- Production configuration.
- Nginx.
- HTTPS.
- Database backups.
- Logging and monitoring.

# 18. Development Rules for AI Coding Assistants

When implementing this project:

1. Always inspect the existing project before modifying files.
2. Do not overwrite working code unnecessarily.
3. Follow the existing directory structure.
4. Use async SQLAlchemy consistently.
5. Use Alembic for database schema changes.
6. Keep routes, services, schemas, and models separate.
7. Avoid unnecessary abstractions.
8. Implement one development phase at a time.
9. Test every API before moving to the next phase.
10. Never hardcode secrets.
11. Never skip user authorization checks.
12. Never claim a feature is complete without testing it.
13. Provide complete code for changed files.
14. Provide exact terminal commands.
15. Explain migrations and database changes.
16. Keep the implementation compatible with Python 3.10.
17. Do not introduce LangChain or LangGraph until the base RAG pipeline works.
18. Preserve existing working functionality.

# 19. MVP Acceptance Criteria

The first usable release is complete when:

- A user can register and log in.
- A user can upload PDF, DOCX, and TXT files.
- Documents are processed asynchronously.
- Text chunks and embeddings are indexed.
- Users can ask questions about their documents.
- Answers contain verifiable source citations.
- Missing information is handled honestly.
- Users cannot access other users' documents.
- Chat history is saved.
- Document deletion cleans up associated data.
- Angular provides a working dashboard and chat interface.
- The application runs through Docker-based infrastructure.

# 20. Final Project Goal

Deliver a production-oriented AI Document Research Agent that combines document management, semantic search, RAG-based question answering, citation verification, secure multi-user access, and a modern Angular interface.

Build a reliable foundational RAG system first. Add advanced agent capabilities only after the core document research workflow is working correctly.

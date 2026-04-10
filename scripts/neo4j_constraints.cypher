// ============================================================================
// Hammurabi — Neo4j Schema Constraints & Indexes
// Run once against a fresh database before ingestion begins.
// Compatible with Neo4j 5.x (uses IF NOT EXISTS guards).
// ============================================================================

// ── Uniqueness constraints ───────────────────────────────────────────────────

// Jurisdiction node: unique ISO 3166-1 alpha-2 code (e.g. "FR", "EU")
CREATE CONSTRAINT jurisdiction_id_unique IF NOT EXISTS
FOR (j:Jurisdiction) REQUIRE j.id IS UNIQUE;

// LegalCode node: unique within its namespace (e.g. "FR-Civil", "EU-GDPR")
CREATE CONSTRAINT legal_code_id_unique IF NOT EXISTS
FOR (lc:LegalCode) REQUIRE lc.id IS UNIQUE;

// Article node: unique composite ID (e.g. "fr-civil-1103")
CREATE CONSTRAINT article_id_unique IF NOT EXISTS
FOR (a:Article) REQUIRE a.id IS UNIQUE;


// Case node: unique docket/case identifier (e.g. "fr-cassiv-2023-21-1234")
CREATE CONSTRAINT case_id_unique IF NOT EXISTS
FOR (c:Case) REQUIRE c.id IS UNIQUE;

// Amendment node: unique amendment ID (e.g. "fr-civil-1103-amend-2016")
CREATE CONSTRAINT amendment_id_unique IF NOT EXISTS
FOR (am:Amendment) REQUIRE am.id IS UNIQUE;

// Document node: unique upload identifier (UUID)
CREATE CONSTRAINT document_id_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.id IS UNIQUE;

// Clause node: unique identifier within a document (UUID)
CREATE CONSTRAINT clause_id_unique IF NOT EXISTS
FOR (cl:Clause) REQUIRE cl.id IS UNIQUE;

// RiskFlag node: unique identifier (UUID)
CREATE CONSTRAINT risk_flag_id_unique IF NOT EXISTS
FOR (rf:RiskFlag) REQUIRE rf.id IS UNIQUE;


// ── Lookup indexes ───────────────────────────────────────────────────────────

// Filter articles by jurisdiction (most common retrieval dimension)
CREATE INDEX article_jurisdiction_idx IF NOT EXISTS
FOR (a:Article) ON (a.jurisdiction);

// Filter articles by legal code name
CREATE INDEX article_code_idx IF NOT EXISTS
FOR (a:Article) ON (a.code);

// Filter articles by effective_date (for historical queries)
CREATE INDEX article_effective_date_idx IF NOT EXISTS
FOR (a:Article) ON (a.effective_date);

// Filter cases by jurisdiction
CREATE INDEX case_jurisdiction_idx IF NOT EXISTS
FOR (c:Case) ON (c.jurisdiction);

// Filter cases by date (for time-range research queries)
CREATE INDEX case_date_idx IF NOT EXISTS
FOR (c:Case) ON (c.date);

// ── Full-text indexes (for fallback keyword search in Cypher) ────────────────

// Full-text search over article content and heading
CREATE FULLTEXT INDEX article_fulltext_idx IF NOT EXISTS
FOR (a:Article) ON EACH [a.content, a.heading];

// Full-text search over case text
CREATE FULLTEXT INDEX case_fulltext_idx IF NOT EXISTS
FOR (c:Case) ON EACH [c.text, c.summary];

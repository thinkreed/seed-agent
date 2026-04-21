# Memory Graph Enhancement Design

## Background and Motivation

### The Gene Insight

Recent research from EvoMap team (Infinite Evolution Lab × Tsinghua University) reveals a fundamental misunderstanding in the industry about how experience should be stored and retrieved for AI agents:

> **"Complete documentation ≠ High-quality control object."**

The paper "From Procedural Skills to Strategy Genes: Towards Experience-Driven Test-Time Evolution" (arXiv:2604.15097) demonstrates through 4,590 controlled experiments that:

1. **Complete Skill packages (2,500 tokens)** perform **below no-guidance baseline** on strong models (Pro: 60.1→50.7, -9.4pp)
2. **Gene objects (~230 tokens)** outperform baseline by **+3.0pp**
3. **Token budget alignment experiment**: Even when Skill is truncated to 230 tokens (same as Gene), Gene still wins decisively

**Key insight**: It's not about "less is more" — it's about **form**. The `strategy` layer is what makes Gene effective, while `summary` and `overview` layers actually dilute control signals.

### Current System Limitations

Our current Skill system has:

| Component | Status | Gap |
|-----------|--------|-----|
| Tier 1 Index | ✅ Already Gene-like | Compact, signal-focused |
| Tier 2 Full Content | ⚠️ Problem | ~2,500 token documents |
| Trigger Matching | ✅ Works | Similar to `signals_match` |
| Outcome Tracking | ❌ Missing | No feedback loop |
| Strategy Field | ❌ Missing | Core control signal absent |
| AVOID Field | ❌ Missing | Failure distillation missing |

**Core problem**: Skills are written once, never evolved. No mechanism to:
- Track which strategies work
- Learn from failures
- Prevent repeated mistakes
- Make evidence-based selection decisions

---

## Design Overview

### Philosophy

Following Gene's "control density" principle:

> **Experience storage should be separate from control signal injection.**

Our design keeps Skill files pure (only control signals), while storing outcome statistics in a dedicated database layer.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Skill Control Layer                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Tier 1: Index (name + triggers + strategy summary)  │    │
│  │ Tier 2a: Gene slice (~230 tokens)                  │    │
│  │   - strategy (ordered steps)                        │    │
│  │   - AVOID (failure warnings)                        │    │
│  │   - constraints (safety bounds)                     │    │
│  │ Tier 2b: Full SKILL.md (optional fallback)         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│                    Memory Graph Layer                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ gene_outcomes table (in sessions.db)                │    │
│  │   - skill_name                                      │    │
│  │   - signal_pattern                                  │    │
│  │   - outcome_status                                  │    │
│  │   - outcome_score                                   │    │
│  │   - timestamp                                       │    │
│  │   + FTS5 virtual table for signal search            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│                    Selection Algorithm                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 1. Query gene_outcomes for success rates            │    │
│  │ 2. Apply Laplace smoothing + confidence decay       │    │
│  │ 3. Combine with trigger match score                 │    │
│  │ 4. Apply ban threshold for low-value strategies     │    │
│  │ 5. Return best candidate                            │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema

### gene_outcomes Table

Location: `~/.seed/memory/raw/sessions.db` (same as L4 sessions)

```sql
CREATE TABLE IF NOT EXISTS gene_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Core triplet (signal → skill → outcome)
    skill_name TEXT NOT NULL,           -- Skill identifier (maps to Gene's gene_id)
    signal_pattern TEXT NOT NULL,       -- Trigger signal pattern (FTS5 searchable)
    outcome_status TEXT NOT NULL,       -- 'success' | 'failed' | 'partial'
    outcome_score REAL NOT NULL,        -- 0.0 - 1.0 (granular success measure)
    
    -- Metadata
    session_id TEXT,                    -- Links to session_messages table
    timestamp TEXT NOT NULL,            -- ISO 8601 format
    iteration_context TEXT,             -- Optional execution context summary
    
    -- GEP-compatible fields (optional)
    intent TEXT,                        -- 'repair' | 'optimize' | 'innovate'
    blast_radius TEXT,                  -- JSON: {"files": N, "lines": N}
    
    -- Index optimization
    CONSTRAINT unique_outcome UNIQUE (skill_name, signal_pattern, timestamp)
);
```

### FTS5 Virtual Table

For efficient signal pattern matching with Chinese text support:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS gene_outcomes_fts USING fts5(
    signal_pattern,
    skill_name,
    outcome_status,
    content='gene_outcomes',
    content_rowid='id',
    tokenize='jieba'  -- Chinese segmentation
);
```

### Triggers for FTS5 Sync

```sql
-- Insert trigger
CREATE TRIGGER IF NOT EXISTS gene_outcomes_ai AFTER INSERT ON gene_outcomes BEGIN
    INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
    VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
END;

-- Delete trigger
CREATE TRIGGER IF NOT EXISTS gene_outcomes_ad AFTER DELETE ON gene_outcomes BEGIN
    INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
    VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
END;

-- Update trigger
CREATE TRIGGER IF NOT EXISTS gene_outcomes_au AFTER UPDATE ON gene_outcomes BEGIN
    INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
    VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
    INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
    VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
END;
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_skill_name ON gene_outcomes(skill_name);
CREATE INDEX IF NOT EXISTS idx_timestamp ON gene_outcomes(timestamp);
CREATE INDEX IF NOT EXISTS idx_status ON gene_outcomes(outcome_status);
CREATE INDEX IF NOT EXISTS idx_session ON gene_outcomes(session_id);
```

---

## Selection Algorithm

### Core Formula (GEP-style)

The algorithm uses Laplace-smoothed probability with confidence decay:

```
p = (successes + 1) / (total + 2)        -- Laplace smoothing (prevents 0/0)
weight = 0.5 ^ (age_days / half_life)    -- Exponential decay
value = p * weight                        -- Final selection score
```

**Parameters** (configurable):

| Parameter | Default | Description |
|-----------|---------|-------------|
| `half_life_days` | 30 | Confidence decay half-life |
| `ban_threshold` | 0.18 | Below this value → strategy banned |
| `min_attempts_for_ban` | 2 | Minimum attempts before ban applies |
| `memory_weight` | 0.6 | Weight for memory-based score |
| `trigger_weight` | 0.4 | Weight for trigger match score |
| `cold_start_penalty` | 0.5 | Penalty for skills with no history |
| `recent_boost_factor` | 0.2 | Bonus for recent successes (30 days) |

### Selection Flow

```python
def select_best_skill(signals: List[str], available_tools: Set[str]) -> Optional[str]:
    """
    Memory Graph-enhanced skill selection.
    
    Flow:
    1. Filter candidates by platform + tool availability
    2. For each candidate, compute selection score:
       - Query gene_outcomes for (skill_name) success rate
       - Apply Laplace smoothing + confidence decay
       - Add recent success boost
       - Combine with trigger match score
    3. Check ban threshold
    4. Return highest-score candidate (or next if top is banned)
    """
    
    # Step 1: Basic filtering
    candidates = [name for name in skills_meta 
                  if should_show_skill(name, available_tools)]
    
    # Step 2: Score computation
    for skill_name in candidates:
        stats = query_outcome_stats(skill_name)
        
        if stats['total'] == 0:
            # Cold start: no history
            score = trigger_match_score(skill_name, signals) * cold_start_penalty
            mode = 'cold'
        else:
            # Warm start: has history
            p = (stats['successes'] + 1) / (stats['total'] + 2)
            weight = 0.5 ** (stats['age_days'] / half_life_days)
            recent_boost = stats['recent_successes'] / stats['total'] * recent_boost_factor
            
            memory_score = p * weight + recent_boost
            trigger_score = trigger_match_score(skill_name, signals)
            
            score = memory_score * memory_weight + trigger_score * trigger_weight
            mode = 'warm'
        
        skill_scores[skill_name] = {'score': score, 'mode': mode, 'stats': stats}
    
    # Step 3: Rank and apply ban threshold
    ranked = sorted(skill_scores.items(), key=lambda x: x[1]['score'], reverse=True)
    
    for skill_name, info in ranked:
        if info['mode'] == 'warm':
            stats = info['stats']
            # Ban check: 2+ attempts + value < 0.18
            if stats['total'] >= min_attempts_for_ban and info['score'] < ban_threshold:
                continue  # Skip banned skill, try next
        return skill_name
    
    return None  # All candidates banned or no candidates
```

### Cold Start Handling

When a new Skill has no outcome history:

| Strategy | Behavior |
|----------|----------|
| Pure cold start | Use trigger match score with `cold_start_penalty` (0.5×) |
| Partial history | Fall back to trigger match if `total < 3` |
| Exploration mode | Occasionally select low-score candidates (genetic drift) |

---

## Tool Functions

### record_skill_outcome

Records execution result to gene_outcomes table.

```python
def record_skill_outcome(
    skill_name: str,
    outcome: str,           # 'success' | 'failed' | 'partial'
    score: float = 1.0,     # 0.0 - 1.0
    signals: List[str] = None,
    session_id: str = None,
    context: str = None
) -> str:
    """
    Record skill execution outcome.
    
    Called after skill execution completes:
    - AgentLoop: after tool execution iteration
    - AutonomousExplorer: after autonomous task completion
    - RalphLoop: after cycle completion
    
    Returns: Status message with updated statistics
    """
```

### get_skill_stats

Query aggregated statistics for a skill.

```python
def get_skill_stats(skill_name: str) -> Dict:
    """
    Get aggregated outcome statistics for a skill.
    
    Returns:
    {
        'total': N,
        'successes': N,
        'failures': N,
        'success_rate': 0.XX,
        'last_success': 'ISO timestamp',
        'last_failure': 'ISO timestamp',
        'recent_success_rate': 0.XX,  # Last 30 days
        'is_banned': bool,
        'ban_until': 'ISO timestamp' | None
    }
    """
```

### list_banned_skills

List skills currently under ban.

```python
def list_banned_skills() -> List[Dict]:
    """
    List skills with value below ban_threshold.
    
    Returns:
    [
        {
            'skill_name': 'xxx',
            'total_attempts': N,
            'current_value': 0.XX,
            'ban_reason': 'Low success rate',
            'suggested_action': 'Review strategy or retire'
        }
    ]
    """
```

---

## Skill Frontmatter Enhancement

### New Fields (Control Signals Only)

The frontmatter is enhanced with Gene-style control fields, **not statistics** (which go to gene_outcomes table):

```yaml
---
name: skill-name
description: Brief description
triggers: [trigger1, trigger2]

# New: Gene-style control signals
strategy:                         # Ordered actionable steps
  - "Step 1: Analyze the input structure"
  - "Step 2: Identify key patterns"
  - "Step 3: Apply transformation"

avoid:                            # Distilled failure warnings
  - "AVOID: Passing min_distance directly as wavelength"
  - "AVOID: Using peak_widths output without unit conversion"

constraints:                      # Safety bounds
  max_files: 10
  forbidden_paths: ["config/", ".env"]

validation:                       # Post-execution verification
  - "pytest tests/ -v"
  - "ruff check src/"
---
```

### Token Budget Estimation

| Field | Token Count | Control Value |
|-------|-------------|---------------|
| name + description + triggers | ~80 | ✅ Routing signal |
| strategy | ~50-100 | ✅ Core control |
| avoid | ~30-50 | ✅ Failure prevention |
| constraints | ~20 | ✅ Safety boundary |
| validation | ~20 | ✅ Verification |
| **Total Tier 2a** | **~200-280** | **All control signals** |

Compare with current full SKILL.md: ~2,500 tokens (most are human-readable noise).

---

## Integration Points

### session_db.py

```python
class SessionDB:
    def _init_db(self):
        # ... existing tables ...
        
        # Add gene_outcomes table
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS gene_outcomes (...);
            CREATE VIRTUAL TABLE IF NOT EXISTS gene_outcomes_fts USING fts5 (...);
            -- triggers and indexes ...
        """)
```

### skill_loader.py

```python
class SkillLoader:
    def select_best_skill(self, signals, available_tools) -> Optional[str]:
        """Memory Graph-enhanced selection"""
        # Implementation per algorithm above
    
    def get_gene_slice(self, name: str) -> str:
        """Extract Tier 2a (strategy + avoid + constraints)"""
        # Return compact control signal injection

# New tool functions
def record_skill_outcome(skill_name, outcome, score, signals, session_id, context) -> str:
    """Record to gene_outcomes table"""

def get_skill_stats(skill_name) -> Dict:
    """Query aggregated statistics"""

def list_banned_skills() -> List[Dict]:
    """List low-value skills"""
```

### agent_loop.py

```python
class AgentLoop:
    async def _execute_tool_calls(self, tool_calls):
        # ... execute tools ...
        
        # After skill execution, record outcome
        if tool_name == 'load_skill':
            skill_name = tool_args.get('name')
            # Determine outcome based on subsequent responses
            outcome = self._evaluate_skill_outcome(skill_result)
            record_skill_outcome(
                skill_name=skill_name,
                outcome=outcome,
                score=...,
                signals=self._extract_signals_from_context(),
                session_id=self.session_id
            )
```

### autonomous.py

```python
class AutonomousExplorer:
    async def _execute_autonomous_task(self):
        # Use Memory Graph selection
        best_skill = self.agent.skill_loader.select_best_skill(
            signals=self._extract_task_signals(),
            available_tools=self.agent.tools.get_tool_names()
        )
        
        if best_skill:
            content = self.agent.skill_loader.load_skill_content(best_skill)
            # Execute with outcome tracking
```

---

## GEP Protocol Compatibility

This design maintains compatibility with GEP (Gene Evolution Protocol) for potential future integration:

| GEP Component | Our Implementation | Compatibility |
|---------------|-------------------|---------------|
| Gene | Skill + frontmatter strategy/avoid/constraints | ✅ Compatible |
| Capsule | session_messages + gene_outcomes | ⚠️ Partial (no diff capture yet) |
| EvolutionEvent | gene_outcomes + session_id link | ✅ Compatible |
| Memory Graph | gene_outcomes table | ✅ Compatible |
| signals_match | triggers field | ✅ Compatible |
| Content-addressing | Not implemented | ⚠️ Optional upgrade |

**Upgrade path to full GEP**:
1. Add SHA-256 asset_id to skill frontmatter
2. Add Capsule table with diff capture
3. Implement Skill Distillation from successful outcomes
4. Add A2A protocol for skill sharing

---

## Configuration

### Environment Variables

```bash
# Memory Graph parameters
MEMORY_GRAPH_HALF_LIFE=30           # Confidence decay half-life (days)
MEMORY_GRAPH_BAN_THRESHOLD=0.18     # Value below this → banned
MEMORY_GRAPH_MIN_ATTEMPTS=2         # Min attempts before ban applies
MEMORY_GRAPH_MAX_ENTRIES=5000       # Max entries per skill (FIFO cleanup)
MEMORY_GRAPH_ENABLED=true           # Enable/disable Memory Graph selection

# Skill loading parameters  
SKILL_DEFAULT_MODE=gene             # 'gene' (Tier 2a) or 'full' (Tier 2b)
```

### Config File Section

Add to `~/.seed/config.json`:

```json
{
  "memory_graph": {
    "enabled": true,
    "half_life_days": 30,
    "ban_threshold": 0.18,
    "min_attempts_for_ban": 2,
    "memory_weight": 0.6,
    "trigger_weight": 0.4,
    "cold_start_penalty": 0.5,
    "recent_boost_factor": 0.2,
    "max_entries_per_skill": 5000
  }
}
```

---

## Implementation Roadmap

### Phase 1: Database Infrastructure (1-2 days)

- [ ] Add gene_outcomes table to session_db.py
- [ ] Add FTS5 virtual table + triggers
- [ ] Add indexes for query optimization
- [ ] Test table creation and basic queries

### Phase 2: Tool Functions (1-2 days)

- [ ] Implement record_skill_outcome()
- [ ] Implement get_skill_stats()
- [ ] Implement list_banned_skills()
- [ ] Register tools in ToolRegistry
- [ ] Write unit tests

### Phase 3: Selection Algorithm (2-3 days)

- [ ] Implement select_best_skill() in skill_loader.py
- [ ] Implement Laplace smoothing + decay formula
- [ ] Implement ban threshold logic
- [ ] Implement cold start handling
- [ ] Implement genetic drift (optional exploration)
- [ ] Integration tests

### Phase 4: Agent Integration (2 days)

- [ ] AgentLoop: auto-record after skill execution
- [ ] AutonomousExplorer: use Memory Graph selection
- [ ] RalphLoop: outcome tracking per cycle
- [ ] CLI: display skill stats on selection

### Phase 5: Frontmatter Enhancement (1 day)

- [ ] Define new YAML schema (strategy, avoid, constraints, validation)
- [ ] Update skill_loader parsing
- [ ] Implement get_gene_slice() for Tier 2a extraction
- [ ] Migration script for existing skills

### Phase 6: Validation & Tuning (continuous)

- [ ] Monitor gene_outcomes growth
- [ ] Collect success rate statistics
- [ ] Tune parameters (half_life, ban_threshold, weights)
- [ ] A/B test: Memory Graph vs baseline selection
- [ ] Document best practices

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Skill selection accuracy | +5% improvement | Compare Memory Graph vs trigger-only selection success rate |
| Repeated failure rate | <5% | Track how often banned skills are still selected |
| Token efficiency | <300 tokens Tier 2a | Measure Gene slice injection size |
| Memory Graph coverage | >80% skills have history | Track skills with >=3 outcome records |
| Cold start success | >50% | First-use success rate for new skills |

---

## References

- **GEP Protocol Specification**: https://evomap.ai/wiki/16-gep-protocol
- **Gene Paper**: "From Procedural Skills to Strategy Genes" (arXiv:2604.15097)
- **Evolver GitHub**: https://github.com/EvoMap/evolver
- **CritPt Benchmark**: https://critpt.com/

---

## Appendix: SQL Queries Reference

### Aggregated Statistics Query

```sql
SELECT 
    skill_name,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
    SUM(CASE WHEN outcome_status = 'failed' THEN 1 ELSE 0 END) as failures,
    ROUND(SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as success_rate,
    MAX(CASE WHEN outcome_status = 'success' THEN timestamp ELSE NULL END) as last_success,
    MAX(CASE WHEN outcome_status = 'failed' THEN timestamp ELSE NULL END) as last_failure
FROM gene_outcomes
GROUP BY skill_name
ORDER BY success_rate DESC;
```

### Low-Value Skills Query (Ban Candidates)

```sql
SELECT 
    skill_name,
    COUNT(*) as total,
    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as successes,
    ROUND((SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) + 1) * 100.0 / (COUNT(*) + 2), 2) as laplace_rate
FROM gene_outcomes
WHERE timestamp > datetime('now', '-30 days')
GROUP BY skill_name
HAVING COUNT(*) >= 2 
  AND (SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) + 1.0) / (COUNT(*) + 2.0) < 0.18
ORDER BY laplace_rate ASC;
```

### Signal Pattern Search

```sql
-- FTS5 search for signal patterns
SELECT 
    skill_name,
    outcome_status,
    outcome_score,
    timestamp
FROM gene_outcomes_fts
WHERE signal_pattern MATCH 'error retry timeout'
ORDER BY timestamp DESC
LIMIT 20;
```

### Recent Success Rate (Last 30 Days)

```sql
SELECT 
    skill_name,
    COUNT(*) as recent_total,
    SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) as recent_successes,
    ROUND(SUM(CASE WHEN outcome_status = 'success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) as recent_rate
FROM gene_outcomes
WHERE timestamp > datetime('now', '-30 days')
GROUP BY skill_name
ORDER BY recent_rate DESC;
```
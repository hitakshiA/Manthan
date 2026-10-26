-- Pretty trace summaries for events.
--
-- Filled in by worker.prettifier (Gemini Flash Lite). Null while pending;
-- one short sentence (≤14 words) once enriched. UI shows summary by
-- default and falls back to raw rendering.

ALTER TABLE events ADD COLUMN IF NOT EXISTS summary TEXT;

-- Find pending events to prettify quickly.
CREATE INDEX IF NOT EXISTS idx_events_pending_summary
    ON events (org_id, id)
    WHERE summary IS NULL
      AND type IN ('tool_call', 'tool_result', 'finding_recorded', 'reflexion', 'brief_drafted');

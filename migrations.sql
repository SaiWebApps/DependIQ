-- DependIQ schema migrations
-- Format: one idempotent ALTER statement per line (e.g. ADD COLUMN IF NOT EXISTS)
-- Each statement must be safe to run on every deploy.
-- Add a date comment above each statement explaining when/why it was added.

-- 2026-05-07: Add workspaces table for team-level project grouping
CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2026-05-07: Add workspace_members table for membership tracking
CREATE TABLE IF NOT EXISTS workspace_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP DEFAULT NOW()
);

-- 2026-05-07: Link projects to workspaces (nullable for existing projects)
ALTER TABLE project_library ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL;

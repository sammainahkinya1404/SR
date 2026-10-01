"""Application services. Every write goes through here: permission checks, ledger postings,
audit entries and domain events all live in this layer, never in the API routes (spec Part B §9)."""

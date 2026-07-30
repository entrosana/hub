"""Domain packs: the only place canonical vocabulary is declared.

The provider kernel (`vocabulary`, `spec`, `executor`, `registry`, `transport`,
`pathfinder`) carries no domain knowledge. Each pack registers its canonical ops,
its author-time search synonyms, and how a tenant is bound to a provider.
"""

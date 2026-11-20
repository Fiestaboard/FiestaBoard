# Request address policy

Keep the supported local administration modes while applying one address
policy before the API routes and mounted transports. Cover local addresses,
explicit browser origins, reverse proxy configuration, and discovery.

Validation starts with handler-level regression cases, then covers the real
application middleware order, authentication, discovery and MCP contracts.
Run the full Python suite and repository checks before publication. This
backend change has no visual design or component changes.

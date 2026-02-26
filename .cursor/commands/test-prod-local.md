Test the production build locally by stopping dev containers, building production images, and starting them with docker-compose.prod.yml. Run the following commands in sequence:

1. docker-compose -f docker-compose.dev.yml down
2. docker-compose -f docker-compose.prod.yml build --no-cache
3. docker-compose -f docker-compose.prod.yml up -d

This builds and runs the production images locally for testing before deploying to your NAS. The UI will be available at http://localhost:4420.

After completion, show the user:
- How to access the UI (http://localhost:4420)
- How to view logs: `docker-compose -f docker-compose.prod.yml logs -f`
- How to check status: `docker-compose -f docker-compose.prod.yml ps`
- Remind them that System Management features will be visible in Settings (production only)
- How to stop: `docker-compose -f docker-compose.prod.yml down`
- How to return to dev mode: `/start`


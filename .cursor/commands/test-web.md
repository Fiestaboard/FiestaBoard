Run tests for the web UI inside the Docker container. Execute:

docker-compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm test"

Show the test results and explain any failures if they occur.





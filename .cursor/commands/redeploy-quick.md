Stop, rebuild (using cache), and restart all Docker containers using docker-compose.dev.yml. Run the following commands in sequence:

1. docker-compose -f docker-compose.dev.yml down
2. docker-compose -f docker-compose.dev.yml build
3. docker-compose -f docker-compose.dev.yml up -d

This is faster than /redeploy because it uses Docker's build cache. After completion, show the user how to view logs and check container status.





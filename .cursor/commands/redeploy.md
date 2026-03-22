Stop, rebuild (with --no-cache), and restart all Docker containers using docker-compose.dev.yml. Run the following commands in sequence:

1. docker-compose -f docker-compose.dev.yml down
2. docker-compose -f docker-compose.dev.yml build --no-cache
3. docker-compose -f docker-compose.dev.yml up -d

After completion, show the user how to view logs and check container status.





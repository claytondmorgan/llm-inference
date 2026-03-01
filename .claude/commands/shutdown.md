Shut down all AWS infrastructure to minimize costs.

Run `./aws-shutdown.sh` from the project root to:
- Scale all ECS services to desired=0 (llm-inference-service, llm-search-engine, llm-ingestion-worker)
- Wait for running tasks to drain
- Stop the RDS instance (llm-postgres)
- Print estimated idle cost

Report the final state and confirm everything is stopped.
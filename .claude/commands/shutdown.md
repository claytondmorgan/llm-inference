Shut down all AWS infrastructure to minimize costs.

Run `./aws-shutdown.sh` from the project root to:
- Scale all ECS services to desired=0 (llm-inference-service, llm-search-engine, llm-ingestion-worker)
- Wait for running tasks to drain
- Snapshot the RDS instance (llm-postgres → llm-postgres-dormant)
- Delete the RDS instance after snapshot completes
- Print estimated idle cost (~$0.83/day)

Report the final state and confirm everything is stopped.
import asyncio

from app.db.postgres import async_session_maker
from app.services.nlp_orchestrator import NLPOrchestrator


async def test():
    async with async_session_maker() as session:
        orchestrator = NLPOrchestrator()
        summary = await orchestrator.run_nlp_cycle(session)
        print(f'Total Processed: {summary.total_processed}')
        print(f'Claims Extracted: {summary.claims_extracted}')
        print(f'LLM Calls: {summary.llm_calls_made}')
        print(f'Statuses: {summary.status_counts}')

if __name__ == '__main__':
    asyncio.run(test())


"""Send one synthetic chat trace and verify it is readable in LangSmith."""
import os
import time

from langsmith import Client, trace
from langsmith.utils import LangSmithNotFoundError


def main() -> int:
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true" or not os.getenv("LANGSMITH_API_KEY"):
        print("chat_tracing_not_configured")
        return 2
    client = Client()
    try:
        with trace("chat_stream", run_type="chain", client=client,
                   inputs={"query": "공개 검증용 질문", "conversation_id": "synthetic-smoke"},
                   tags=["tax-assistant", "chat", "synthetic-smoke"]) as run:
            run.end(outputs={"answer": "공개 검증용 응답"})
        client.flush(timeout=10)
        for _ in range(6):
            try:
                observed = client.read_run(run.id)
                if observed.outputs and observed.outputs.get("answer") == "공개 검증용 응답":
                    print("chat_trace_readback: ok")
                    return 0
                print("chat_trace_readback: incomplete")
                return 1
            except LangSmithNotFoundError:
                time.sleep(1)
        print("chat_trace_readback: not_found")
        return 1
    except Exception as exc:
        print(f"chat_trace_readback: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

# 세션 인수인계

## 2026-08-23 Ollama 동시 GPU 적재

- `qwen3.5:9b` 5.5GB와 `qwen3-embedding:4b` 4.4GB를 컨텍스트 4,096에서 모두
  100% GPU로 적재했고 3회 교차 호출을 통과했다. 잔여 VRAM은 약 463MiB다.
- 운영 chat 기본 `OLLAMA_NUM_CTX`는 4,096로 변경했다. 병렬도 증가나 Windows GPU 사용량
  급증 시 OOM 위험이 있으므로 `OLLAMA_NUM_PARALLEL=1`을 유지한다.

## 2026-08-23 serving 실험 환경 최종 감사

- WSL/Windows를 점검해 vLLM·Infinity·TEI·llama.cpp·리랭커 실행 자원과 어제 받은 모델을
  정리했다. WSL에는 관련 컨테이너·이미지·모델 볼륨·Python 패키지가 남아 있지 않다.
- 현재 운영 자원인 Windows Ollama, `qwen3.5:9b`, `qwen3-embedding:4b`와 프로젝트 DB는 보존했다.
- 재도입용 llama.cpp 코드와 Compose 파일만 저장소에 남아 있다.

## 2026-08-23 llama.cpp 실행 자원 삭제

- llama.cpp 도입 코드는 유지하고 WSL Docker의 컨테이너 2개, 이미지 2개와
  `tax_assistant_llama_cache`만 삭제했다.
- 현재 런타임은 Ollama LLM·Ollama v1 임베딩이며, llama.cpp를 다시 사용할 때는
  `dev/docker-up-llamacpp-wsl.sh`가 필요한 이미지와 모델을 재다운로드한다.

## 2026-08-23 vLLM·Infinity 제거

- vLLM·Infinity 전용 파일, 컨테이너, 이미지와 Hugging Face/Infinity 모델 캐시 볼륨을 삭제했다.
- 이후 표준 실행은 `dev/docker-up-llamacpp-wsl.sh`만 사용한다.
- PostgreSQL 데이터와 `tax_assistant_llama_cache`는 보존했다.
- 과거 vLLM·Infinity 절은 실험 이력이며 재실행 지침이 아니다.
- TEI Docker 이미지와 `tax_assistant_reranker_cache`, 리랭커 코드·설정·health/UI 표시도 제거했다.
- 후속 llama.cpp CPU A/B에서 BGE-Reranker-v2-M3 Q4는 MRR 0.9276→0.9088로 하락하고
  평균 1.746초가 추가되어 채택하지 않았다. 현재 검색 정렬을 유지한다.

## 2026-08-23 llama.cpp 소규모 서비스 전환

- 신규 overlay `docker-compose.llamacpp.yml`과 실행 스크립트
  `dev/docker-up-llamacpp-wsl.sh`를 추가했다.
- 생성은 Qwen3.5-9B GGUF Q4_K_M CUDA, embedding_v2는 Qwen3 Embedding 4B GGUF
  Q4_K_M CPU/last pooling 구성이다. 활성 임베딩은 데이터 안전을 위해 아직 v1이다.
- 다음 필수 작업은 llama.cpp 임베딩 비교·백필·골든셋 평가와
  `dragonkue/bge-reranker-v2-m3-ko`의 자체 GGUF Q4_K_M 변환 및 평가다.
- 최신 backend 이미지 전체 테스트는 `287 passed`, llama.cpp Compose config는 정상이다.
  실제 기동에서 llama.cpp CPU/CUDA 이미지는 정상 pull됐으나 컨테이너가 Hugging Face의
  IPv6 주소만 해석하고 연결하지 못해 GGUF 다운로드가 실패했다. WSL 호스트 HTTPS는
  정상이다. 다음 작업은 호스트에 GGUF를 선다운로드하고 read-only volume으로 마운트하는 것이다.
- Mac에서는 Docker가 Metal GPU를 전달하지 않으므로 llama-server를 호스트에서 실행하고
  backend 컨테이너가 `host.docker.internal`로 접속하는 별도 프로파일이 필요하다.

## 2026-08-23 vLLM NVFP4 재검증

- 10.43GiB는 체크포인트 다운로드 크기이며 실제 가중치 VRAM 사용량으로 해석하지 않는다.
- 모델 제작자의 Qwen3.5 하이브리드 구조 주의사항에 따라 Compose의 FP8 KV cache 강제
  설정을 제거했다. 단독 계측에서 compressed-tensors 양자화, 모델 로딩 9.71GiB,
  weights+non-torch 10.11GiB, activation 0.27GiB, KV cache 0.37GiB를 확인했다.
- `gpu-memory-utilization=0.96`은 Windows가 사용하는 VRAM 때문에 시작 전 검사에서 실패했다.
  `0.90`에서는 11,205/12,227MiB를 사용하며 컨테이너 health가 통과했다.

## 2026-08-23 Ollama 임베딩 상주 옵션 제거

- Ollama 임베딩 adapter는 `/api/embed` 요청에 `keep_alive`를 보내지 않는다.
- `OLLAMA_KEEP_ALIVE_SEC=-1`은 Ollama 채팅 LLM에만 적용된다. 이미 메모리에 올라간
  임베딩 모델은 다음 정상 임베딩 요청부터 Ollama 기본 유휴 만료 정책을 적용받는다.

## 2026-08-22 provider 중립화 및 Infinity 검증

- 생성 LLM provider는 `ollama`/`vllm`, 임베딩과 리랭커 provider는 각각
  `ollama`/`infinity`만 허용한다.
- 최신 백엔드 Docker 이미지 전체 테스트 결과는 `284 passed`이다.
- Infinity 공식 CPU 이미지의 Transformers가 Qwen3를 인식하지 못해 커스텀 이미지에
  Transformers 4.56.2와 Sentence-Transformers 5.1.1을 고정했다.
- Qwen 공식 모델은 last-token pooling을 요구한다. smoke test에서 부분 snapshot이
  mean pooling으로 대체되는 현상을 확인했다. 활성 버전은 v1 Ollama로 유지하며
  `embedding_v2` 백필은 실행하지 않았다.
- 공식 Ollama는 범용 `/api/rerank`를 제공하지 않는다. Ollama reranker adapter는
  호환 API 게이트웨이용이며, 기본 Ollama에서는 Infinity를 사용하거나 비활성화한다.
- Infinity 임베딩과 리랭커를 별도 컨테이너로 분리했다. 각 역할은
  `INFINITY_*_DEVICE=cpu|cuda`로 독립 배치하며 `dev/set-inference-device-wsl.sh`로
  해당 컨테이너만 재생성할 수 있다. 12GB GPU에서는 vLLM 실행 중 GPU 전환을 차단한다.
- 이전의 컨테이너 시작 시각 초기화는 Docker Desktop 크래시가 아니었다. Docker는
  Ubuntu WSL 내부 systemd 서비스이며, Codex의 일회성 `wsl.exe -e` 명령이 끝날 때
  배포판도 Stopped 상태가 되어 다음 명령에서 다시 시작된 것이다.
- 실제 vLLM 차단 원인은 Windows Ollama의 `qwen3-embedding:4b Q4_K_M`이
  `keep_alive=-1`로 GPU에 상주하면서 VRAM 약 4.37GB를 점유한 것이다. vLLM의 기존 0.96 설정은
  시작 시 11.46GiB free VRAM을 요구하지만 실제 free는 10.77GiB였다. Ollama 임베딩을
  CPU 전용 서버로 옮기거나 언로드하기 전에는 12GB GPU에서 vLLM과 동시 실행할 수 없다.
- WSL RAM은 24GB(실제 23.47GiB), swap 16GB로 정상 적용됐다. 안정화를 위해 vLLM과
  두 Infinity 모델은 현재 중지했다.

이 파일은 미완료 작업 또는 다음 세션에 반드시 전달해야 하는 내용이 있을 때 갱신한다.
완료된 작업의 장기 상태는 `CURRENT_STATUS.md`, 영구 설계 이유는 `DECISIONS.md`에 반영한다.

## 현재 인수인계

- 활성 작업: vLLM 생성 서버와 한국어 리랭커 구현 및 실제 기동 완료. 새 작업 전 `git status --short`로 기존 변경을 확인할 것.
- 최근 영역: 생성 LLM vLLM 전환, Ollama 임베딩 유지, Docker GPU 실행 스크립트.
- 최근 검증: provider·health·검색 관련 최신 backend 선택 테스트 `29 passed`. 전체 테스트는 Infinity 전환 완료 후 재실행 필요.
- NVIDIA Container Toolkit 1.20.0 설치, Docker `nvidia` runtime 등록 및 컨테이너 `nvidia-smi` 검증 완료. `dev/docker-up-vllm-wsl.sh`로 전체 스택 기동 및 dependency health를 확인했다.
- 모델 조합: 생성 `ig1/Qwen3.5-9B-NVFP4`, 임베딩 `Qwen3-Embedding-4B`, 리랭커 `dragonkue/bge-reranker-v2-m3-ko`. 임베딩·리랭커는 Infinity CPU 다중 모델 overlay로 통합 중이다.
- 12GB GPU 제약: NVFP4 모델은 텍스트 전용·eager·기본 KV dtype·2,048 토큰·동시 1요청·GPU utilization 0.90으로 검증했다. CPU offload는 Qwen GDN Triton 커널의 CPU pointer 오류로 사용할 수 없다.
- CPU 추론 제약: WSL 할당 RAM은 15GiB이며 Infinity 컨테이너는 12GiB로 제한했다. Qwen3 Embedding 4B 백필과 reranker 동시 실행의 지연·메모리를 실제 측정해야 한다.
- 공식 Infinity `latest-cpu` smoke test는 내장 Transformers가 `qwen3`를 인식하지 못해 실패했다. `docker/infinity.Dockerfile`에서 Qwen3 지원 버전을 고정했으며 커스텀 이미지 재검증이 필요하다.
- 프런트엔드는 `/api/health/dependencies`를 30초마다 조회해 역할별 실제 provider와 모델을 표시한다.
- 데이터 주의: 기존 DB는 과거 수집기로 인해 호·목이 누락됐을 수 있으며 전체 재수집은 아직
  자동 실행하지 않는다.
- 추천 다음 작업: `target.text`를 직접 조문 RAG 컨텍스트에 우선 반영.

## 작업 중 갱신 형식

```markdown
### YYYY-MM-DD — 작업 제목

- 사용자 목표:
- 완료한 변경:
- 변경 파일:
- 실행한 검증과 결과:
- 남은 작업:
- 막힌 이유 또는 필요한 사용자 결정:
- 데이터·마이그레이션·배포 주의사항:
```

## 갱신 원칙

- “테스트 완료” 대신 명령과 결과 수를 쓴다.
- 실행하지 않은 작업을 완료로 표시하지 않는다.
- 코드 경로와 함수명을 구체적으로 적는다.
- 비밀값, 토큰, 실제 `.env` 내용을 기록하지 않는다.
- 작업이 완전히 끝나면 임시 메모를 제거하고 `CURRENT_STATUS.md`에 최종 상태를 반영한다.

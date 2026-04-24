# Especificação: Migração do Agente n8n → Modal (Python + LangGraph)

> **Versão:** 2.0 — Revisada após auditoria cruzada com `n8n_workflow.json` e documentações oficiais (Modal, LangGraph, Meta Platform, Redis).

---

## 1. Objetivo

Migrar o "clone conversacional" do Dr. Antonio de Deus (Instagram Direct) da plataforma visual n8n para código Python determinístico, orquestrado pelo **LangGraph** e hospedado na infraestrutura serverless do **Modal**.

**Meta principal:** Eliminar a dependência do n8n mantendo 100% de paridade funcional com o workflow original e ganhando testabilidade, observabilidade e controle de versão.

---

## 2. Requisitos e Restrições

### 2.1 Resposta Instantânea à Meta
O webhook exposto no Modal retornará `HTTP 200 OK` de forma **instantânea** (< 100ms). Todo processamento pesado (debounce, IA, envio) será delegado a uma função Modal em background via `.spawn()`. Isso impede que a Meta reentre com retransmissões por timeout (limite de ~20s).

### 2.2 Debounce / Empilhamento de Mensagens (via Redis)
Reproduz fielmente a lógica de empilhamento do n8n:
1. Mensagem chega → é adicionada a uma lista no Redis (`RPUSH`).
2. Se for a **primeira mensagem** da janela (lista estava vazia), o worker aguarda **2 segundos** (`asyncio.sleep`).
3. Mensagens subsequentes dentro da janela apenas fazem `RPUSH` e encerram silenciosamente.
4. Após o timer, o worker lê toda a lista (`LRANGE`), apaga a chave (`DEL`) e concatena tudo para enviar ao agente LLM.

### 2.3 Modelos de IA (com Fallback)
- **Primário:** Google Gemini Flash (`gemini-3.0-flash` via `ChatGoogleGenerativeAI`)
- **Fallback:** OpenAI GPT-5-mini (`gpt-5-mini` via `ChatOpenAI`)
- Mecanismo: `.with_fallbacks()` nativo do LangChain — se o Gemini retornar erro (500, rate limit, timeout), a mesma chamada é automaticamente refeita no GPT-5-mini.

### 2.4 Tradução Multimídia Nativa
Áudios e imagens são baixados da CDN da Meta e passados diretamente como conteúdo multimodal ao Gemini (que suporta áudio e imagem nativamente), sem necessidade de pipeline separada de Whisper + GPT-4o-mini. Em caso de fallback para OpenAI, o conteúdo multimídia é convertido para base64 no formato esperado pela API da OpenAI.

### 2.5 Persistência de Memória (Simples e Direta)

O fluxo de mensagens é baixo, então a persistência será simples: escrita direta na tabela existente do Supabase, sem camadas extras de checkpointing.

- **Tabela:** `ias_chat_histories_drAntonio` (schema: `session_id`, `message` como JSON `{type, content}`)
- **Escrita:** Supabase client faz `INSERT` das mensagens `human` (entrada do paciente) e `ai` (resposta do agente)
- **Leitura:** Para carregar o histórico da conversa no LangGraph, o `chat_history_writer.py` faz `SELECT` das últimas N mensagens filtradas por `session_id` e as converte em `HumanMessage`/`AIMessage` do LangChain
- **session_id:** `{sender_id}_direct_drantonio` (mesmo padrão do n8n)
- **LangGraph:** Compilado sem checkpointer (`graph.compile()` sem `PostgresSaver`). O estado da conversa é reconstruído a cada invocação a partir do histórico lido do Supabase — exatamente como o n8n já fazia.

### 2.6 Ambiente Local com Logs Detalhados
- `modal serve` sobe um endpoint público HTTPS temporário (sufixo `-dev`) para testar o fluxo inteiro na nuvem com hot-reload.
- Script `execution/simulate_webhook.py` dispara payloads idênticos ao formato da Meta contra o endpoint dev, permitindo testar sem reconfigurar o app da Meta.
- Logging estruturado em JSON (via `structlog`) em todos os módulos, com níveis: `DEBUG` para dev, `INFO` para produção.

---

## 3. Três Camadas de Bloqueio (Fielmente do n8n)

O workflow n8n implementa **3 mecanismos de bloqueio distintos** que devem ser preservados:

### 3.1 Deduplicação de Mensagem
- **Chave Redis:** `{message_mid}` (o `mid` da mensagem do Instagram)
- **TTL:** 30 segundos
- **Quando ativa:** Ao enviar a resposta com sucesso (após `Reply_direct`)
- **Propósito:** Impede que retransmissões da Meta (webhook retry) reprocessem a mesma mensagem.

### 3.2 Bloqueio por Echo (Humano Respondeu)
- **Chave Redis:** `{recipient_id}_direct_dr_antonio_block`
- **TTL:** 180 segundos (3 minutos)
- **Quando ativa:** Quando chega uma mensagem com `is_echo=true` (o Dr. Antonio respondeu manualmente pelo Instagram)
- **Propósito:** O bot fica em silêncio por 3 minutos para não atropelar o humano.

### 3.3 Bloqueio pós-Handoff (Equipe Assumiu)
- **Chave Redis:** `{recipient_id}_direct_dr_antonio_block`
- **TTL:** 18000 segundos (5 horas)
- **Quando ativa:** Após salvar a conversa no Supabase (fluxo de echo com persistência)
- **Propósito:** Quando a equipe assume a conversa via outro canal, o bot para completamente por 5 horas.

---

## 4. Fluxo Completo de Processamento

```
Meta Webhook POST
       │
       ▼
┌─────────────────────┐
│  webhook_handler.py │  ← GET: verificação hub.challenge
│  (FastAPI endpoint)  │  ← POST: extrai payload, retorna 200 OK
└──────────┬──────────┘
           │ .spawn()
           ▼
┌─────────────────────┐
│ message_processor.py│  ← Orquestrador principal
└──────────┬──────────┘
           │
     ┌─────┴──────┐
     ▼            ▼
┌─────────┐  ┌──────────────┐
│ block   │  │ instagram    │
│ manager │  │ receiver     │
│ .py     │  │ .py          │
│         │  │ (download    │
│ dedup?  │  │  mídia)      │
│ echo?   │  └──────┬───────┘
│ handoff?│         │
└────┬────┘         │
     │ ok           │
     ▼              ▼
┌─────────────────────┐
│ debounce_stacker.py │  ← RPUSH + sleep(2s) + LRANGE + DEL
└──────────┬──────────┘
           │ mensagens concatenadas
           ▼
┌─────────────────────┐
│   agent_graph.py    │  ← LangGraph StateGraph
│   (Gemini → GPT     │     + Tool: encaminhamento
│    fallback)         │     + histórico via Supabase
└──────────┬──────────┘
           │ resposta do agente
           ▼
┌─────────────────────┐
│ chat_history_writer │  ← INSERT em ias_chat_histories_drAntonio
│ .py                 │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ "VAZIO"? → ignora   │  ← Filtro: se resposta = "VAZIO", não envia nada
└──────────┬──────────┘
           │ resposta válida
           ▼
┌─────────────────────┐
│ instagram_sender.py │  ← split por \n → loop:
│                     │     TYPING_ON → wait → send text
│                     │     + POST tracking mensageria
│                     │     + SET dedup key (TTL 30s)
└─────────────────────┘
```

---

## 5. Integrações Externas Mantidas

| Integração | Endpoint | Método | Propósito |
|---|---|---|---|
| **Instagram Graph API** | `https://graph.instagram.com/v22.0/{page_id}/messages` | POST | Enviar mensagens e `TYPING_ON` |
| **Instagram CDN** | URL dinâmica do `attachments[].payload.url` | GET | Baixar áudio/imagem |
| **Supabase Postgres** | Connection string via Supabase client | SQL | Chat History (`ias_chat_histories_drAntonio`) |
| **Redis** | URI do Redis existente | Redis protocol | Debounce, dedup, bloqueio |
| **Encaminhamento** | `https://webhook.leaocorp.com.br/webhook/tool-encaminhamento-unita` | POST | Tool do agente — envia lead para equipe |
| **Tracking Mensageria** | `https://webhook.leaocorp.com.br/webhook/send-by-ia-mensageria` | POST | Registra cada mensagem enviada pela IA (fire-and-forget, `onError: continueRegularOutput`) |

---

## 6. Arquitetura de Módulos (Desacoplada, SRP)

```
execution/
├── modal_app.py               # Definição do App Modal: Image, Secrets, deploy
├── webhook_handler.py         # @modal.fastapi_endpoint — GET (verificação Meta) + POST (ingestão)
├── message_processor.py       # Orquestrador: block_check → receive → debounce → agent → send
├── debounce_stacker.py        # Lógica pura de empilhamento Redis (RPUSH/LRANGE/DEL)
├── block_manager.py           # 3 camadas: is_message_duplicate, is_echo_block, is_handoff_block
├── agent_graph.py             # LangGraph StateGraph + tools + fallback LLM
├── chat_history_writer.py     # Leitura + escrita na tabela ias_chat_histories_drAntonio
├── instagram_receiver.py      # Download mídia CDN → conversão para HumanMessage multimodal
├── instagram_sender.py        # TYPING_ON + split \n + envio sequencial + tracking mensageria
├── redis_client.py            # Wrapper fino sobre Redis (connect, push, pop, get, set, delete)
├── supabase_client.py         # Wrapper fino sobre Supabase/Postgres (insert, query)
├── config.py                  # Constantes, blocklists, TTLs, URLs, IDs de página
└── simulate_webhook.py        # Script de teste: dispara payloads Mock contra endpoint dev

directives/
├── system_prompts/
│   └── dr_antonio_direct.md   # System prompt completo extraído do n8n (~400 linhas)
└── n8n_migration_agent.md     # SOP de referência da migração

tests/
├── test_webhook_handler.py
├── test_debounce_stacker.py
├── test_block_manager.py
├── test_agent_graph.py
├── test_instagram_receiver.py
├── test_instagram_sender.py
├── test_chat_history_writer.py
└── test_message_processor.py
```

### Princípios aplicados:
- **SRP:** Cada arquivo tem uma única responsabilidade. Nenhum ultrapassa 500 linhas.
- **Injeção de dependência:** Redis client, Supabase client e config são injetados — não importados como globais.
- **Wrappers finos:** Libs de terceiros (redis, supabase, httpx) estão atrás de interfaces próprias do projeto.
- **System prompt fora do código:** Carregado via `Path.read_text()` de `directives/system_prompts/`.

---

## 7. Configuração e Credenciais

### 7.1 Variáveis de Ambiente (`.env` local / `modal.Secret` em produção)

```env
# Meta / Instagram
META_VERIFY_TOKEN=<token de verificação do webhook>
META_PAGE_ACCESS_TOKEN=<token de acesso da página>
META_PAGE_ID=17841400753420214

# LLMs
GOOGLE_API_KEY=<chave da API Gemini>
OPENAI_API_KEY=<chave da API OpenAI>

# Supabase / Postgres
SUPABASE_DB_URL=postgresql://user:pass@host:6543/postgres

# Redis
REDIS_URL=redis://user:pass@host:port

# Bloqueio
BLOCKED_SENDER_IDS=8205676472806970,1398645327760860,...
ADMIN_SENDER_IDS=1141940870875707,1253595482403978
```

### 7.2 Modal Secrets
Todas as variáveis acima são cadastradas como `modal.Secret.from_name("agent-ai-secrets")` e injetadas nos containers via decorator `@app.function(secrets=[...])`.

---

## 8. Funcionalidades Fora do Escopo (v1)

| Item | Motivo |
|---|---|
| Resposta automática a **Comments** de posts do Instagram | O workflow n8n tem a rota de comments (`Filter2`), mas é um fluxo separado. Será implementado como v2 após validação do Direct. |
| Dashboard de métricas em tempo real | Fora do escopo da migração. Os dados estarão disponíveis no Supabase para consulta futura. |

---

## 9. Plano de Verificação

### 9.1 Testes Automatizados
- Cada módulo terá testes unitários com mocks para I/O externo (Redis, Supabase, APIs).
- Comando único: `pytest tests/ -v`
- Mocks nomeados (ex: `FakeRedisClient`, `FakeSupabaseClient`) — sem stubs inline.

### 9.2 Teste de Integração Local
1. `modal serve execution/modal_app.py` → sobe endpoint `-dev` com HTTPS.
2. `python execution/simulate_webhook.py --endpoint <url-dev>` → dispara payloads reais da Meta (copiados do `pinData` do n8n) contra o endpoint.
3. Verificar nos logs estruturados: dedup, debounce, chamada ao LLM, resposta enviada.

### 9.3 Teste de Produção (Canary)
1. `modal deploy execution/modal_app.py` → sobe endpoint permanente.
2. Reconfigurar webhook no painel Meta para apontar para a URL do Modal.
3. Enviar mensagem de teste real via Instagram Direct.
4. Validar resposta recebida e registros no Supabase + Redis.

---

## 10. Próxima Etapa

Com esta spec aprovada, o próximo passo é gerar o **Plano de Implementação detalhado** (task-by-task, TDD, bite-sized) seguindo a skill `writing-plans`, decompondo cada módulo em steps de 2-5 minutos com código completo e comandos de teste.

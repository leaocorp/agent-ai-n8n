# Agent AI — Dr. Antonio Instagram Direct

Este projeto é um agente de Inteligência Artificial conversacional desenhado especificamente para o Instagram Direct do Dr. Antonio de Deus. Ele atua como o primeiro nível de atendimento clínico, qualificando leads, respondendo dúvidas frequentes sobre tratamentos e direcionando pacientes para agendamento.

Originalmente construído no n8n, o projeto foi **migrado para uma arquitetura Python Serverless (Modal)** para ganhar velocidade, resiliência, redução extrema de custos de infraestrutura e capacidade de escalar perfeitamente com picos de tráfego.

**Stack:** Python 3.12 · Modal · LangGraph · Gemini Flash (fallback GPT) · Redis · Supabase · FastAPI

---

## Principais Funcionalidades

- **Atendimento Contínuo e Contextualizado**: Lê o histórico do paciente no banco de dados (Supabase) para manter conversas longas e consistentes.
- **Empilhamento de Mensagens (Debounce)**: Se o paciente manda 5 mensagens curtas seguidas ("Oi", "tudo bem?", "queria saber", "sobre o", "implante"), o robô aguarda um breve período (15s) e junta tudo antes de chamar a IA, gerando uma resposta única e coesa e economizando tokens.
- **Detecção de Handoff (Intervenção Humana)**: Se a equipe médica entra na conversa e responde pelo aplicativo do celular (Business Suite), o robô se "cala" silenciosamente por 5 horas, garantindo que não vai interromper o fechamento de um negócio ou o acolhimento médico.
- **Segurança de Falhas (Fallback)**: Usa o modelo Gemini (rápido e barato) como motor principal via LangGraph. Se o Google cair ou sofrer rate limit, automaticamente muda para a OpenAI em tempo de execução.
- **Autoscaling Serverless**: Roda no Modal com custo zero quando ocioso. Se chegarem 100 pacientes ao mesmo tempo, ele sobe 100 containers em milissegundos.

---

## Como funciona o Backend

```text
Instagram DM (Webhook POST)
    │
    ▼
Modal FastAPI (valida assinatura e devolve HTTP 200 em < 100ms para a Meta não travar)
    │
    └─► process_message.spawn()  ← Roda em background, orquestrando tudo assincronamente:
            │
            ├─ BlockManager      → Evita loop de mensagens repetidas e cuida do Handoff (Redis)
            ├─ DebounceStacker   → Empilha mensagens recebidas em até 15s (Redis)
            ├─ ChatHistoryWriter → Puxa o histórico antigo do banco (Supabase)
            ├─ AgentGraph        → Chama a IA Gemini → GPT fallback (LangGraph)
            ├─ ChatHistoryWriter → Salva a resposta da IA no histórico (Supabase)
            └─ InstagramSender   → Exibe "digitando..." (TYPING_ON), quebra em bolhas e envia.
```

**Três camadas de segurança via Redis:**

| Camada | Mecanismo e Chave | TTL (Tempo) | Objetivo |
|--------|-------------------|-------------|----------|
| **Dedup** | `dedup:{mid}` | 30s | Instagram pode enviar o webhook duplicado se a rede oscilar. Impede o robô de responder duas vezes. |
| **Echo (Bot)** | `bot_msg:{message_id}` | 30s | Quando a IA envia uma msg, nós mesmos recebemos o "eco" da Meta. Salvamos o ID exato para ignorar esse eco instantaneamente. |
| **Handoff (Humano)** | `{recipient}_direct_dr_antonio_block` | 5 horas | Se chegar um "eco" da Meta que *não* está salvo acima, é porque a equipe humana usou o aplicativo para responder. O robô se silencia. |

---

## Estrutura de arquivos

```
execution/
├── config.py               # Variáveis de ambiente e constantes
├── redis_client.py         # Wrapper Redis (injeção de dependência)
├── supabase_client.py      # Wrapper Supabase
├── block_manager.py        # 3 camadas de bloqueio
├── debounce_stacker.py     # Empilhamento de mensagens
├── instagram_receiver.py   # Parse de webhooks + download de mídia
├── instagram_sender.py     # TYPING_ON + split por \n + envio
├── chat_history_writer.py  # Leitura/escrita na tabela Supabase
├── agent_graph.py          # LangGraph ReAct (Gemini + fallback GPT)
├── message_processor.py    # Orquestrador principal
├── webhook_handler.py      # Verificação GET + validação POST
├── modal_app.py            # Definição do App Modal (deploy)
└── simulate_webhook.py     # Simulador de webhook para testes locais

directives/
└── system_prompts/
    └── dr_antonio_direct.md   # System prompt do agente

tests/
├── conftest.py             # Fixtures: FakeRedisClient, FakeSupabaseClient
├── test_config.py
├── test_redis_client.py
├── test_block_manager.py
├── test_debounce_stacker.py
├── test_supabase_client.py
├── test_chat_history_writer.py
├── test_instagram_receiver.py
├── test_instagram_sender.py
├── test_agent_graph.py
├── test_message_processor.py
└── test_webhook_handler.py
```

---

## Pré-requisitos

- Python 3.12+
- Conta no [Modal](https://modal.com) com CLI instalada (`pip install modal`)
- Redis (Upstash ou self-hosted)
- Supabase com a tabela `ias_chat_histories_drAntonio`
- Chave da API Google Gemini e OpenAI
- App Meta configurado com webhook do Instagram

---

## Configuração

### 1. Clonar e instalar dependências

```bash
git clone <repo>
cd agent-ai
pip install -r requirements.txt
```

### 2. Criar o `.env`

```bash
cp .env.example .env
```

Preencher todas as variáveis:

```env
# Meta / Instagram
META_VERIFY_TOKEN=seu_token_de_verificacao
META_PAGE_ACCESS_TOKEN=seu_page_access_token
META_PAGE_ID=17841400753420214

# LLMs
GOOGLE_API_KEY=sua_chave_gemini
OPENAI_API_KEY=sua_chave_openai

# Supabase
SUPABASE_DB_URL=postgresql://user:pass@host:6543/postgres

# Redis
REDIS_URL=redis://default:sua_senha@host:porta

# Bloqueio (IDs separados por vírgula, pode ficar vazio)
BLOCKED_SENDER_IDS=
ADMIN_SENDER_IDS=1141940870875707,1253595482403978
```

### 3. Cadastrar segredos no Modal

```bash
modal secret create agent-ai-secrets \
  META_VERIFY_TOKEN="..." \
  META_PAGE_ACCESS_TOKEN="..." \
  META_PAGE_ID="..." \
  GOOGLE_API_KEY="..." \
  OPENAI_API_KEY="..." \
  SUPABASE_DB_URL="..." \
  REDIS_URL="..." \
  BLOCKED_SENDER_IDS="" \
  ADMIN_SENDER_IDS="..."
```

> Alternativamente, crie o secret pelo painel em [modal.com/secrets](https://modal.com/secrets) com o nome `agent-ai-secrets`.

### 4. Criar a tabela no Supabase

Execute no SQL Editor do Supabase:

```sql
CREATE TABLE IF NOT EXISTS ias_chat_histories_drAntonio (
    id         BIGSERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    message    JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_id
    ON ias_chat_histories_drAntonio (session_id);
```

---

## Rodando o projeto

### Testes (sem precisar de credenciais reais)

```bash
# Todos os testes
python -m pytest tests/ -v

# Um módulo específico
python -m pytest tests/test_message_processor.py -v

# Com cobertura (requer pytest-cov)
python -m pytest tests/ --cov=execution --cov-report=term-missing
```

Saída esperada: **40 passed**

---

### Desenvolvimento local (Modal `serve`)

Sobe um endpoint HTTPS temporário com hot-reload. Toda alteração de código é refletida automaticamente.

```bash
modal serve execution/modal_app.py
```

Você verá uma URL como:
```
https://sua-conta--agent-ai-dr-antonio-webhook-get-dev.modal.run  ← GET (verificação)
https://sua-conta--agent-ai-dr-antonio-webhook-post-dev.modal.run ← POST (mensagens)
```

#### Simular uma mensagem de teste

Com o servidor rodando em outro terminal, use o simulador:

```bash
# Mensagem de texto simples
python execution/simulate_webhook.py \
  --endpoint https://sua-conta--agent-ai-dr-antonio-webhook-post-dev.modal.run \
  --text "Olá doutor, quero saber sobre o tratamento"

# Trocar o remetente
python execution/simulate_webhook.py \
  --endpoint https://... \
  --text "Quanto custa a consulta?" \
  --sender 9999999999
```

Os logs estruturados aparecem no terminal do `modal serve` em tempo real.

---

### Configurar o webhook da Meta (teste com ngrok opcional)

Para apontar o Instagram para o endpoint `-dev`:

1. Acesse [developers.facebook.com](https://developers.facebook.com) → seu App → Webhooks
2. Em **Instagram**, edite o webhook:
   - **URL:** `https://sua-conta--agent-ai-dr-antonio-webhook-post-dev.modal.run`
   - **Token de verificação:** o valor de `META_VERIFY_TOKEN` do seu `.env`
3. Assine os campos: `messages`, `messaging_postbacks`

> O GET de verificação é tratado automaticamente pelo `webhook_get` em `modal_app.py`.

---

### Deploy em produção

```bash
modal deploy execution/modal_app.py
```

Isso cria URLs permanentes (sem o sufixo `-dev`). Atualize o webhook no painel da Meta para a nova URL.

Para ver os logs em produção:

```bash
modal app logs agent-ai-dr-antonio
```

---

## Arquitetura de módulos

Cada módulo tem **uma responsabilidade** (SRP) e aceita dependências via construtor (sem globais):

| Módulo | Responsabilidade |
|--------|-----------------|
| `config.py` | Lê `.env` e expõe `Config` imutável (dataclass frozen) |
| `redis_client.py` | Wrapper fino sobre redis-py com logging estruturado |
| `supabase_client.py` | Wrapper fino sobre supabase-py com interface async |
| `block_manager.py` | Dedup + echo block + handoff block via Redis |
| `debounce_stacker.py` | RPUSH → sleep → LRANGE → DEL para empilhar mensagens |
| `instagram_receiver.py` | Parse do JSON do webhook Meta + download de mídia CDN |
| `instagram_sender.py` | Split por `\n` + TYPING_ON + envio sequencial + tracking |
| `chat_history_writer.py` | INSERT/SELECT na tabela Supabase, converte para LangChain messages |
| `agent_graph.py` | Monta o grafo LangGraph com Gemini, fallback GPT, tool encaminhamento |
| `message_processor.py` | Orquestra o pipeline completo: bloqueia → debounce → agente → envia |
| `webhook_handler.py` | Funções puras: verifica token GET e valida body POST |
| `modal_app.py` | Define App Modal, Image, Secrets, endpoints FastAPI e worker |

---

## Variáveis de ambiente — referência completa

| Variável | Obrigatória | Descrição |
|----------|-------------|-----------|
| `META_VERIFY_TOKEN` | Sim | Token de verificação do webhook Meta |
| `META_PAGE_ACCESS_TOKEN` | Sim | Token de acesso da página Instagram |
| `META_PAGE_ID` | Sim | ID numérico da página (padrão: `17841400753420214`) |
| `GOOGLE_API_KEY` | Sim | Chave da API Google para Gemini Flash |
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI para fallback GPT |
| `SUPABASE_DB_URL` | Sim | Connection string PostgreSQL do Supabase |
| `REDIS_URL` | Sim | URI de conexão Redis (`redis://user:pass@host:port`) |
| `BLOCKED_SENDER_IDS` | Não | IDs Instagram bloqueados, separados por vírgula |
| `ADMIN_SENDER_IDS` | Não | IDs de administradores, separados por vírgula |

---

## Fluxo de bloqueio detalhado

```
Mensagem recebida
    │
    ├─ is_echo? ──────────────────► activate_echo_block (3 min)
    │                                save_ai_message + activate_handoff_block (5h)
    │
    ├─ is_sender_blocked? ────────► ignora
    │
    ├─ is_message_duplicate? ─────► ignora (mesmo mid já processado)
    │
    ├─ is_human_takeover_active? ─► salva mensagem humana, não responde
    │
    ├─ push_message() ────────────► is_first?
    │       │
    │       ├─ não: apenas empilha, sai silenciosamente
    │       │
    │       └─ sim: sleep(2s) → collect → salva → agente → envia
    │
    └─ resposta == "VAZIO"? ──────► não envia nada
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'execution'`**
```bash
# Rode sempre a partir da raiz do projeto
cd agent-ai
python -m pytest tests/
```

**Testes falhando com `asyncio` errors**
```bash
# Confirme que pytest.ini tem asyncio_mode = auto
cat pytest.ini
```

**`modal serve` não encontra os segredos**
```bash
# Liste os secrets cadastrados
modal secret list
# Recrie se necessário
modal secret create agent-ai-secrets META_VERIFY_TOKEN="..." ...
```

**Webhook da Meta retorna erro de verificação**
- Confirme que `META_VERIFY_TOKEN` no `.env` é igual ao cadastrado no painel Meta
- Confirme que o endpoint GET está acessível publicamente (use `modal serve`)

**Gemini retorna erro 429 (rate limit)**
- O fallback para GPT-5-mini acontece automaticamente via `.with_fallbacks()`
- Verifique cota no Google AI Studio se ocorrer com frequência

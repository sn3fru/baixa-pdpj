# Devedor360 v2 - Documentacao Tecnica

## Indice

**Como Usar**
1. [Guia Rapido de Uso](#1-guia-rapido-de-uso)
2. [Frontend Web](#2-frontend-web)

**Pipeline (Backend)**
3. [Visao Geral do Pipeline](#3-visao-geral-do-pipeline)
4. [Arquitetura](#4-arquitetura)
5. [Estrutura de Arquivos](#5-estrutura-de-arquivos)
6. [Configuracao (config.py)](#6-configuracao)
7. [Utilitarios (utils.py)](#7-utilitarios)
8. [Gerenciador de Cache (cache_manager.py)](#8-gerenciador-de-cache)
9. [Cliente API PDPJ (api_client.py)](#9-cliente-api-pdpj)
10. [Step 1 - Coleta Unificada (s1_coleta_unificada.py)](#10-step-1---coleta-unificada)
11. [Step 2 - Organizacao de Processos (s2_organiza_processos.py)](#11-step-2---organizacao-de-processos)
12. [Step 3 - Visao Devedor (s3_visao_devedor.py)](#12-step-3---visao-devedor)
13. [Pipeline (pipeline.py)](#13-pipeline)
14. [Estrutura de Saida (outputs/)](#14-estrutura-de-saida)
15. [APIs Externas](#15-apis-externas)
16. [Integracao com Frontend](#16-integracao-com-frontend)
17. [Referencia de Eventos (Callbacks)](#17-referencia-de-eventos)
18. [Guia de Impacto de Alteracoes](#18-guia-de-impacto-de-alteracoes)
19. [Sistema de Flags (flags.py)](#19-sistema-de-flags)
20. [Homonimos (Resolucao de Ambiguidades)](#20-homonimos)
21. [Deployment (Heroku / Producao)](#21-deployment)

---

## 1. Guia Rapido de Uso

### Instalacao

```bash
cd devedor360-v2
pip install -r requirements.txt
```

### Configurar tokens

Edite o arquivo `.env` e insira seus tokens PDPJ:

```
PDPJ_TOKENS=token1,token2,token3
```

### Iniciar o servidor web

```bash
python web_app.py
# Acesse http://localhost:8000
```

Ou, se preferir rodar diretamente via linha de comando (sem frontend):

```bash
python pipeline.py                     # Executa S1+S2+S3 completo
python pipeline.py --steps s2 s3       # Executa apenas S2 e S3
python pipeline.py --processos 123 456 # Busca processos especificos
```

### Passo a passo pela interface web

1. **Upload** (`/upload`) - Suba a planilha Excel com os devedores. O sistema valida as colunas e mostra preview.
2. **Configuracao** (`/config`) - Revise limites de busca, tipos de busca (documento/nome/filiais), workers, etc. Alteracoes sao salvas automaticamente.
3. **Pipeline S1** (`/pipeline`) - Selecione S1 e clique "Executar Pipeline". Acompanhe o progresso em tempo real no Kanban animado. Voce pode navegar para outras paginas e o progresso continua no sidebar.
4. **Homonimos** (`/homonimos`) - **Importante se busca por nome esta habilitada.** Quando nomes retornam multiplos documentos (CPFs/CNPJs), o analista seleciona quais sao do devedor correto. Individuos nao resolvidos serao pulados no S2.
5. **Pipeline S2+S3** (`/pipeline`) - Execute S2 e S3 para consolidar processos e gerar a visao devedor.
6. **Resultados** - Explore os dados nas telas:
   - `/individuos` - Cada pessoa/empresa coletada (com status de homonimos)
   - `/processos` - Tabela completa com paginacao server-side, filtro, sort, export
   - `/devedores` - Visao agregada por entidade com graficos
   - `/arquivos` - Navegador de pastas e arquivos gerados
7. **Download** - Apos pipeline concluido, baixe o ZIP com todos os resultados (especialmente importante no Heroku, onde dados sao efemeros).
8. **Ajuda** (`/ajuda`) - Guia detalhado com FAQ e referencia de flags

### Formato da planilha de entrada

| Coluna | Obrigatorio | Descricao | Exemplo |
|--------|-------------|-----------|---------|
| `nr_documento` | Sim* | CPF (11 digitos) ou CNPJ (14 digitos), so numeros | 12345678909 |
| `nome_estoque` | Sim* | Nome completo da pessoa ou empresa | JOAO DA SILVA |
| `posicao` | Nao | ID/ranking (auto-gerado se ausente) | 1 |
| `tp_documento` | Nao | CPF ou CNPJ (auto-detectado se ausente) | CPF |

*Pelo menos `nr_documento` ou `nome_estoque` deve existir. Aliases aceitos: `documento`, `cpf`, `cnpj`, `cpf_cnpj`, `nome`, `nome_parte`.

---

## 2. Frontend Web

### Stack

| Tecnologia | Versao | Funcao |
|-----------|--------|--------|
| **FastAPI** | >=0.109 | Backend HTTP + SSE |
| **Jinja2** | >=3.1 | Templates HTML server-side |
| **HTMX** | 1.9.12 | Interatividade sem framework JS |
| **Alpine.js** | 3.14 | Reatividade local (forms, modals) |
| **Tailwind CSS** | CDN | Estilizacao utility-first |
| **Tabulator** | 6.2 | Tabelas com filtro/sort/export |
| **SheetJS** | 0.20 | Export Excel client-side |
| **ECharts** | 5.5 | Graficos (pie, bar, etc.) |

**Zero npm. Zero build step. Tudo via CDN.**

### Estrutura de Arquivos (web/)

```
devedor360-v2/
  web_app.py              # Entry point: uvicorn web_app:app
  flags.py                # Registry de flags extensivel
  Procfile                # Heroku: web: uvicorn web_app:app --host 0.0.0.0 --port $PORT
  runtime.txt             # Heroku: python-3.12.8
  .env.example            # Template de configuracao (copiar para .env)
  web/
    __init__.py            # Cria FastAPI app, monta routers
    state.py               # RunInfo + AppState (eventos em lista append-only para SSE replay)
    routes/
      pages.py             # Rotas de paginas HTML (10 paginas)
      api_config.py        # GET/POST /api/config (auto-save)
      api_pipeline.py      # POST /api/executar, GET /api/status/stream (SSE index-based)
      api_data.py          # Upload, dados, homonimos, docs, arquivos, ZIP, ping
    templates/
      base.html            # Layout + sidebar + CDN imports + placeholder pipeline status
      pages/
        dashboard.html     # KPIs + graficos + historico + alerta homonimos + aviso Heroku
        upload.html        # Upload + validacao + preview Tabulator
        config.html        # Parametros editaveis com auto-save (debounce 800ms)
        pipeline.html      # Kanban animado + SSE resiliente + timer + ZIP download
        individuos.html    # Tabela S1 com coluna de homonimos
        homonimos.html     # Resolucao de ambiguidades por nome (cards expandiveis)
        processos.html     # Tabela S2 com paginacao server-side remota
        devedores.html     # Tabela S3 com paginacao server-side + chart top 10
        arquivos.html      # File browser navegavel
        ajuda.html         # Guia de uso + FAQ
    static/
      app.css              # Overrides Tabulator dark + animacoes Kanban (glow, flash, stripes, pulse, pop)
      app.js               # Pipeline status sidebar + keep-alive Heroku + helpers
```

### Paginas

| Pagina | URL | Descricao |
|--------|-----|-----------|
| Dashboard | `/` | KPIs, graficos de origens/classificacao, historico, alerta de homonimos pendentes |
| Upload | `/upload` | Upload de planilha, validacao de colunas, preview editavel |
| Configuracao | `/config` | Todos os parametros do `.env` editaveis com **auto-save** (sem botao salvar), flags listadas |
| Pipeline | `/pipeline` | Selecao de steps, **Kanban visual animado** com metricas live, progresso SSE resiliente, log colorido, timer, download ZIP |
| Individuos | `/individuos` | Tabela de individuos com modal de detalhes e coluna de status de homonimos |
| **Homonimos** | `/homonimos` | **Resolucao de ambiguidades por nome** - analista seleciona quais documentos sao do devedor correto |
| Processos | `/processos` | Tabela S2 com **paginacao server-side**, filtro, sort, export Excel/CSV |
| Devedores | `/devedores` | Visao devedor S3 com **paginacao server-side**, chart top 10, export |
| Arquivos | `/arquivos` | File browser navegavel |
| Ajuda | `/ajuda` | Passo a passo, formato planilha, FAQ |

### Endpoints da API

**Configuracao:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/config` | Retorna configuracao atual (tokens mascarados) |
| POST | `/api/config` | Atualiza `.env` com novos valores (chamado pelo auto-save do frontend) |
| GET | `/api/config/validate` | Valida config e retorna erros |

**Upload:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | `/api/upload` | Recebe Excel (.xls/.xlsx), valida, normaliza para .xlsx, retorna preview |
| GET | `/api/upload/preview` | Preview da planilha de entrada atual (tenta openpyxl, fallback xlrd) |

**Pipeline:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | `/api/executar` | Inicia pipeline em background thread |
| GET | `/api/status` | Status atual do pipeline (running, idle, etc.) |
| GET | `/api/status/stream?since=N` | **SSE com index-based replay** - reconecta sem perder eventos |
| GET | `/api/history` | Historico de execucoes |

**Dados:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/stats` | Estatisticas gerais (dashboard) + contagem de homonimos pendentes |
| GET | `/api/individuos` | Lista individuos processados (inclui status de homonimos) |
| GET | `/api/individuos/{id}` | Detalhes de um individuo |
| GET | `/api/processos/meta` | Metadados da tabela S2 (colunas, total) - sem dados |
| GET | `/api/processos/filter?page=&size=&sort=&dir=&q=` | **Paginacao server-side** para Tabulator remoto |
| GET | `/api/devedores/meta` | Metadados da tabela S3 (colunas, total) - sem dados |
| GET | `/api/devedores/filter?page=&size=&sort=&dir=&q=` | **Paginacao server-side** para Tabulator remoto |
| GET | `/api/arquivos?path=` | Lista/le diretorio ou arquivo |
| GET | `/api/arquivos/download?path=` | Download de arquivo |
| GET | `/api/docs` | Documentacao tecnica renderizada em HTML |

**Homonimos:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/homonimos` | Lista individuos com homonimos (pendentes, resolvidos, unicos) |
| GET | `/api/homonimos/{id}` | Detalhe completo dos homonimos de um individuo |
| POST | `/api/homonimos/{id}/resolver` | Analista marca documentos corretos `{selecoes: {doc: true/false}}` |
| POST | `/api/homonimos/{id}/resetar` | Volta resolucao para "pendente" |

**Utilidades / Heroku:**

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| GET | `/api/download-zip` | Stream ZIP com todos os outputs (dados, Excels, caches) |
| GET | `/api/download-zip/info` | Info do ZIP (qtd arquivos, tamanho total) |
| GET | `/api/ping` | Health check - usado pelo keep-alive do frontend |

### Tabelas interativas

Todas as tabelas de dados usam **Tabulator 6.2** e oferecem:
- Filtro por coluna (campo no cabecalho de cada coluna)
- Ordenacao crescente/decrescente (clique no titulo)
- **Paginacao server-side** (processos e devedores) com seletor de tamanho de pagina
- Export Excel (.xlsx) com dados filtrados
- Export CSV com dados filtrados
- Botao "Baixar Original" para o arquivo gerado pelo pipeline
- Colunas arrastáveis e redimensionaveis
- **Tooltips** no header e celulas (texto completo ao passar o mouse)
- Formatacao automatica de moeda (BRL) e flags

**Paginacao server-side (processos e devedores):**
- O frontend faz `fetch` para `/api/processos/filter` ou `/api/devedores/filter` com `page`, `size`, `sort`, `dir`, `q` (JSON de filtros)
- O backend usa `_DFCache` (cache thread-safe de DataFrames lidos de Excel, invalida por mtime) e `_paginate_df` (filtro case-insensitive, sort com deteccao automatica de tipo numerico, paginacao)
- Retorna `{ last_page, data, total, total_filtered }` no formato esperado pelo Tabulator remoto

### Features de UX especiais

**Auto-save na configuracao:** Toda alteracao (input text, checkbox, textarea) e salva automaticamente apos 800ms de debounce (1500ms para textarea de tokens). Indicador visual de status (salvando/salvo/erro) no header da pagina.

**Pipeline Kanban animado:** Cards S1/S2/S3 com:
- Barra de progresso animada (progress-stripes CSS)
- Metricas live (processos, detalhes, paginas) com animacao `num-pop`
- Nome do individuo sendo processado (pulsando)
- Efeito glow no card em execucao, flash ao completar
- Timer global (elapsed time) atualizado a cada segundo
- Banner "Pipeline Concluido" com metricas agregadas e botao ZIP
- Log de eventos colorido com dots e filtro de detalhes

**SSE resiliente (index-based):**
- Eventos do pipeline sao armazenados em lista append-only no `AppState` (nao mais em queue)
- O frontend conecta via `EventSource` a `/api/status/stream?since=N`
- A cada evento recebido, atualiza `sseIndex` com `evt._idx`
- Se a conexao cai, reconecta automaticamente enviando o ultimo indice — sem perder eventos
- O sidebar mostra status global do pipeline em todas as paginas (polling a cada 3s)

**Homonimos:** Ver [secao 20](#20-homonimos) para detalhes completos.

---

## 3. Visao Geral do Pipeline

O Devedor360 e um pipeline ETL que pesquisa, coleta e consolida informacoes de processos judiciais a partir da API PDPJ (Plataforma Digital do Poder Judiciario), organizando-as por individuo/entidade para gerar uma visao 360 graus do perfil processual de cada devedor.

### Pipeline em 3 Steps

```
ENTRADA                    STEP 1                      STEP 2                    STEP 3
(Excel)              Coleta Unificada           Organiza Processos          Visao Devedor
                                                
 posicao  ─┐     ┌─ Busca por Documento        Extrai campos             Agrega por
 nome     ─┤     ├─ Busca por Filiais    ───>  Deduplica           ───>  Entity ID
 documento ─┘     ├─ Busca por Nome             Corrige SELIC             (raiz CNPJ
                  └─ Busca por Processo         Exporta Excel              ou CPF)
                                                                          Exporta Excel
 
 outputs/{id}/                                saida_processos_            visao_devedor_
   metadata.json                              consolidados_*.xlsx         *.xlsx
   processos_unicos.json
   detalhes/*.json
   por_documento/pages/*.json
   por_nome/*/pages/*.json
   por_filial/{cnpj}/pages/*.json
```

### Principios de Design

- **Modular**: cada step e uma classe independente que pode ser instanciada e executada isoladamente
- **Injetavel**: toda configuracao passa pela classe `Config`, que aceita overrides via dict/JSON
- **Frontend-ready**: todas as classes aceitam `progress_callback` para emitir eventos em tempo real
- **Thread-safe**: coleta de detalhes usa worker pool; caches e stats protegidos por locks
- **Resiliente**: retries com backoff exponencial, gestao de HTTP 429, cache de resultados

---

## 4. Arquitetura

### Grafo de Dependencias

```
                    .env
                     │
                 config.py          (Config, constantes)
                  /     \
            utils.py   cache_manager.py   (funcoes puras)   (CacheManager)
               |         /       \
          api_client.py           |        (PDPJClient)
               \                  |
        s1_coleta_unificada.py    |        (ColetaUnificada, GlobalStats)
                 \                |
          s2_organiza_processos.py         (OrganizadorProcessos)
                      \
              s3_visao_devedor.py           (VisaoDevedor)
                       \
                    pipeline.py             (Pipeline - orquestrador)
```

### Camadas de Uso

Cada modulo expoe 3 interfaces:

| Camada | Alvo | Exemplo |
|--------|------|---------|
| **Classe** | Frontend / integracao | `ColetaUnificada(config, callback).executar()` |
| **Funcao** | Scripts / notebooks | `executar_coleta(config)` |
| **CLI** | Terminal | `python s1_coleta_unificada.py` |

---

## 5. Estrutura de Arquivos

```
devedor360-v2/
├── .env                          # Variaveis de ambiente (tokens, parametros)
├── .gitignore                    # Ignora .env, outputs, caches
├── requirements.txt              # Dependencias Python
├── DOCUMENTACAO_TECNICA.md       # Este documento
├── PLANO_REFATORACAO.md          # Historico de planejamento
│
├── config.py                     # Configuracao centralizada + classe Config
├── utils.py                      # Funcoes puras (documentos, datas, SELIC, classificacao)
├── cache_manager.py              # Gerenciamento de caches thread-safe
├── api_client.py                 # Cliente HTTP para API PDPJ
│
├── s1_coleta_unificada.py        # Step 1: coleta de dados
├── s2_organiza_processos.py      # Step 2: extrai campos, deduplica, Excel
├── s3_visao_devedor.py           # Step 3: agrega por entidade, Excel formatado
└── pipeline.py                   # Orquestrador s1 → s2 → s3
```

---

## 6. Configuracao

**Arquivo:** `config.py` (217 linhas)

### 4.1 Carregamento do .env

Na importacao do modulo, o `.env` e carregado automaticamente via `python-dotenv`. Se a lib nao estiver instalada, um parser fallback le o arquivo manualmente.

### 4.2 Constantes de Modulo

Todas as constantes sao definidas a nivel de modulo lendo `os.getenv()` com defaults seguros:

| Constante | Tipo | Default | Descricao |
|-----------|------|---------|-----------|
| `TOKENS` | list[str] | `[]` | Tokens JWT separados por virgula |
| `BASE_URL` | str | `https://api-processo-integracao...` | URL base da API PDPJ |
| `TRIBUNAL` | str | `TJPE` | Sigla do tribunal |
| `ID_CLASSE` | str | `1116` | Codigo da classe (1116 = Execucao Fiscal) |
| `INPUT_FILE` | str | `Recife_nomes_partes_estoque.xlsx` | Planilha de entrada |
| `OUTPUT_DIR` | str | `outputs` | Diretorio de saida |
| `MAX_POR_PAGINA` | int | `100` | Resultados por pagina da API |
| `MAX_PAGINAS_POR_CASO` | int | `100` | Max paginas por busca |
| `MAX_PROCESSOS_TOTAIS_POR_CASO` | int | `1000` | Teto de processos por busca |
| `MAX_PROCESSOS_ALERTA_API` | int | `5000` | Limiar para "caso gigante" |
| `MAX_PROCESSOS_PER_DOC` | int | `1` | Limite por categoria (EF/PA/OU) por individuo |
| `MAX_PROCESSOS_PER_CNPJ_ROOT` | int | `2` | Limite total por individuo |
| `MAX_FILIAIS` | int | `1` | Quantas filiais CNPJ iterar |
| `DOWNLOAD_DETALHES` | bool | `false` | Se baixa capas individuais |
| `ENABLE_BUSCA_DOCUMENTO` | bool | `true` | Ativa busca por CPF/CNPJ |
| `ENABLE_BUSCA_NOME` | bool | `true` | Ativa busca por nome |
| `ENABLE_BUSCA_FILIAL` | bool | `true` | Ativa iteracao de filiais |
| `WORKERS_PER_TOKEN` | int | `1` | Threads de download por token |
| `DEBUG` | bool | `false` | Modo verboso |
| `DASHBOARD_ENABLED` | bool | `true` | Dashboard em tempo real |
| `DASHBOARD_UPDATE_INTERVAL` | int | `10` | Segundos entre atualizacoes |
| `FILTRO_MUNICIPIO` | str | `DISTRITO FEDERAL X` | Filtro de municipio |
| `BLACKLIST` | set | `{"9999"}` | Documentos a ignorar |
| `CACHE_DIR` | str | `.` | Diretorio dos caches |

### 4.3 Classe Config

```python
class Config:
    def __init__(self, **kw)            # Cria com overrides opcionais
    def to_dict(self) -> dict           # Serializa (JSON-safe, sets → listas)
    @classmethod from_dict(cls, d)      # Cria a partir de dict
    @classmethod from_env(cls)          # Cria usando .env (defaults)
    def validar(self) -> list           # Lista de erros (vazia = OK)
    def imprimir(self)                  # Exibe resumo no console
```

**Contrato da validacao:** retorna lista de strings. Validacoes:
- Pelo menos 1 token (cada token > 50 caracteres)
- `base_url` nao vazia
- `input_file` nao vazio

**Atributos derivados:**
- `num_workers`: `min(len(tokens) * workers_per_token, 8)` — maximo 8 workers

### 4.4 Helpers Internos

| Funcao | Assinatura | Retorno |
|--------|-----------|---------|
| `_bool` | `(val) -> bool` | Converte "true"/"1"/"yes"/"sim" para True |
| `_int` | `(val, default) -> int` | Parse seguro de inteiro |

---

## 7. Utilitarios

**Arquivo:** `utils.py` (571 linhas)

Funcoes puras sem estado. Nenhuma depende de config ou cache (exceto SELIC que aceita cache opcional).

### 5.1 Validacao e Normalizacao de Documentos

| Funcao | Entrada | Saida | Descricao |
|--------|---------|-------|-----------|
| `normalizar_documento(str)` | `"123.456.789-09"` | `"12345678909"` | Remove nao-digitos, padleft 11 ou 14 |
| `validar_cpf(str)` | `"12345678909"` | `bool` | Valida digitos verificadores |
| `validar_cnpj(str)` | `"12345678000199"` | `bool` | Valida digitos verificadores |
| `gerar_cnpj_completo(root, branch)` | `("12345678", "0002")` | `"12345678000299"` | Calcula DVs automaticamente |
| `obter_raiz_cnpj(doc)` | `"12345678000199"` | `"12345678"` | Primeiros 8 digitos (CNPJ) ou `""` |
| `identificar_tipo_documento(str)` | qualquer | `"CPF"` / `"CNPJ"` / `""` | Normaliza + valida + classifica |

**Logica de `normalizar_documento`:**
1. Remove tudo que nao e digito
2. Se <= 11 digitos: padleft com zeros ate 11 (CPF)
3. Se > 14 digitos: pega os ultimos 14
4. Senao: padleft ate 14 (CNPJ)

**Logica de `gerar_cnpj_completo`:**
1. Concatena raiz (8) + filial (4) = 12 digitos
2. Calcula 1o DV com pesos [5,4,3,2,9,8,7,6,5,4,3,2]
3. Calcula 2o DV com pesos [6,5,4,3,2,9,8,7,6,5,4,3,2]
4. Retorna string de 14 digitos

### 5.2 Formatacao de Datas

| Funcao | Entrada | Saida | Descricao |
|--------|---------|-------|-----------|
| `parse_iso_date(str)` | ISO string | `datetime` ou `None` | Parse robusto com 3 tentativas |
| `formatar_data_iso(str)` | ISO string | `"DD/MM/YYYY"` | ISO → formato BR |
| `parse_date(str)` | ISO ou DD/MM/YYYY | `datetime` | Tenta ambos os formatos |
| `obter_ano_processo(str)` | CNJ | `int` | Extrai ano do 2o segmento |
| `calcular_data_ajuizamento(dist, prim, cnj)` | 3 strings | `"DD/MM/YYYY"` | Logica inteligente de data |

**Logica de `parse_iso_date` (3 tentativas):**
1. `datetime.fromisoformat()`
2. Regex para microsegundos truncados + normalize para 6 digitos
3. `strptime` descartando parte fracionaria

**Logica de `calcular_data_ajuizamento`:**
1. Extrai ano do CNJ (2o segmento apos `.`)
2. Se data_distribuicao.year == ano → usa data_distribuicao
3. Se data_primeiro_doc.year == ano → usa data_primeiro_doc
4. Fallback: `01/07/{ano}` (meio do ano)

### 5.3 SELIC (Correcao Monetaria)

| Funcao | Entrada | Saida | Descricao |
|--------|---------|-------|-----------|
| `somar_selic_periodo(ini, fim, cache?)` | `"DD/MM/YYYY"` x2 | `float` | Soma taxa SELIC via API BCB |
| `corrigir_valor_com_selic(valor, data, cache?)` | float + str | `float` | Aplica correcao monetaria |

**Fluxo de `somar_selic_periodo`:**
1. Arredonda data_ini para dia 1 do mes
2. Constroi chave de cache: `"{ini_arredondado}_{fim}"`
3. Se cache_manager fornecido → consulta cache
4. Se nao cacheado → GET na API BCB (serie 4390)
5. Soma todos os valores da resposta JSON
6. Salva no cache e retorna

**Fluxo de `corrigir_valor_com_selic`:**
1. Converte valor e data
2. Define periodo: `data_ajuiz` ate `1o dia do mes atual - 1 dia`
3. Se data_ajuiz >= fim_periodo → retorna valor original
4. Calcula: `valor * (1 + selic_acumulada / 100)`

### 5.4 Manipulacao de Partes

| Funcao | Entrada | Saida |
|--------|---------|-------|
| `montar_partes_string(list[dict])` | Lista de partes da API | `"ATIVO X PASSIVO e OUTROS (N)"` |

**Keywords de polo ativo:** AUTOR, APELANTE, EXEQUENTE, REQUERENTE, ATIVO
**Keywords de polo passivo:** REU, RÉU, APELADO, EXECUTADO, REQUERIDO, PASSIVO

### 5.5 Classificacao de Processos

| Funcao | Entrada | Saida | Criterio |
|--------|---------|-------|----------|
| `is_execucao_fiscal(item)` | dict processo | `bool` | tramitacoes[].classe[].codigo == 1116 |
| `is_polo_ativo(item, doc)` | dict + doc normalizado | `bool` | doc no polo ATIVO das partes |
| `is_polo_passivo_nao_exec_fiscal(tram, doc)` | dict tramitacao + doc | `0`/`1` | doc no polo PASSIVO e classe != 1116 |
| `is_justica_trabalho(cnj)` | string CNJ | `bool` | 5o segmento do CNJ == "5" |
| `extrair_flag_extinto(detalhe)` | dict detalhe | `0`/`1` | Busca 25 termos de extincao nos movimentos |

**`EXTINCAO_TERMS`** (25 termos, case-insensitive): lista completa de descricoes de movimentos que indicam extincao do processo (satisfacao, cancelamento, desistencia, prescricao, etc.)

**Logica de `extrair_flag_extinto`:**
1. Para cada tramitacao:
   - Para cada movimento: verifica descricao contra `EXTINCAO_TERMS`
   - Verifica `ultimoMovimento.descricao` separadamente
2. Retorna 1 se qualquer match, 0 caso contrario

### 5.6 Priorizacao

```python
def priorizar_processos(lista_conteudo, doc_normalizado=None) -> (ef, pa, ou)
```

Separa processos em 3 listas ordenadas por prioridade:
1. **exec_fiscal** (EF): classe 1116
2. **polo_ativo** (PA): documento no polo ativo (so se `doc` fornecido)
3. **outros** (OU): todos os demais

Cada lista e deduplicada mantendo a ordem original.

### 5.7 Extracao de Documentos

```python
def extrair_documentos_dos_processos(processos) -> {doc_normalizado: [itens]}
```

Para cada processo, varre `tramitacoes[].partes[].documentosPrincipais[].numero`, normaliza, valida (CPF ou CNPJ valido) e agrupa. Usado pelo Step 1 na busca por nome para identificar quais documentos estao associados aos processos encontrados.

### 5.8 Extracao de Campos

| Funcao | Fonte | Retorno | Uso |
|--------|-------|---------|-----|
| `extrair_campos_processo(item, doc, raiz, filial, cache?)` | JSON detalhe | `list[dict]` (1 por tramitacao) | Step 2 (com detalhes) |
| `extrair_campos_pagina(item, doc)` | JSON page content item | `dict` | Step 2 (sem detalhes) |

**Campos extraidos por `extrair_campos_processo`:**

| Campo | Tipo | Origem |
|-------|------|--------|
| Numero CNJ | str | `item.numeroProcesso` |
| Valor Acao | float | `tram.valorAcao` |
| Valor Corrigido | float | Calculado via `corrigir_valor_com_selic()` |
| Data Ajuizamento | str | Calculado via `calcular_data_ajuizamento()` |
| Data Primeiro Ajuizamento | str | `min(dataHoraPrimeiroAjuizamento, min(documentos[].dataHoraJuntada))` |
| Data Ultimo Movimento | str | `item.dataHoraUltimoMovimento` |
| Classe | str | `tram.classe[0].descricao (codigo)` |
| Classe Hierarquia | str | `tram.classe[0].hierarquia` |
| Assunto | str | `tram.assunto[0].descricao (codigo)` |
| Assunto Hierarquia | str | `tram.assunto[0].hierarquia` |
| Partes | str | Via `montar_partes_string()` |
| Orgao Julgador | str | `siglaTribunal - orgaoJulgador.nome` |
| Instancia | str | `tram.instancia` |
| Tribunal | str | `tram.tribunal.nome` |
| CNPJ Completo | str | Parametro `doc_pasta` |
| CNPJ Raiz | str | Parametro `raiz_pasta` |
| CNPJ Filial | str | Parametro `filial_pasta` |
| Flag Extinto | int | Via `extrair_flag_extinto()` |
| Flag Reu | int | Via `is_polo_passivo_nao_exec_fiscal()` |

Se o processo nao tem tramitacoes, gera 1 registro base com campos vazios.

**Campos extraidos por `extrair_campos_pagina` (subset):**
Numero CNJ, ID Processo, Tribunal, Data Atualizacao, Data Ultimo Movimento Global, CNPJ Completo, Data Ajuizamento, Valor Acao, Classe, Assunto, Orgao Julgador, Partes, Flag Extinto.

### 5.9 Utilidades de Arquivo

| Funcao | Descricao |
|--------|-----------|
| `deletar_pastas_vazias(root)` | Remove pastas vazias recursivamente (nao remove root). Retorna contagem. |
| `pasta_so_tem_paginas(pasta)` | True se so contem `page_*.json` (nenhum detalhe baixado). |

---

## 8. Gerenciador de Cache

**Arquivo:** `cache_manager.py` (221 linhas)

### 6.1 Classe CacheManager

```python
class CacheManager:
    def __init__(self, cache_dir=".", debug=False, **file_overrides)
```

**Inicializacao:** carrega todos os caches do disco para memoria. Thread-safe via `threading.Lock`.

**Arquivos de cache (nomes configuraveis):**

| Chave interna | Arquivo default | Tipo em memoria | Conteudo |
|---------------|-----------------|-----------------|----------|
| `processos_404` | `processos_404.json` | `set` | Processos que retornaram 404 |
| `filiais_inex` | `filiais_inexistentes.json` | `set` | CNPJs de filiais sem processos |
| `casos_gigantes` | `casos_gigantes.json` | `dict` | `{doc: total_processos}` para >5000 |
| `cache_procs` | `cache_processos_completos.json` | `dict` | `{numero: status}` (ex: "ok") |
| `selic` | `selic_cache.json` | `dict` | `{periodo: taxa_acumulada}` |
| `log_det` | `log_detalhado_execucao.json` | arquivo | `{doc: {info + timestamp}}` |
| `log_erros` | `log_erros_detalhado.json` | arquivo | `[{ts, proc, doc, tipo, det}]` (max 2000) |

### 6.2 Metodos Publicos

**Processos 404:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `is_processo_404` | `(proc: str) -> bool` | Verifica + incrementa hit counter |
| `add_processo_404` | `(proc: str)` | Adiciona ao set |

**Filiais inexistentes:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `is_filial_inexistente` | `(cnpj: str) -> bool` | Verifica no set |
| `add_filial_inexistente` | `(cnpj: str)` | Adiciona ao set |

**Casos gigantes:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `is_caso_gigante` | `(doc: str) -> bool` | Verifica no dict |
| `add_caso_gigante` | `(doc: str, total: int)` | Salva doc + total |

**Cache de processos:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `is_processo_processado` | `(proc: str) -> bool` | Verifica no dict |
| `get_status_processo` | `(proc: str) -> str` | Retorna status ou `""` |
| `add_processo` | `(proc: str, status: str)` | Salva `{proc: status}` |
| `separar_processados` | `(lista: list) -> (ja, falta)` | Divide lista em processados e pendentes |

**SELIC:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `get_selic` | `(key: str) -> float/None` | Retorna valor cacheado ou None |
| `set_selic` | `(key: str, valor: float)` | Salva no dict |

**Logs:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `log_erro` | `(proc, doc, tipo, detalhes)` | Append ao JSON de erros (max 2000 entradas) |
| `log_detalhado` | `(doc, info_dict)` | Upsert no JSON de log detalhado |

**Persistencia e estatisticas:**

| Metodo | Assinatura | Comportamento |
|--------|-----------|---------------|
| `save_all()` | - | Salva todos os 5 caches em disco |
| `get_stats()` | `-> dict` | Retorna contagens + hits |

### 6.3 Formato get_stats()

```python
{
    "processos_404": 150,
    "filiais_inexistentes": 23,
    "casos_gigantes": 2,
    "cache_processos": 5400,
    "selic_cache": 48,
    "hits": {"p404": 312, "filial": 0, "proc": 0, "selic": 156}
}
```

---

## 9. Cliente API PDPJ

**Arquivo:** `api_client.py` (342 linhas)

### 7.1 Classe PDPJClient

```python
class PDPJClient:
    def __init__(self, tokens, base_url, tribunal="TJPE", id_classe="1116",
                 max_por_pagina=100, max_retries=5, backoff_base=1.0, debug=False)
    
    @classmethod from_config(cls, config) -> PDPJClient
```

### 7.2 Gerenciamento de Tokens

- **Round-robin:** `_next_token()` incrementa `_token_idx` sob lock e retorna `tokens[idx % len(tokens)]`
- **Headers:** `{"Authorization": "Bearer {token}", "Accept": "application/json"}`

### 7.3 HTTP Core - get()

```python
def get(self, url, params=None, token=None, timeout=60) -> requests.Response
```

**Fluxo de retries (max 5 tentativas):**

```
Para cada tentativa:
  1. Espera se _global_429_lock esta bloqueado (max 120s)
  2. Incrementa _stats["requests"]
  3. Monta headers com proximo token
  4. Faz requests.get()
  5. Se 429:
     - Incrementa _stats["errors_429"]
     - Calcula wait = max(Retry-After header, 10 * (attempt+1))
     - Bloqueia _global_429_lock para TODAS as threads
     - sleep(wait)
     - Desbloqueia _global_429_lock
     - retry
  6. Se 500/502/503/504:
     - Incrementa _stats["retries"]
     - sleep(backoff_base * 2^attempt + random(0,1))
     - retry
  7. Se 200 ou outro: retorna Response
  8. Se ConnectionError/Timeout:
     - Incrementa errors_other e retries
     - Backoff exponencial
     - retry
  
  Apos max_retries: raise ConnectionError
```

**Nota sobre 429:** o `_global_429_lock` e um `threading.Event`. Quando uma thread recebe 429, TODAS as threads param de fazer requests ate o cooldown terminar. Isso evita sobrecarga.

### 7.4 buscar_por_documento()

```python
def buscar_por_documento(self, documento, max_paginas=100, max_processos=1000,
                          id_classe=None, save_dir=None, callback=None) -> dict
```

**Parametros da API:**
- `cpfCnpjParte`: documento
- `siglaTribunal`: tribunal configurado
- `tamanhoPagina`: max_por_pagina
- `idClasse`: (opcional) filtro de classe
- `searchAfter`: cursor de paginacao (a partir da 2a pagina)

**Retorno:**
```python
{
    "processos": [item1, item2, ...],   # lista de dicts da API
    "total_api": 1234,                   # totalRegistros da 1a pagina
    "paginas": 5,                        # quantas paginas foram lidas
    "gigante": False                     # True se total_api > 5000
}
```

**Paginacao cursor-based:**
1. Faz GET da pagina 1
2. Extrai `searchAfter` do response (campo `searchAfter` ou `content[-1].sort`)
3. Adiciona `searchAfter` como param na proxima pagina
4. Para quando: content vazio, searchAfter ausente, max_paginas, ou max_processos atingido

**Cache de paginas:** se `save_dir` fornecido, salva `page_N.json` em disco. Na proxima execucao, carrega do disco sem chamar a API.

### 7.5 buscar_por_nome()

```python
def buscar_por_nome(self, nome, max_paginas=100, max_processos=1000,
                     save_dir=None, callback=None) -> dict
```

Faz **2 buscas separadas** e mergeia (replicando o comportamento do `s1-nomes-recife.py` original):
1. Parametro `nomeParte` → salva em `{save_dir}/nomeParte/page_N.json`
2. Parametro `outroNomeParte` → salva em `{save_dir}/outroNomeParte/page_N.json`

**Parametros da API (por busca):**
- `nomeParte` ou `outroNomeParte`: nome buscado
- `tribunal`: sigla do tribunal configurado (ex: `TJPE`)
- `idClasse`: classe configurada (ex: `1116` para Execucao Fiscal) — aplicado se configurado
- `tamanhoPagina`: max resultados por pagina
- `searchAfter`: cursor de paginacao

**Merge:** usa dict `{numeroProcesso: item}` para deduplicar (primeiro encontrado prevalece).

**Retorno:**
```python
{
    "processos": [merged_items],
    "total": 75,
    "origens": {"nomeParte": 50, "outroNomeParte": 40}   # antes da dedup
}
```

### 7.6 buscar_detalhe_processo()

```python
def buscar_detalhe_processo(self, numero_processo, save_path=None) -> dict
```

**Fluxo:**
1. Se `save_path` existe em disco → carrega e retorna (sem chamar API)
2. GET `{base_url}/{numero_processo}`
3. Se 404 ou erro → retorna `{}`
4. Se 200 → salva em `save_path` (se fornecido) e retorna dict

### 7.7 Estatisticas

```python
def get_stats(self) -> dict
# {"requests": N, "retries": N, "errors_429": N, "errors_other": N, "pages_ok": N, "details_ok": N}
```

---

## 10. Step 1 - Coleta Unificada

**Arquivo:** `s1_coleta_unificada.py` (536 linhas)

### 8.1 GlobalStats

Objeto thread-safe para metricas em tempo real:

| Atributo | Tipo | Descricao |
|----------|------|-----------|
| `total_individuos` | int | Total de linhas da planilha |
| `processados` | int | Quantos individuos ja foram processados |
| `em_andamento` | str | ID + nome do individuo atual |
| `processos_encontrados` | int | Total acumulado de processos |
| `detalhes_baixados` | int | Detalhes com sucesso |
| `detalhes_404` | int | Detalhes 404 |
| `detalhes_cache` | int | Detalhes ja existentes em disco |
| `erros` | int | Erros diversos |
| `inicio` | float | Timestamp de inicio |

Metodos: `inc(**kw)` (soma), `put(**kw)` (set), `snapshot() -> dict`.

### 8.2 ColetaUnificada

```python
class ColetaUnificada:
    def __init__(self, config=None, progress_callback=None)
    def executar(self) -> dict
    def executar_por_processos(self, numeros, output_subdir="por_numero") -> dict
```

### 8.3 Fluxo de executar()

```
1. Valida config
2. Cria output_dir
3. Le planilha de entrada → DataFrame
4. Define total_individuos
5. Inicia workers (se download_detalhes=True)
6. Inicia thread de dashboard (se habilitado e sem callback)
7. Para cada linha do DataFrame:
   a. _processar_individuo(idx, row)
   b. Incrementa processados
   c. Em caso de erro: loga + incrementa erros
8. Aguarda fila de detalhes esvaziar
9. Para workers
10. Salva caches
11. Emite "coleta_fim"
12. Imprime dashboard final
13. Retorna snapshot + api_stats + cache_stats
```

### 8.4 Fluxo de _processar_individuo()

```
1. IDENTIFICACAO
   - Extrai: posicao → id (6 digitos, padleft), nome_estoque → nome, nr_documento → doc
   - Normaliza documento, identifica tipo (CPF/CNPJ), extrai raiz CNPJ
   - Verifica blacklist → skip

2. POOL DE PROCESSOS (dict: {numero: {item, origens: set}})

3. BUSCA POR DOCUMENTO (se habilitada e documento valido)
   - Chama api.buscar_por_documento()
   - Adiciona resultados ao pool com origem "por_documento"
   - Se gigante: marca no cache

4. BUSCA POR FILIAIS (se habilitada e CNPJ)
   - Para filial 0002 ate max_filiais+1:
     - Gera CNPJ completo com DVs
     - Skip se filial ja marcada como inexistente
     - Chama api.buscar_por_documento(cnpj_filial)
     - Se 0 resultados: marca filial como inexistente
     - Adiciona ao pool com origem "por_filial:{cnpj}"

5. BUSCA POR NOME (se habilitada e nome nao vazio)
   - Chama api.buscar_por_nome() (faz nomeParte + outroNomeParte + merge)
   - Extrai documentos (CPF/CNPJ) dos processos encontrados via extrair_documentos_dos_processos()
   - Adiciona ao pool com origem "por_nome"
   - **HOMONIMOS:** Salva homonimos.json com:
     - Cada documento encontrado: tipo, nomes das partes, qtd processos, amostra
     - Status: "unico" (1 doc) ou "pendente" (multiplos docs, precisa resolver)
     - Se multiplos docs: analista deve resolver na aba /homonimos antes do S2

6. PRIORIZACAO
   - Separa pool em: exec_fiscal, polo_ativo, outros
   - Aplica limites: max_processos_per_doc por categoria, max_processos_per_root total

7. PROCESSOS_UNICOS.JSON
   - Para cada processo selecionado: salva origens, prioridade, detalhe_baixado
   - Salva em {ind_dir}/processos_unicos.json

8. DOWNLOAD DETALHES (se habilitado)
   - Para cada processo selecionado:
     - Skip se 404 no cache
     - Skip se ja existe em disco (marca como cache hit)
     - Enfileira na task_queue: (numero, save_path, documento)

9. METADATA.JSON
   - Salva id, nome, documento, tipo, buscas (resultado de cada busca), priorizacao, timestamp
   - Inclui flag `homonimos_pendentes: true/false` se existem homonimos nao resolvidos
```

### 8.5 Limites (_aplicar_limites)

```python
def _aplicar_limites(self, ef, pa, ou) -> list:
```

1. Se `max_processos_per_doc > 0`: trunca cada lista (EF, PA, OU) nesse limite
2. Concatena: `ef + pa + ou`
3. Se `max_processos_per_root > 0`: trunca resultado total nesse limite

**Exemplo com defaults (per_doc=1, per_root=2):**
- 5 EF, 3 PA, 10 OU → trunca para 1 EF, 1 PA, 1 OU → concatena para 3 → trunca para 2

### 8.6 Workers

- Pool de `num_workers` threads daemon
- Cada worker consome da `_queue` com timeout de 2s
- Chama `api.buscar_detalhe_processo()` com `save_path`
- Se sucesso: `cache.add_processo(proc, "ok")`
- Se falha: `cache.add_processo_404(proc)`
- `queue.task_done()` sempre executado (garante que `queue.join()` funciona)

### 8.7 Dashboard

Thread daemon que imprime a cada `dashboard_interval` segundos. Detecta automaticamente Jupyter (usa `clear_output`) vs terminal (usa `cls`/`clear`).

### 8.8 API de Conveniencia

```python
def executar_coleta(config=None, progress_callback=None) -> dict
def executar_coleta_processos(processos: list, config=None) -> dict
```

---

## 11. Step 2 - Organizacao de Processos

**Arquivo:** `s2_organiza_processos.py` (426 linhas)

### 9.1 Colunas de Exportacao

```python
EXPORT_COLUMNS = [
    "ID Individuo", "Nome Cliente", "Origens",
    "Numero CNJ", "Valor Acao", "Valor Corrigido",
    "Data Ajuizamento", "Data Primeiro Ajuizamento", "Data Ultimo Movimento",
    "Classe", "Classe Hierarquia", "Assunto", "Assunto Hierarquia",
    "Partes", "Orgao Julgador", "Instancia", "Tribunal",
    "CNPJ Completo", "CNPJ Raiz", "CNPJ Filial",
    "Flag Extinto", "Flag Reu",
]
```

### 9.2 OrganizadorProcessos

```python
class OrganizadorProcessos:
    def __init__(self, config=None, progress_callback=None)
    def executar(self) -> pd.DataFrame
    def consolidar_paginas(self) -> pd.DataFrame
```

### 9.3 Fluxo de executar()

```
1. Lista pastas de individuos em output_dir
   - Prioriza pastas com metadata.json
   - Fallback: qualquer subpasta
2. Limpa pastas vazias
3. Para cada individuo:
   a. **VERIFICA HOMONIMOS (_resolver_homonimos)**:
      - Se nao existe homonimos.json → processa tudo normalmente
      - Se existe com status "unico" (1 doc) → processa tudo
      - Se existe com status "pendente" (multiplos docs, nao resolvido) → PULA individuo
      - Se existe com status "resolvido" → filtra apenas processos dos documentos selecionados
   b. Le metadata.json (id, nome, documento, tipo_documento)
   c. Le processos_unicos.json (origens por processo)
   d. Se pasta detalhes/ existe:
      - Para cada .json em detalhes/:
        - Se homonimos resolvidos: skip se processo nao esta nos permitidos
        - extrair_campos_processo() → lista de records
        - Adiciona ID Individuo, Nome Cliente, Origens
   e. Senao (fallback pages):
      - Coleta page_*.json recursivamente
      - Para cada item em content:
        - Se homonimos resolvidos: skip se processo nao esta nos permitidos
        - extrair_campos_pagina() → record
        - Adiciona ID Individuo, Nome Cliente, Origens
4. Monta DataFrame
5. Deduplicacao (3 etapas)
6. Join com dados de cliente
7. Seleciona EXPORT_COLUMNS
8. Salva saida_processos_consolidados_{timestamp}.xlsx
9. Salva caches (SELIC)
```

### 9.3.1 _resolver_homonimos (novo)

```python
@staticmethod
def _resolver_homonimos(ind_dir: str) -> set | None
```

| Retorno | Significado | Acao no S2 |
|---------|-------------|-----------|
| `None` | Sem homonimos.json | Processa tudo normalmente |
| `set()` (vazio) | Homonimos pendentes | **Pula individuo** |
| `set({...})` | Homonimos resolvidos | Filtra por processos dos docs selecionados |

Le `homonimos.json`, itera os documentos com `selecionado: true`, e retorna o conjunto de numeros de processo desses documentos.

### 9.4 Deduplicacao (3 Etapas)

```
ETAPA 1: df.drop_duplicates(subset=["Numero CNJ"], keep="first")
         Remove duplicatas exatas.

ETAPA 2: Se ainda ha duplicatas em "Numero CNJ":
         - Calcula _info_count = quantidade de campos nao-nulos/nao-vazios
         - Ordena por _info_count desc
         - drop_duplicates(subset=["Numero CNJ"], keep="first")
         Mantem a linha com mais informacao.

ETAPA 3: drop_duplicates(subset=["Numero CNJ", "CNPJ Raiz"], keep="first")
         Remove processos repetidos dentro do mesmo CNPJ raiz.

POS: Consolida origens — se mesmo CNJ apareceu com origens diferentes,
     mergeia todas as origens unicas em uma string.
```

### 9.5 Join com Clientes

1. Le planilha de entrada (input_file)
2. Auto-detecta colunas de documento e nome (heuristica por nome da coluna)
3. Cria `nome_map`: `{doc_normalizado: nome, raiz_8dig: nome}`
4. Preenche "Nome Cliente" onde vazio, tentando match por CNPJ Completo, depois por CNPJ Raiz

### 9.6 consolidar_paginas()

Versao simplificada que le apenas `page_*.json` (sem detalhes). Gera `processos_paginados_consolidados_{timestamp}.xlsx`. Util quando `DOWNLOAD_DETALHES=false`.

### 9.7 API de Conveniencia

```python
def executar_organizacao(config=None, progress_callback=None) -> pd.DataFrame
def consolidar_paginas(config=None) -> pd.DataFrame
```

---

## 12. Step 3 - Visao Devedor

**Arquivo:** `s3_visao_devedor.py` (490 linhas)

### 10.1 Entity ID

```python
def calcular_entity_id(row) -> str
```

**Logica de resolucao:**
1. Se CNPJ Raiz presente e >= 8 digitos e != "NA" → usa raiz[:8]
2. Se CNPJ Completo com 14 digitos → extrai raiz[:8]
3. Se CNPJ Completo com 11 digitos (CPF) → usa CPF inteiro
4. Fallback: documento ou "DESCONHECIDO"

### 10.2 Indicadores por Entidade

```python
def aggregate_por_entidade(grupo: pd.DataFrame) -> dict
```

**Indicadores calculados:**

| Indicador | Tipo | Calculo |
|-----------|------|---------|
| Entity ID | str | Chave do grupo |
| IDs Individuos | str | Lista unica de IDs que contribuiram processos |
| Qtd Processos | int | `len(grupo)` |
| Qtd Ativos | int | `count(Flag Extinto == 0)` |
| Qtd Extintos | int | `count(Flag Extinto == 1)` |
| Qtd Exec Fiscal | int | Classe contem "1116" |
| Qtd Trabalhista | int | `is_justica_trabalho(CNJ)` |
| Qtd Polo Ativo Nao EF | int | `Flag Reu == 1 AND classe != 1116` |
| Total Valor Acao | float | `sum(Valor Acao)` |
| Total Valor Corrigido | float | `sum(Valor Corrigido)` |
| Saldo Liquido | float | `sum(Valor Corrigido onde ativo) - sum(Valor Corrigido onde extinto)` |
| Maior Valor Individual | float | `max(Valor Corrigido)` |
| Data Mais Antiga | str | `min(Data Ajuizamento)` |
| Data Mais Recente | str | `max(Data Ajuizamento)` |
| Ultima Atualizacao | str | `max(Data Ultimo Movimento)` |
| Tribunais | str | Lista unica separada por `\|` |
| Classes | str | Lista unica separada por `\|` |
| Origens | str | Todas as origens consolidadas |

### 10.3 VisaoDevedor

```python
class VisaoDevedor:
    def __init__(self, config=None, df_processos=None, progress_callback=None)
    def executar(self) -> pd.DataFrame
```

### 10.4 Fluxo de executar()

```
1. Obtem DataFrame de processos:
   - Se df_processos passado → usa diretamente
   - Senao: procura saida_processos_consolidados_*.xlsx (mais recente) em output_dir
   - Fallback: procura em ./
2. Cria coluna "Entity ID" via calcular_entity_id()
3. Agrupa por Entity ID
4. Para cada grupo: aggregate_por_entidade() → dict de indicadores
5. Join com planilha de entrada (nome do devedor)
6. Adiciona estatisticas de download:
   - Para cada pasta em output_dir com metadata.json:
     - Conta page_*.json e .json nao-page
     - Mapeia entity_id → {paginas, detalhes}
7. Ordena por Saldo Liquido desc
8. Salva visao_devedor_{timestamp}.xlsx com formatacao
```

### 10.5 Formatacao Excel

- **Header:** fonte branca, bold, fundo azul (#2F5496), centralizado
- **Bordas:** finas em todas as celulas
- **Colunas monetarias:** formato `#,##0.00`
- **Saldo Liquido negativo:** fonte vermelha, bold
- **Larguras:** ajustadas ao header (max 40, monetarias = 18)
- **Congelamento:** header fixo (A2)
- **Filtro automatico:** habilitado em todas as colunas

### 10.6 API de Conveniencia

```python
def executar_visao_devedor(config=None, df_processos=None, progress_callback=None) -> pd.DataFrame
```

---

## 13. Pipeline

**Arquivo:** `pipeline.py` (185 linhas)

### 11.1 Classe Pipeline

```python
class Pipeline:
    def __init__(self, config=None, progress_callback=None)
    def executar(self, steps=None) -> dict
    def executar_por_processos(self, numeros: list) -> dict
```

### 11.2 Fluxo

```python
executar(steps=["s1", "s2", "s3"])  # default: todos
```

Executa sequencialmente os steps indicados. Cada step usa import lazy.

**Retorno:**
```python
{
    "s1": {snapshot + api_stats + cache_stats},
    "s2": {"total_processos": N, "colunas": [...]},
    "s3": {"total_entidades": N},
    "elapsed": 123.45
}
```

### 11.3 CLI

```bash
python pipeline.py                          # roda tudo
python pipeline.py --step s1                # so coleta
python pipeline.py --step s2 s3             # organizacao + visao
python pipeline.py --processos "0001-23..." # busca processos especificos
python pipeline.py --debug                  # modo verboso
```

---

## 14. Estrutura de Saida

### 12.1 Pastas por Individuo

```
outputs/
├── 000001/                              # ID do individuo (posicao padleft 6)
│   ├── metadata.json                    # Metadados: id, nome, doc, buscas, priorizacao, homonimos_pendentes
│   ├── processos_unicos.json            # {numero: {origens, prioridade, detalhe_baixado}}
│   ├── homonimos.json                   # Mapeamento documento→processos (se busca por nome habilitada)
│   ├── por_documento/
│   │   └── pages/
│   │       ├── page_1.json              # Resposta paginada da API
│   │       └── page_2.json
│   ├── por_filial/
│   │   └── 12345678000299/
│   │       └── pages/
│   │           └── page_1.json
│   ├── por_nome/
│   │   ├── nomeParte/
│   │   │   └── page_1.json
│   │   └── outroNomeParte/
│   │       └── page_1.json
│   └── detalhes/                        # So se DOWNLOAD_DETALHES=true
│       ├── 0001234-56.2020.8.17.0001.json
│       └── 0005678-90.2019.8.17.0002.json
├── 000002/
│   └── ...
├── saida_processos_consolidados_20260212_1430.xlsx    # Saida do Step 2
└── visao_devedor_20260212_1435.xlsx                   # Saida do Step 3
```

### 12.2 metadata.json

```json
{
  "id": "000001",
  "nome": "EMPRESA EXEMPLO LTDA",
  "documento": "12345678000199",
  "documento_normalizado": "12345678000199",
  "tipo_documento": "CNPJ",
  "buscas": {
    "por_documento": {
      "total_api": 45,
      "processos": 45,
      "gigante": false
    },
    "por_filial": {
      "12345678000299": {"processos": 3}
    },
    "por_nome": {
      "total": 30,
      "origens_api": {"nomeParte": 20, "outroNomeParte": 15},
      "documentos_encontrados": ["12345678000199", "98765432100"],
      "homonimos": true
    }
  },
  "total_processos_unicos": 60,
  "priorizacao": {"exec_fiscal": 10, "polo_ativo": 5, "outros": 45},
  "homonimos_pendentes": true,
  "timestamp": "2026-02-12T14:30:00.000000"
}
```

### 12.3 homonimos.json (novo)

Gerado pelo S1 quando a busca por nome encontra processos. Essencial para resolver ambiguidades antes do S2.

```json
{
  "nome_busca": "JOAO DA SILVA",
  "total_documentos": 3,
  "total_processos_nome": 85,
  "status": "pendente",
  "documentos": {
    "12345678909": {
      "documento": "12345678909",
      "tipo": "CPF",
      "nomes": ["JOAO DA SILVA", "JOAO DA SILVA ME"],
      "qtd_processos": 45,
      "processos": ["0001234-56.2020.8.17.0001", "0005678-90.2019.8.17.0002"],
      "selecionado": null
    },
    "98765432100": {
      "documento": "98765432100",
      "tipo": "CPF",
      "nomes": ["JOAO DA SILVA JUNIOR"],
      "qtd_processos": 30,
      "processos": ["0009999-88.2021.8.17.0003"],
      "selecionado": null
    },
    "11222333000144": {
      "documento": "11222333000144",
      "tipo": "CNPJ",
      "nomes": ["JOAO DA SILVA COMERCIO LTDA"],
      "qtd_processos": 10,
      "processos": ["0007777-11.2022.8.17.0004"],
      "selecionado": null
    }
  }
}
```

**Campos do status:**

| Status | Significado | Acao no S2 |
|--------|-------------|-----------|
| `"unico"` | Apenas 1 documento encontrado | Processa tudo normalmente |
| `"pendente"` | Multiplos documentos, nao resolvido | **Pula individuo** |
| `"resolvido"` | Analista selecionou documentos corretos | Filtra processos dos selecionados |

**Campos de `selecionado`:**

| Valor | Significado |
|-------|-------------|
| `null` | Nao resolvido ainda |
| `true` | Este documento e do devedor correto |
| `false` | Este documento nao e do devedor |

Apos resolucao, `status` muda para `"resolvido"` e `resolvido_em` e adicionado com timestamp.
```

### 12.4 processos_unicos.json

```json
{
  "0001234-56.2020.8.17.0001": {
    "origens": ["por_documento", "por_nome"],
    "prioridade": "exec_fiscal",
    "detalhe_baixado": true
  },
  "0005678-90.2019.8.17.0002": {
    "origens": ["por_filial:12345678000299"],
    "prioridade": "outros",
    "detalhe_baixado": false
  }
}
```

---

## 15. APIs Externas

### 13.1 API PDPJ

**Base URL:** `https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1/processos`

**Autenticacao:** Header `Authorization: Bearer {JWT}`

**Endpoints usados:**

| Metodo | Path | Parametros | Uso |
|--------|------|-----------|-----|
| GET | `/` | `cpfCnpjParte`, `siglaTribunal`, `tamanhoPagina`, `idClasse`, `searchAfter` | Busca por documento |
| GET | `/` | `nomeParte`, `tribunal`, `idClasse`, `tamanhoPagina`, `searchAfter` | Busca por nome (campo 1) |
| GET | `/` | `outroNomeParte`, `tribunal`, `idClasse`, `tamanhoPagina`, `searchAfter` | Busca por nome (campo 2) |
| GET | `/{numeroProcesso}` | - | Detalhe individual |

**Resposta paginada:**
```json
{
  "totalRegistros": 1234,
  "content": [
    {
      "id": "...",
      "numeroProcesso": "0001234-56.2020.8.17.0001",
      "siglaTribunal": "TJPE",
      "dataHoraAtualizacao": "...",
      "dataHoraUltimoMovimento": "...",
      "tramitacoes": [
        {
          "classe": [{"codigo": 1116, "descricao": "Execucao Fiscal", "hierarquia": "..."}],
          "assunto": [{"codigo": 123, "descricao": "...", "hierarquia": "..."}],
          "partes": [
            {
              "polo": "ATIVO",
              "tipoParte": "AUTOR",
              "nome": "MUNICIPIO DE RECIFE",
              "documentosPrincipais": [{"numero": "12345678000199"}]
            }
          ],
          "valorAcao": 15000.50,
          "orgaoJulgador": {"nome": "1a Vara da Fazenda Publica"},
          "instancia": "1",
          "tribunal": {"nome": "TJPE"},
          "ultimoMovimento": {"descricao": "..."},
          "movimentos": [{"descricao": "..."}],
          "dataHoraUltimaDistribuicao": "...",
          "dataHoraPrimeiroAjuizamento": "..."
        }
      ],
      "sort": [123456789, 987654321]
    }
  ],
  "searchAfter": [123456789, 987654321]
}
```

### 13.2 API Banco Central (SELIC)

**URL:** `https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados`

**Parametros:** `formato=json`, `dataInicial=DD/MM/YYYY`, `dataFinal=DD/MM/YYYY`

**Resposta:**
```json
[
  {"data": "02/01/2020", "valor": "0,017699"},
  {"data": "03/01/2020", "valor": "0,017699"}
]
```

**Serie 4390:** Taxa SELIC diaria (% ao dia). Somamos todos os valores do periodo para obter a taxa acumulada.

---

## 16. Integracao com Frontend

### 14.1 Exemplo Flask

```python
from flask import Flask, request, jsonify
from config import Config
from pipeline import Pipeline

app = Flask(__name__)

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(Config.from_env().to_dict())

@app.route("/api/executar", methods=["POST"])
def executar():
    cfg = Config.from_dict(request.json.get("config", {}))
    erros = cfg.validar()
    if erros:
        return jsonify({"erros": erros}), 400
    resultado = Pipeline(cfg).executar(steps=request.json.get("steps", ["s1", "s2", "s3"]))
    return jsonify(resultado)
```

### 14.2 Exemplo Streamlit

```python
import streamlit as st
from config import Config
from s1_coleta_unificada import ColetaUnificada

st.title("Devedor360")
token = st.text_input("Token PDPJ")
if st.button("Executar Coleta"):
    cfg = Config(tokens=[token], download_detalhes=True)
    progress = st.progress(0)
    status = st.empty()
    
    def callback(evt, data):
        if evt == "ind_done":
            progress.progress(data["idx"] / 100)
            status.text(f"Processado: {data['id']}")
    
    resultado = ColetaUnificada(cfg, callback).executar()
    st.success(f"Finalizado! {resultado['processos']} processos encontrados.")
```

### 14.3 Exemplo FastAPI com WebSocket

```python
from fastapi import FastAPI, WebSocket
from config import Config
from pipeline import Pipeline

app = FastAPI()

@app.websocket("/ws/pipeline")
async def pipeline_ws(ws: WebSocket):
    await ws.accept()
    data = await ws.receive_json()
    cfg = Config.from_dict(data.get("config", {}))
    
    def callback(step, evt, data):
        import asyncio
        asyncio.run(ws.send_json({"step": step, "event": evt, "data": data}))
    
    resultado = Pipeline(cfg, callback).executar(steps=data.get("steps"))
    await ws.send_json({"event": "done", "resultado": resultado})
```

---

## 17. Referencia de Eventos (Callbacks)

### 15.1 Step 1 (ColetaUnificada)

| Evento | Data | Quando |
|--------|------|--------|
| `coleta_inicio` | `{"total": N}` | Inicio da coleta |
| `ind_start` | `{"id": "000001", "nome": "...", "idx": 0}` | Inicio de cada individuo |
| `ind_done` | `{"id": "000001", "procs": 5, "idx": 0}` | Fim de cada individuo |
| `det_ok` | `{"proc": "0001234-..."}` | Detalhe baixado com sucesso |
| `coleta_fim` | `{snapshot + api + cache}` | Fim da coleta |

### 15.2 Step 2 (OrganizadorProcessos)

| Evento | Data | Quando |
|--------|------|--------|
| `s2_inicio` | `{"total": N}` | Inicio do processamento |
| `s2_progresso` | `{"i": 5, "total": 100, "records": 250}` | Apos cada individuo |
| `s2_homonimo_pendente` | `{"id": "000001", "nome": "..."}` | Individuo pulado por homonimos nao resolvidos |
| `s2_fim` | `{"arquivo": "...", "total": N, "stats": {...}}` | Fim |

### 15.3 Step 3 (VisaoDevedor)

| Evento | Data | Quando |
|--------|------|--------|
| `s3_inicio` | `{"total_processos": N}` | Inicio |
| `s3_progresso` | `{"i": 50, "total": 200}` | A cada 50 entidades |
| `s3_fim` | `{"arquivo": "...", "entidades": N}` | Fim |

### 15.4 Pipeline

| Evento | Data | Quando |
|--------|------|--------|
| `pipeline_inicio` | `{"steps": ["s1","s2","s3"]}` | Inicio |
| `pipeline_fim` | `{"elapsed": 123.45}` | Fim |
| `s1` / `s2` / `s3` | (delegado ao step) | Encapsulados |

---

## 18. Guia de Impacto de Alteracoes

### Adicionar novo tipo de busca no Step 1

| Arquivo | Local | Acao |
|---------|-------|------|
| `config.py` | Classe Config | Adicionar flag `enable_busca_novo` |
| `.env` | - | Adicionar variavel |
| `s1_coleta_unificada.py` | `_processar_individuo()` | Adicionar bloco de busca (D) |
| `s1_coleta_unificada.py` | Nova funcao `_busca_novo()` | Implementar logica |
| `api_client.py` | (se novo endpoint) | Adicionar metodo |

### Adicionar novo campo extraido dos processos

| Arquivo | Local | Acao |
|---------|-------|------|
| `utils.py` | `extrair_campos_processo()` | Adicionar campo ao dict |
| `utils.py` | `extrair_campos_pagina()` | Adicionar campo (se disponivel) |
| `s2_organiza_processos.py` | `EXPORT_COLUMNS` | Adicionar nome da coluna |

### Adicionar novo indicador na visao devedor

| Arquivo | Local | Acao |
|---------|-------|------|
| `s3_visao_devedor.py` | `aggregate_por_entidade()` | Calcular indicador |
| `s3_visao_devedor.py` | `_salvar_excel()` | (se formatacao especial) |

### Alterar logica de priorizacao

| Arquivo | Local | Acao |
|---------|-------|------|
| `utils.py` | `priorizar_processos()` | Alterar regras |
| `utils.py` | `is_execucao_fiscal()`, `is_polo_ativo()` | Ajustar classificadores |
| `s1_coleta_unificada.py` | `_aplicar_limites()` | Ajustar limites se necessario |

### Alterar logica de deduplicacao

| Arquivo | Local | Acao |
|---------|-------|------|
| `s2_organiza_processos.py` | `_deduplicar()` | Alterar etapas |

### Adicionar novo cache

| Arquivo | Local | Acao |
|---------|-------|------|
| `cache_manager.py` | `_DEFAULTS` | Adicionar nome do arquivo |
| `cache_manager.py` | `__init__` | Adicionar atributo |
| `cache_manager.py` | `_load_all` / `save_all` | Adicionar I/O |
| `cache_manager.py` | Novos metodos | `is_*` / `add_*` / `get_*` |

### Trocar API ou adicionar nova fonte de dados

| Arquivo | Local | Acao |
|---------|-------|------|
| `api_client.py` | Nova classe ou metodo | Implementar cliente |
| `config.py` | Config | Adicionar parametros |
| `s1_coleta_unificada.py` | `_processar_individuo()` | Integrar nova fonte |

### Alterar formato da planilha de entrada

| Arquivo | Local | Acao |
|---------|-------|------|
| `s1_coleta_unificada.py` | `_processar_individuo()` linhas 200-202 | Alterar nomes das colunas |
| `s2_organiza_processos.py` | `_join_clientes()` | Ajustar heuristica de colunas |
| `s3_visao_devedor.py` | `_join_input()` | Ajustar heuristica de colunas |

### Alterar termos de extincao

| Arquivo | Local | Acao |
|---------|-------|------|
| `utils.py` | `EXTINCAO_TERMS` (linhas 286-312) | Adicionar/remover termos |

### Adicionar formatacao Excel

| Arquivo | Local | Acao |
|---------|-------|------|
| `s3_visao_devedor.py` | `_salvar_excel()` | Alterar estilos openpyxl |

### Alterar logica de resolucao de homonimos

| Arquivo | Local | Acao |
|---------|-------|------|
| `s1_coleta_unificada.py` | `_busca_nome()` | Alterar como documentos sao extraidos/agrupados |
| `s2_organiza_processos.py` | `_resolver_homonimos()` | Alterar logica de filtragem |
| `web/routes/api_data.py` | Endpoints `/api/homonimos/*` | Alterar API de resolucao |
| `web/templates/pages/homonimos.html` | Frontend | Alterar UI de selecao |

### Adicionar nova pagina no frontend

| Arquivo | Local | Acao |
|---------|-------|------|
| `web/routes/pages.py` | Nova rota `@router.get("/nova")` | Adicionar rota da pagina |
| `web/templates/pages/nova.html` | Novo template | Criar pagina (estende `base.html`) |
| `web/templates/base.html` | Sidebar | Adicionar link de navegacao |
| `web/routes/api_data.py` | (se novo endpoint) | Adicionar API de dados |

---

## 19. Sistema de Flags (flags.py)

Flags sao funcoes Python puras registradas com `@register_flag()`:

```python
@register_flag("pgfn", "PGFN", "Fazenda Nacional no polo ativo", color="red")
def flag_pgfn(processo: dict, doc: str = "") -> bool:
    ...
```

Para adicionar uma nova flag basta criar a funcao no `flags.py`. Ela aparece automaticamente:
- Na tabela de configuracao do frontend
- Na avaliacao de cada processo (pipeline)
- Como coluna nas planilhas de saida

Flags pre-registradas: `anulatoria`, `pgfn`, `bancos`, `exec_fiscal`, `trabalhista`.

Funcoes auxiliares disponiveis em `flags.py`:
- `avaliar_flags(processo, doc)` - Avalia todas as flags para um processo
- `listar_flags()` - Retorna lista de flags para o frontend
- `_get_nomes_polo(processo, polo)` - Nomes de um polo (ATIVO/PASSIVO)
- `_doc_no_polo(processo, doc, polo)` - Verifica se documento esta em polo

---

## 20. Homonimos

### 20.1 O Problema

Quando buscamos processos por **nome** (nomeParte + outroNomeParte), a API PDPJ retorna todos os processos de qualquer pessoa que tenha aquele nome. Se "JOAO DA SILVA" retorna processos de 3 CPFs diferentes (homonimos), precisamos que o analista indique qual e o devedor correto antes de consolidar os dados.

### 20.2 Fluxo Completo

```
S1 (Coleta)                      Frontend                        S2 (Organizacao)
                                                                 
busca por nome ─┐                                               
nomeParte       ├─> processos ─> extrair_documentos ─>          
outroNomeParte ─┘                                               
                                  homonimos.json                 
                                  {doc1: procs, doc2: procs}     
                                        │                        
                                        ▼                        
                                  /homonimos (frontend)          
                                  analista seleciona ─────────>  _resolver_homonimos()
                                  docs corretos                  filtra processos
                                        │                        
                                  POST /api/homonimos/{id}/      
                                  resolver                       
                                        │                        
                                  homonimos.json                 
                                  status: "resolvido"            
                                  selecionado: true/false        
```

### 20.3 Geracao (S1)

No metodo `_busca_nome()` de `ColetaUnificada`:

1. Apos receber processos da API, chama `extrair_documentos_dos_processos()` que agrupa processos por CPF/CNPJ
2. Para cada documento encontrado, extrai:
   - Tipo (CPF/CNPJ)
   - Nomes das partes associadas (de `tramitacoes[].partes[].nome`)
   - Quantidade de processos
   - Amostra de ate 20 numeros de processo
3. Salva `homonimos.json` na pasta do individuo
4. Se mais de 1 documento: status = `"pendente"`, senao: `"unico"`

### 20.4 Resolucao (Frontend)

A pagina `/homonimos` permite o analista:

1. Ver lista de todos os individuos com homonimos (filtro: pendentes/resolvidos/unicos)
2. Expandir um individuo para ver os documentos candidatos
3. Para cada documento: ver CPF/CNPJ formatado, tipo, nomes associados, qtd processos
4. Marcar checkboxes nos documentos que sao do devedor correto
5. Clicar "Confirmar Selecao" — chama `POST /api/homonimos/{id}/resolver`
6. Status muda para "resolvido", `selecionado` atualizado para cada documento

**Reset:** O analista pode clicar "Resetar" para voltar ao estado "pendente" (`POST /api/homonimos/{id}/resetar`).

### 20.5 Filtragem (S2)

No metodo `_processar_individuo()` de `OrganizadorProcessos`:

1. Chama `_resolver_homonimos(ind_dir)` que le `homonimos.json`
2. Se retorna `None` (sem homonimos): processa tudo normalmente
3. Se retorna `set()` vazio (pendente): **pula o individuo** e emite evento `s2_homonimo_pendente`
4. Se retorna `set(processos)`: filtra apenas esses processos nos detalhes e pages

### 20.6 Visibilidade

- **Dashboard:** Banner amarelo "N homonimo(s) pendente(s)" com link para `/homonimos`
- **Individuos:** Coluna "Homonimos" com badge Pendente/Resolvido/OK
- **Stats API:** Campos `homonimos_pendentes` e `homonimos_resolvidos`

---

## 21. Deployment

### 21.1 Heroku

**Arquivos de configuracao:**

| Arquivo | Conteudo |
|---------|----------|
| `Procfile` | `web: uvicorn web_app:app --host 0.0.0.0 --port $PORT` |
| `runtime.txt` | `python-3.12.8` |
| `.env.example` | Template com todos os parametros (copiar para `.env`) |
| `requirements.txt` | Dependencias Python com versoes |

**Deploy:**
```bash
heroku create meu-app
heroku config:set PDPJ_TOKENS=token1,token2
git push heroku master
```

### 21.2 Filesystem Efemero

O Heroku reinicia dynos periodicamente e **perde todos os dados em disco**. Para contornar:

1. **Download ZIP:** Endpoint `GET /api/download-zip` gera um ZIP streamado com todos os outputs, Excels e caches. Botao disponivel na pagina Pipeline (apos conclusao) e no Dashboard.
2. **Keep-alive:** O frontend faz polling de `GET /api/ping` a cada 20s enquanto o pipeline roda, impedindo que o dyno hiberne. Implementado em `app.js` com `startKeepAlive()`/`stopKeepAlive()`.
3. **Banner de aviso:** Dashboard e Pipeline mostram alertas sobre a perda de dados.

### 21.3 GitHub

O `.gitignore` esta configurado para ignorar:
- `.env` (tokens reais)
- `outputs/` (dados baixados)
- `nomes/` (dados do codigo original)
- Todos os Excels gerados (`entrada_*.xlsx`, `saida_*.xlsx`, `visao_devedor_*.xlsx`)
- Caches (`selic_cache.json`, `processos_404.json`, etc.)
- Arquivos temporarios (`_temp_upload*`)
- IDE/OS files (`.vscode/`, `.idea/`, `.cursor/`, `Thumbs.db`, etc.)

### 21.4 Variaveis de Ambiente (.env)

Todas as configuracoes sao lidas do `.env`. Ver `.env.example` para o template completo. Principais:

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `PDPJ_TOKENS` | (obrigatorio) | Tokens JWT separados por virgula |
| `PDPJ_BASE_URL` | `https://api-processo-...` | URL base da API PDPJ |
| `PDPJ_TRIBUNAL` | `TJPE` | Sigla do tribunal |
| `PDPJ_ID_CLASSE` | `1116` | Classe de processo (vazio = sem filtro) |
| `INPUT_FILE` | `Recife_nomes_partes_estoque.xlsx` | Planilha de entrada |
| `OUTPUT_DIR` | `outputs` | Diretorio de saida |
| `DOWNLOAD_DETALHES` | `false` | Baixar capas individuais dos processos |
| `ENABLE_BUSCA_DOCUMENTO` | `true` | Buscar por CPF/CNPJ |
| `ENABLE_BUSCA_NOME` | `true` | Buscar por nomeParte + outroNomeParte |
| `ENABLE_BUSCA_FILIAL` | `true` | Iterar filiais CNPJ |
| `DEBUG` | `false` | Modo verboso |

---

*Documento gerado em 12/02/2026. Atualizado com frontend web, homonimos, paginacao server-side, SSE resiliente, Kanban animado e deployment Heroku.*

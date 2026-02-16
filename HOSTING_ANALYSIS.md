# Análise de Hospedagem Gratuita - Cron Macroeconômico

## Requisitos do Projeto

| Componente | Necessidade |
|------------|-------------|
| Banco de dados | ~2MB/dia (~60MB/mês de notícias) |
| Cron | Rodar a cada 30-60 min |
| Uptime | Não precisa ser 24/7, pode ter cold starts |

---

## 1. BANCO DE DADOS - Opções Gratuitas

### Opção A: Turso (SQLite Cloud) ⭐ RECOMENDADO
| Aspecto | Detalhe |
|---------|---------|
| Free tier | **9GB de storage**, 1 bilhão de leituras/mês |
| Vantagem | Compatível com SQLite atual (migração simples) |
| SDK | Python via `libsql` |
| Latência | Edge locations globais |
| URL | turso.tech |

### Opção B: Supabase (PostgreSQL)
| Aspecto | Detalhe |
|---------|---------|
| Free tier | 500MB storage, 2GB bandwidth |
| Vantagem | API REST automática, dashboard bonito |
| Desvantagem | Pausa após 1 semana sem uso |
| URL | supabase.com |

### Opção C: Neon (PostgreSQL)
| Aspecto | Detalhe |
|---------|---------|
| Free tier | 512MB storage, 190 compute hours/mês |
| Vantagem | Branching de banco (útil para dev) |
| Desvantagem | Cold starts de ~1s |
| URL | neon.tech |

### Opção D: MongoDB Atlas
| Aspecto | Detalhe |
|---------|---------|
| Free tier | 512MB storage |
| Vantagem | Flexível para dados não estruturados |
| Desvantagem | Requer reescrever queries |
| URL | mongodb.com/atlas |

---

## 2. CRON/SCHEDULER - Opções Gratuitas

### Opção A: GitHub Actions ⭐ RECOMENDADO
| Aspecto | Detalhe |
|---------|---------|
| Free tier | **2000 min/mês** (repos públicos: ilimitado) |
| Execução | Cron syntax nativo, até cada 5 min |
| Vantagem | Já integrado com Git, logs automáticos |
| Desvantagem | Pode ter delay de até 15min em horários de pico |

**Cálculo:**
- 48 execuções/dia × 4 min cada = 192 min/dia
- 192 × 30 = 5760 min/mês
- Solução: repo público (ilimitado) ou rodar a cada 1h (2880 min/mês)

### Opção B: Render (Background Worker)
| Aspecto | Detalhe |
|---------|---------|
| Free tier | 750 horas/mês |
| Vantagem | Servidor sempre rodando |
| Desvantagem | Spin down após 15min sem requests |
| URL | render.com |

### Opção C: Cloudflare Workers + Cron Triggers
| Aspecto | Detalhe |
|---------|---------|
| Free tier | 100k requests/dia |
| Vantagem | Extremamente rápido, edge computing |
| Desvantagem | Limite de CPU 10ms (pode ser pouco) |
| URL | workers.cloudflare.com |

### Opção D: Railway
| Aspecto | Detalhe |
|---------|---------|
| Free tier | $5 crédito/mês (~500h de uso leve) |
| Vantagem | Deploy simples via Git |
| Desvantagem | Crédito pode acabar se mal configurado |
| URL | railway.app |

---

## 3. COMBINAÇÕES RECOMENDADAS

### 🥇 Combinação 1: Turso + GitHub Actions (MELHOR)
```
Custo: $0
Storage: 9GB (suficiente para ~1 ano de notícias)
Execução: Ilimitada (repo público)
Complexidade: Baixa
```

**Vantagens:**
- SQLite → Turso = migração quase zero
- GitHub Actions = cron confiável e gratuito
- Logs e histórico de execuções automáticos
- Fácil debugging

### 🥈 Combinação 2: Supabase + GitHub Actions
```
Custo: $0
Storage: 500MB (~3-4 meses de notícias)
Execução: Ilimitada (repo público)
Complexidade: Média (migrar para PostgreSQL)
```

**Vantagens:**
- Dashboard visual para ver dados
- API REST automática (útil para o blog)
- Mais robusto para crescer

### 🥉 Combinação 3: Neon + Render
```
Custo: $0
Storage: 512MB
Execução: 750h/mês
Complexidade: Média
```

**Vantagens:**
- Pode rodar como servidor contínuo
- Bom se quiser adicionar API depois

---

## 4. ARQUITETURA RECOMENDADA

```
┌─────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Cron: "0 */1 * * *" (a cada 1 hora)            │    │
│  │                                                  │    │
│  │  1. Checkout do código                          │    │
│  │  2. Setup Python                                │    │
│  │  3. pip install requirements                    │    │
│  │  4. python main.py fetch                        │    │
│  │  5. (Opcional) Gerar relatório                  │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                      TURSO DB                            │
│  ┌─────────────────────────────────────────────────┐    │
│  │  SQLite na nuvem                                │    │
│  │  - news (notícias)                              │    │
│  │  - sources (fontes)                             │    │
│  │  - keywords (filtros)                           │    │
│  │  - fetch_logs (histórico)                       │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              FUTURO: VERCEL/CLOUDFLARE                   │
│  ┌─────────────────────────────────────────────────┐    │
│  │  API REST para servir notícias ao blog          │    │
│  │  - GET /api/news (listar)                       │    │
│  │  - GET /api/news/top (prioridade)               │    │
│  │  - Webhook para publicação automática           │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

---

## 5. ESTIMATIVA DE CONSUMO (Combinação 1)

### Turso
| Recurso | Uso estimado/mês | Limite grátis |
|---------|------------------|---------------|
| Storage | ~60MB | 9GB |
| Leituras | ~50k | 1 bilhão |
| Escritas | ~50k | Ilimitado |

### GitHub Actions (repo público)
| Recurso | Uso estimado/mês | Limite grátis |
|---------|------------------|---------------|
| Minutos | ~3000 min | Ilimitado |
| Execuções | ~720 | Ilimitado |

**Veredicto:** Cabe confortavelmente no free tier por muito tempo.

---

## 6. PRÓXIMOS PASSOS

1. **Criar conta no Turso** (turso.tech)
2. **Criar conta no GitHub** (se não tiver)
3. **Criar repositório público** para o projeto
4. **Adaptar código** para usar Turso
5. **Configurar GitHub Actions** workflow
6. **Testar** execução automática

---

## 7. ALTERNATIVA MINIMALISTA

Se quiser ainda mais simples, pode usar apenas:

**GitHub Actions + SQLite no próprio repo**
- O banco SQLite fica commitado no repo
- GitHub Actions roda, atualiza o banco, commita de volta
- Simples mas "hackish"
- Funciona para volumes pequenos

---

## DECISÃO SUGERIDA

**Ir com Turso + GitHub Actions** porque:
1. Zero custo
2. Migração simples (SQLite → Turso)
3. Escalável para o futuro
4. Profissional e confiável

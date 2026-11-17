# COOL GIRLS STUFF · robô de ofertas

O robô roda sozinho a cada 20 minutos aqui no GitHub. Ele:

1. procura promoções de beleza na **Shopee** e no **Mercado Livre** (a **Amazon** entra quando você tiver 10 vendas em 30 dias);
2. filtra pelo que está no arquivo `config.toml` (desconto mínimo, faixa de preço, lojas oficiais, palavras proibidas);
3. coloca o **seu link de afiliada** em cada produto;
4. atualiza o catálogo público e o **painel de postagem**, com a mensagem pronta pro grupo.

- **Catálogo:** `https://SEU-USUARIO.github.io/NOME-DO-REPOSITORIO/`
- **Painel de postagem:** o mesmo endereço com `#painel` no final. Lá você copia as mensagens das ofertas novas e cola no grupo.

---

## Configuração (faz uma vez só)

Todas as chaves ficam em **Settings › Secrets and variables › Actions**, na aba **Secrets**, botão **New repository secret**. Ninguém consegue ver o que você coloca ali, nem quem visita o repositório.

### 1. Ligar o site
**Settings › Pages ›** em *Source*, escolha **GitHub Actions**.

Depois, em **Settings › Secrets and variables › Actions**, aba **Variables**, crie:
| Nome | Valor |
|---|---|
| `SITE_URL` | o endereço do seu catálogo, com `/` no final. Ex.: `https://coolgirls.github.io/coolgirlsstuff/` |

### 2. Shopee
1. Entre em **affiliate.shopee.com.br** com a sua conta de afiliada.
2. Abra a seção **Open API** e gere suas credenciais.
3. Crie os Secrets:

| Nome | O que colar |
|---|---|
| `SHOPEE_APP_ID` | o App ID (só números) |
| `SHOPEE_SECRET` | o Secret (texto comprido) |

A Shopee já devolve as ofertas com o seu link de comissão. Não precisa fazer mais nada.

### 3. Mercado Livre: seus códigos de afiliada
1. No painel de Afiliados do Mercado Livre, gere um link de qualquer produto.
2. Abra esse link e olhe o endereço no navegador. Ele tem `matt_word=...` e `matt_tool=...`.
3. Crie os Secrets:

| Nome | O que colar |
|---|---|
| `ML_MATT_WORD` | o que vem depois de `matt_word=` (até o próximo `&`) |
| `ML_MATT_TOOL` | o número que vem depois de `matt_tool=` |

> **Teste antes de divulgar:** pegue um link do catálogo, abra numa aba anônima e confira, um dia depois, na sua Central de Afiliados se o clique apareceu.

### 4. Mercado Livre: o aplicativo (pra buscar as ofertas)
1. Entre em **developers.mercadolivre.com.br** › **Criar aplicação** (com a mesma conta).
2. Nome: `COOL GIRLS STUFF`. Em **URI de redirecionamento**, coloque exatamente o mesmo valor do `SITE_URL`.
3. Escopo: **somente leitura**.
4. Copie o **Client ID** e o **Client Secret** e crie os Secrets:

| Nome | O que colar |
|---|---|
| `ML_CLIENT_ID` | Client ID |
| `ML_CLIENT_SECRET` | Client Secret |

Se o robô avisar *"client_credentials não aceito"*, faça também o passo 5.

### 5. (Só se o robô pedir) Autorizar o Mercado Livre
1. Crie um token do GitHub: foto do perfil › **Settings › Developer settings › Fine-grained tokens › Generate new token**. Escolha só este repositório e, em *Permissions*, **Secrets: Read and write**. Salve como Secret `GH_PAT`.
2. **Actions › Conectar Mercado Livre › Run workflow** com o campo vazio. Abra o link que aparecer no registro e autorize.
3. Você cai no seu site com um código `TG-...` em destaque. Rode **Conectar Mercado Livre** de novo colando esse código. O código vale só 10 minutos.

### 6. Suas lojas favoritas da Shopee
No `config.toml`, troque `nome` e `shop_id` das duas lojas. O robô olha todas as ofertas delas, com um corte de desconto menor, e elas ganham a etiqueta **K-beauty** no catálogo.

### 7. Ligar
**Actions › Robô de ofertas › Run workflow.** Em 1 ou 2 minutos o catálogo está no ar. Depois ele roda sozinho.

---

## Ajustes do dia a dia
Abra o `config.toml` aqui no GitHub (ícone de lápis), mude e clique em **Commit changes**. O robô roda na hora com a configuração nova.

- `desconto_minimo`: suba se estiver entrando oferta demais; desça se estiver vazio.
- `buscas`: as palavras que o robô procura. Ponha marcas que você ama (ex.: `"cosrx"`, `"la roche-posay"`).
- `palavras_proibidas`: o que nunca pode aparecer.
- `link_do_grupo`: o convite do grupo, que vai no fim das mensagens e no botão do site.

## Se algo der errado
**Actions** › clique na última execução › **Buscar ofertas**. O robô escreve em português o que conseguiu e o que faltou.

## Amazon
A Amazon só libera a API (Creators API) com 10 vendas qualificadas nos últimos 30 dias. Quando chegar lá, gere as credenciais no Associates Central e me chame pra ligar essa parte.

## Para testar no computador (opcional)
```
python testes/simular.py
```
Roda o robô com respostas de mentira das lojas e confere se tudo funciona.
